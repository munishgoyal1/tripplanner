# Production Observability and SLOs

This runbook defines the initial production reliability contract for the hosted
trip planner. It uses the existing PII-safe JSON event stream written to Azure
Container Apps stdout and retained in Log Analytics for 30 days. It does not
add Application Insights or duplicate telemetry infrastructure.

## Automatic production failure alert

Production Bicep enables one Azure Monitor scheduled-query rule over the
existing production Log Analytics workspace. Every five minutes it checks the
previous five minutes for:

- ordinary JSON records at `ERROR` or `CRITICAL` level;
- terminal `chat_operation` records with `outcome == "error"`; and
- `tool_call` records with `status == "error"`.

Any match opens a severity-1 alert and notifies the production Action Group at
`munishgoyal@aitripplanner.co` using Azure Monitor's common alert schema. The alert is
stateful, so a continuing failure condition remains one alert instead of sending
one email per log line. Auto-mitigation resolves it after the query is clean.

The query is owned by `infra/queries/application-failures.kql` and loaded by
`infra/main.bicep`. `enableFailureAlerts` defaults to false and is enabled only
by `infra/prod.bicepparam`; local and canary never create email alerts. Creating
or changing the production Action Group still requires the normal
`APPROVE_PROD_DEPLOYMENT` gate and a deletion-free production `what-if`.

After the approved first deployment, send an Action Group test notification and
confirm delivery. Then validate the query with a controlled PII-safe error event;
do not create a user-facing outage just to test alerting.

## Local and canary analysis

Local FastAPI startup retains a rotating, PII-redacted JSON stream at
the primary Git checkout's `logs/diagnostics/local-app.jsonl` while leaving
console output human-readable. Primary and worker VS Code windows resolve the
same path through Git's common directory. Analyze it after a development session
or from a daily Windows scheduled task:

```powershell
.\scripts\analyze-errors.ps1 -Environment local -Hours 24
```

Canary analysis reads its existing Log Analytics workspace through the signed-in
Azure CLI and uses the exact production failure query:

```powershell
.\scripts\analyze-errors.ps1 -Environment canary -Hours 24
```

Each command writes a redacted Markdown report under ignored
`logs/diagnostics/`. Exit code `0` means no matching failures; exit code `1`
means failures were grouped with targeted checks for application, chat, or tool
health. Run canary analysis after smoke and at least daily during a bake. A
Windows Task Scheduler job may invoke the same command daily; it needs only the
user's existing Azure CLI session and sends no email.

## Service-level indicators

Every terminal `POST /chat` and `POST /chat/stream` path emits one
`chat_operation` event with:

- `outcome`: `completed`, `replayed`, `capped`, or `error`.
- `duration_ms`: elapsed time from request admission through terminal result.
- `transport`: `json` or `sse`.
- `error`: exception class for failures, never the exception message.
- `user`: a stable one-way hash, never the raw principal.

Final Azure OpenAI `RateLimitError` records also include only safe provider
metadata: deployment, HTTP status, inferred token/request scope, retry delay,
and remaining token/request headers when Azure returns them. Response bodies,
prompts, credentials, and user text are never included.

`completed` and `replayed` are successful service outcomes. `capped` is an
intentional product-policy outcome and is excluded from the reliability
numerator and denominator. `error` includes admission, persistence, usage-check,
model, tool-graph, and final transcript-save failures.

## Initial objectives

These are pragmatic objectives for a low-traffic personal application, not a
claim that the service already has enough production volume to prove them.

| Indicator | Objective | Window | Minimum sample |
| --- | ---: | ---: | ---: |
| Accepted chat success rate | >= 99% | Rolling 30 days | 20 accepted operations |
| Accepted chat p95 latency | <= 120 seconds | Rolling 30 days | 20 accepted operations |
| Release observation success rate | 100% | 30 minutes after production release | 1 accepted operation |

A low-volume window below the minimum sample is reported as insufficient data,
not as passing. Public availability is currently enforced by the independent
hosted smoke suite before and after promotion. A true uptime SLO needs an
external scheduled probe; Container App logs alone cannot detect requests that
never reach the app.

## Log Analytics queries

Replace the app-name predicate only if resource naming changes. Container Apps
stores each JSON stdout line in `Log_s`.

### Rolling chat SLO

```kql
let Window = 30d;
let MinimumSample = 20;
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(Window)
| where ContainerAppName_s startswith "prod-app-"
| extend event = parse_json(Log_s)
| where tostring(event.event_kind) == "chat_operation"
| extend outcome = tostring(event.outcome), duration_ms = todouble(event.duration_ms)
| where outcome != "capped"
| summarize
    accepted = count(),
    succeeded = countif(outcome in ("completed", "replayed")),
    errors = countif(outcome == "error"),
    p95_ms = percentile(duration_ms, 95)
| extend
    success_rate_pct = round(100.0 * succeeded / accepted, 2),
    sample_status = iff(accepted >= MinimumSample, "enough data", "insufficient data"),
    availability_objective_met = accepted >= MinimumSample and success_rate_pct >= 99.0,
    latency_objective_met = accepted >= MinimumSample and p95_ms <= 120000.0
```

### Production release observation

Run this after the critical-flow check and again at the end of the 30-minute
observation period.

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(30m)
| where ContainerAppName_s startswith "prod-app-"
| extend event = parse_json(Log_s)
| where tostring(event.event_kind) == "chat_operation"
| extend
    outcome = tostring(event.outcome),
    duration_ms = todouble(event.duration_ms),
    transport = tostring(event.transport),
    error = tostring(event.error)
| project TimeGenerated, outcome, duration_ms, transport, error
| order by TimeGenerated desc
```

### Failure diagnosis

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(24h)
| where ContainerAppName_s startswith "prod-app-"
| extend event = parse_json(Log_s)
| where tostring(event.event_kind) == "chat_operation"
| where tostring(event.outcome) == "error"
| summarize failures = count() by error = tostring(event.error), bin(TimeGenerated, 1h)
| order by TimeGenerated desc, failures desc
```

For the shared alert/analyzer classification, run the checked-in query directly:

```kql
// infra/queries/application-failures.kql
ContainerAppConsoleLogs_CL
| extend event = parse_json(Log_s)
| extend
    level = toupper(tostring(event.level)),
    event_kind = tostring(event.event_kind),
    outcome = tostring(event.outcome),
    status = tostring(event.status)
| where level in ("ERROR", "CRITICAL")
    or (event_kind == "chat_operation" and outcome == "error")
    or (event_kind == "tool_call" and status == "error")
```

### Tool health

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(24h)
| where ContainerAppName_s startswith "prod-app-"
| extend event = parse_json(Log_s)
| where tostring(event.event_kind) == "tool_call"
| summarize
    calls = count(),
    errors = countif(tostring(event.status) == "error"),
    cache_hits = countif(tobool(event.cache_hit)),
    p95_ms = percentile(todouble(event.ms), 95)
    by tool = tostring(event.tool)
| extend error_rate_pct = round(100.0 * errors / calls, 2)
| order by errors desc, p95_ms desc
```

### Chat, workflow, and storage phases

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(24h)
| where ContainerAppName_s startswith "prod-app-"
| extend event = parse_json(Log_s)
| where tostring(event.event_kind) in
    ("chat_phase", "workflow_operation", "storage_operation")
| extend
    kind = tostring(event.event_kind),
    operation = tostring(event.operation),
    status = tostring(event.status),
    duration_ms = todouble(event.ms)
| summarize
    calls = count(),
    errors = countif(status == "error"),
    p50_ms = percentile(duration_ms, 50),
    p95_ms = percentile(duration_ms, 95)
    by kind, operation
| order by errors desc, p95_ms desc
```

`chat_phase` separates admission/setup from post-generation finalization. Workflow
and storage spans may be nested, so their summed durations are attribution evidence,
not request wall time. Use `chat_operation` or request duration for end-to-end latency.

## Release response

After production promotion, run the hosted smoke suite, complete one normal
planning turn, and inspect the release-observation query. Roll back when the
smoke suite fails, the representative accepted operation errors, or the new
revision introduces repeated chat failures. A single slow operation is a reason
to investigate tool health; it is not sufficient evidence of a p95 regression.

Do not query the restricted `audit_events` container for routine reliability
monitoring. It contains raw values and is intentionally separate from the
sanitized operational stream.
