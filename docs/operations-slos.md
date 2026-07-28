# Production Observability and SLOs

This runbook defines the initial production reliability contract for the hosted
trip planner. It uses the existing PII-safe JSON event stream written to Azure
Container Apps stdout and retained in Log Analytics for 30 days. It does not
add Application Insights or duplicate telemetry infrastructure.

## Service-level indicators

Every terminal `POST /chat` and `POST /chat/stream` path emits one
`chat_operation` event with:

- `outcome`: `completed`, `replayed`, `capped`, or `error`.
- `duration_ms`: elapsed time from request admission through terminal result.
- `transport`: `json` or `sse`.
- `error`: exception class for failures, never the exception message.
- `user`: a stable one-way hash, never the raw principal.

`completed` and `replayed` are successful service outcomes. `capped` is an
intentional product-policy outcome and is excluded from the reliability
numerator and denominator. `error` includes admission, persistence, usage-check,
model, tool-graph, and final transcript-save failures.

## Initial objectives

These are pragmatic objectives for a low-traffic personal application, not a
claim that the service already has enough production volume to prove them.

| Indicator | Objective | Window | Minimum sample |
|---|---:|---:|---:|
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

## Release response

After production promotion, run the hosted smoke suite, complete one normal
planning turn, and inspect the release-observation query. Roll back when the
smoke suite fails, the representative accepted operation errors, or the new
revision introduces repeated chat failures. A single slow operation is a reason
to investigate tool health; it is not sufficient evidence of a p95 regression.

Do not query the restricted `audit_events` container for routine reliability
monitoring. It contains raw values and is intentionally separate from the
sanitized operational stream.
