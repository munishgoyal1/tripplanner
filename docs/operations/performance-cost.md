# Performance and Cost Baseline

This runbook separates three kinds of evidence that answer different questions:

1. A deterministic local regression gate catches large API route/admission slowdowns.
2. Production telemetry shows real chat and provider-tool behavior.
3. Azure Cost Management and Cosmos metrics show billed cost and database efficiency.

Do not substitute one for another. A fast in-process benchmark is not a capacity test,
and a quiet Azure bill does not prove acceptable latency.

## Unified harness reports

`tripplanner.validation.harness.run_scenario` wraps a callable in a scenario/run
context, captures correlated `app_event` evidence, and returns one versioned report.
Pass `output_path` to write the same report as JSON. Its sections cover cost, cache
effectiveness, outbound-request amplification, event duration, and quality.

The cost section deliberately contains separate layers:

1. `measured` contains provider-reported tokens and classified successful Google
  requests observed during the run.
2. `estimated` applies the versioned planning catalog in
  `validation/harness/pricing.py`; these assumptions are not authoritative prices.
3. `billing_reconciliation` is absent until a delayed cloud billing export is supplied.

Google classification uses both endpoint and `X-Goog-FieldMask` because Text Search
and Place Details SKU classes cannot be attributed from host-level telemetry alone.
Optional model-based subjective quality evaluation must record its own LLM evidence
and cost; deterministic plan evals can be adapted with `plan_quality` without a model
call. Harness evaluators calculate evidence, while CI/release gates own thresholds.

## Deterministic regression gate

Run from the repository root:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts\performance_baseline.py `
  --report-path logs\performance\baseline.json
```

The runner exercises the real FastAPI application, identity middleware,
`asyncio.to_thread` delegation, and workspace mutation admission for:

- `GET /trip/view`
- `GET /trip/map`
- `GET /trip/itinerary`
- `POST /trip/stop/booked`

Storage and view computation are replaced with deterministic representative data.
No model, Cosmos, travel provider, email provider, or external network call is made.
Three warmups are excluded, then 30 samples per scenario produce min, mean, p50,
p95, max, HTTP error rate, and total run time. The gate fails on an HTTP error or a
scenario p95 above 750 ms. It also compares LLM usage before and after the run and
fails unless both call and cost deltas are zero.

The 750 ms ceiling is intentionally conservative. It detects accidental blocking,
network access, or gross route/admission regressions without treating workstation or
CI scheduling noise as a product incident. Optimize only after repeated evidence
identifies the same bottleneck. Do not tighten this ceiling from one unusually fast run.

The JSON report is optional evidence under ignored `logs/`; it contains no credentials
or user data. The pytest contract for the runner is:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest -q tests\test_performance_baseline.py
```

## Production latency and provider health

Use [operations-slos.md](operations-slos.md) for the accepted-chat success and p95
latency objectives, low-volume interpretation, release observation, failure diagnosis,
and per-tool latency/error/cache-hit queries. Those events reflect real hosted model,
provider, persistence, and cold-start behavior that the hermetic gate intentionally
excludes.

Investigate a repeated production regression in this order:

1. Separate Container App cold starts from warm requests and confirm the sample count.
2. Use `chat_operation` outcomes and durations to locate the affected window.
3. Use `tool_call` p95, errors, and cache-hit rate to identify provider or cache changes.
4. Check Cosmos latency, normalized RU consumption, and HTTP 429 throttling.
5. Change code, cache policy, throughput, or hosting only when that evidence identifies
   the controlling cost or latency source.

## Cost review

Application LLM cost is available through the existing per-user monthly usage ledger
and `/usage` API. The local gate proves only that its own execution adds no model calls;
it does not forecast real trip-planning token consumption.

For Azure spend, review Cost Management over a representative date range grouped by
resource, service, and meter. Compare against request volume before attributing a
change to code. For Cosmos, correlate billed provisioned throughput with normalized RU
consumption, server-side latency, and throttled requests; sustained low utilization is
a sizing signal, while 429s or high normalized RU require query/partition analysis
before reducing throughput.

Provider dashboards remain the source of truth for Google Places/Maps, Duffel,
Amadeus, Tavily, and email usage. Never run a synthetic load test against paid
providers or production user data without an explicit budget, isolated identity/data,
and owner approval.
