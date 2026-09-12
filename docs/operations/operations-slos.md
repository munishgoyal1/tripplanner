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

Any match opens a `[prod]` severity-1 alert and notifies the production Action Group at
`munishgoyal@aitripplanner.co` using Azure Monitor's common alert schema. The alert is
stateful, so a continuing failure condition remains one alert instead of sending
one email per log line. Auto-mitigation resolves it after the query is clean.

The query is owned by `infra/queries/application-failures.kql` and loaded by
`infra/main.bicep`. `enableFailureAlerts` defaults to false and is enabled only
by `infra/prod.bicepparam`; local and canary never create email alerts. Creating
or changing the production Action Group still requires the normal
`APPROVE_PROD_DEPLOYMENT` gate and a deletion-free production `what-if`.

This alert, the four operational alerts below (latency burn, model throttling,
circuit breaker, cache degradation), and the Cosmos 429 alert are all **infra
health / error signals, not billing/cost alerts** — their severity, evaluation
window, and threshold are declared in `azureInfraHealthAlerts` in
[`infra/billing-guardrails.json`](../../infra/billing-guardrails.json), the
single config file for every Azure + GCP alert (billing guardrails live in the
same file, under `gcp`/`azure`/`gcpQuotaAlertPolicies`). `infra/main.bicep`
reads that JSON via `loadJsonContent()`; only the KQL query bodies stay as
separate files under `infra/queries/`, since Bicep needs a literal path to
load file content.

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


## Private flight recorder

Disabled by default (`TRIPPLANNER_FLIGHT_RECORDER=0`) in every environment. Set it
to `1` in `config/environments/<environment>.env` and restart the backend to
record a diagnostic session; set it back to `0` and restart when finished. Process
environment overrides retain precedence. This master flag also gates the local
trip archive (`TRIPPLANNER_DEBUG_STORE` remains its local-only sub-control).
Disabling preserves existing history and ordinary logs, alerts and usage ledgers,
while skipping recorder callbacks, custom model transports and capture work. This is
separate from content-free rotating logs and the local-only `debug-store` archive.
Set `TRIPPLANNER_FLIGHT_RECORDER_DIR` to a private writable path; by default it uses
`~/.tripplanner/flight-recorder/<environment>`. Callers enqueue bounded snapshots;
the worker writes atomic fsynced batches. Windows inherits the private user's directory ACL;
POSIX files use mode 0600. Never commit or publish these records.

When Cosmos is configured, a daemon periodically retries the spool into the
environment database's `flight_recorder` container (`/user_id` partition). Successful
uploads remove the spool file. JSON is gzip/base64 encoded into <=128,000-character
chunks with an event checksum/count. An interrupted upload retries idempotently;
export rejects missing or corrupt chunks. Runtime container creation and IaC both
set a seven-day TTL. Without Cosmos, local files expire after seven days when the
worker runs. Hosted missing/unavailable Cosmos is degraded, not a successful durable
archive. A lost container disk can lose its unuploaded spool; use persistent storage
when this residual window is unacceptable. No per-token Cosmos writes occur.

The daemon drains at most 25 spool batches per worker pass by default (configurable with
`TRIPPLANNER_FLIGHT_RECORDER_BATCH_SIZE`, clamped to 1-500) and emits at most one
progress summary per minute. Successful `storage_operation`, `cache_access`, duplicate
`outbound_call`, cache-served `provider_call`, and `llm_usage` events continue to feed
alert observers, metrics, and content-free ledgers, but are intentionally absent as
individual console/app-file and recorder-spool entries. One interaction-summary event
retains their aggregate counts in private flight evidence and one content-free durable
telemetry-summary row supports the operations dashboard. Cache-usage ledger rows are
also coalesced by interaction/provider/operation while preserving exact `units` and
estimated savings. Failures remain visible. Human-facing logs retain API completions,
LLM/tool/attempted-provider activity, workflow stages, and one interaction summary.
Local LLM prompt lines contain at most 100 PII-scrubbed words and the complete word
count; hosted prompt lines contain counts only. Provider lines include service,
purpose/dataset, SKU, billing posture, HTTP status, and duration. Local provider and
summary lines may include bounded Places names, while hosted logs remain content-free.

`GET /providers/status` includes non-sensitive `outbound.flight_recorder` health:
enabled, last error type, last successful upload and pending event count. Watch
`flight_recorder_degraded` logs and spool growth. A start without an end means a
crash/interruption or missing evidence; never infer successful completion from it.
An integrity-checked event does not certify that the itinerary itself is correct.

Trip flow reconstruction: semantic console lines carry `trip=<trip_key>` and
`flow=<flow_key>` when attributed; model preview/result pairs also carry the
same `call` ID as the private recorder span. Keys are the first 16 hex characters
of SHA-256 of the original trip/interaction ID, preserving joins even when phone
redaction scrubs digits in legacy ID fields. Filter `logs/diagnostics/local-app.jsonl`
with `rg '<copied flow key>'` for a turn, or the trip key for all its turns.
The FLOW terminal outcome follows `chat_operation`; failures print ERROR with
their exception class instead of an ambiguous INFO event name.
Prompt previews show the latest user request (up to 40 words) and latest message,
still capped at 100 words overall. Full counts and the text hash cover message
text and tool arguments, including normalized LangChain tool calls, but exclude
tool schemas and wire serialization. Private `http.attempt` is the exact wire
request evidence when verbose capture is enabled; failures retain bounded excerpts.
Multiple model rounds follow tool results; round lines give
the forced tool and reason. Successful cache/storage measurements remain aggregated.

`COST settled` reconciles the interaction reservation with catalog-estimated
spend and unknown-cost allowances; it is not a provider invoice or payment.
An attempted model call without usage has `billing_status=unknown`, remains
eligible for the ledger's conservative unknown-cost allowance, and must not be
presented as free. Cache-served calls remain explicitly nonbillable.

Export with the target environment's ordinary operator credentials (no public
payload-read endpoint is exposed). Specify `--cosmos` when the environment uses
Cosmos; otherwise this reads the private local spool/archive:

```powershell
$env:TRIPPLANNER_ENVIRONMENT = 'local'
python -m tripplanner.flight_recorder --user-id USER_ID --trip-id TRIP_ID --cosmos --output C:/private/kashmir-flight.json
```

Omit `--trip-id` to inspect the user's retained turns; use `--trace-id` for one run.
Trip filtering includes earlier research from the same trace before the trip ID
was assigned. Export refuses to overwrite an existing file. Reconstruct using
`trace_id`, `span_id`/`parent_span_id`, `attempt_id`, `interaction_id`, `request_id`
and UTC timestamps; sequence disambiguates events with the same clock reading.
`chat.persisted` and `trip.saved` establish successful persistence, while attempt
and graph error events preserve failed work. Account clear/delete removes the
user's recorder partition and pending files along with ordinary user data.

Coverage: graph/turn lifecycle, model prompts including tool schemas, model replies
and token metadata, all five current model construction paths, shared travel-provider
HTTP requests/responses, model transport attempts/retry counts and partial stream
failures, tool callbacks, application logs/events, planner JSON/SSE bodies, revisions.
Secrets are redacted; document-extraction model content and binary media are recorded
as metadata only. OAuth/document route bodies are excluded. Browser-owned Maps SDK
network calls and storage/auth SDK-internal retries are not intercepted by this
server recorder. SDK usage and billing records remain complementary evidence.

After deploying to each hosted environment, run one normal authorized planning turn
and export its trace. Verify the model/tool pairs, retry status if one occurred,
final transcript and saved revision, and a drained healthy spool. This task's
hermetic tests do not substitute for that live deployment smoke check.


### Bounded recorder defaults (2026-09-12)

Normal HTTP successes retain byte counts/hashes and correlation, not bodies.
Failures retain at most 64 KiB per HTTP request/response, marked truncated when
necessary. `TRIPPLANNER_FLIGHT_RECORDER_VERBOSE=1` enables successful HTTP body
capture with the same bound. Model and tool callbacks retain metadata only; exact
wire evidence has one owner at the HTTP boundary. The independent opt-in local
`LOG_FULL_LLM_PROMPTS` console facility is unchanged.

Recorder callers enqueue snapshots (at most 256 KiB each) into an 8 MiB / 512-event
queue. A worker groups up to 25 events for the same user/trace into one spool write
and one compressed Cosmos envelope. Queue overflow is counted and logged, with
failure events prioritized. Normal shutdown flushes to disk without waiting for
Cosmos. A hard crash can lose the last unflushed diagnostic events; accounting and
trip persistence do not use this lossy queue. Export expands both old individual
records and new batch envelopes before filtering/sorting, preserving original IDs.
`spooled_events` is a legacy status name counting spool files/batches; queued event
and byte counts and dropped events are exposed separately.

The local recorder spool is capped at 50 MiB and seven days. The local interaction
study archive keeps only trip turns, actual provider attempts and failures; successful
cache-only/read-only requests do not create study files. Its details are bounded
(200 events / 100 provider entries with truncation metadata) and retention runs
asynchronously, at most once per ten minutes, to seven days / 50 MiB. The complete
provider/cost ledger remains separate and is not sampled or pruned by these caps.
Historical test-contaminated data must not be treated as verified real API usage.
