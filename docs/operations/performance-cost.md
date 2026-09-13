# Performance and Cost Baseline

This runbook separates three kinds of evidence that answer different questions:

1. A deterministic local regression gate catches large API route/admission slowdowns.
2. Production telemetry shows real chat and provider-tool behavior.
3. Azure Cost Management and Cosmos metrics show billed cost and database efficiency.

Do not substitute one for another. A fast in-process benchmark is not a capacity test,
and a quiet Azure bill does not prove acceptable latency.

## Unified harness reports

### Daily ceiling estimate reconciliation (2026-09-12)

The cost ledger's unknown-call P95 floor is a safety fallback, not a provider
price. Missing Tavily prices and classifying free weather as billable caused
ordinary background views to settle at INR 40 each. The provider catalog now
estimates basic search at $0.009 and advanced/legacy unspecified search at
$0.018: [Tavily PAYG](https://docs.tavily.com/documentation/api-credits) is
$0.008 per credit, with one/two credits respectively; the estimate includes
12.5% headroom and assumes no available free credits. Other Tavily endpoints
remain unpriced rather than inheriting a search price.

Only the public forecast, archive and geocoding Open-Meteo hosts are excluded
from spend ([public API pricing](https://open-meteo.com/en/pricing)). Customer
hosts remain subject to pricing/fallback. Unknown paid providers still trigger
the existing P95 floor. Azure uses the existing measured-token catalog.

Google remains priced at conservative global gross rates. India eligibility
and billing-account-wide free-pool consumption must be verified before lowering
admission charges using [India prices](https://developers.google.com/maps/billing-and-pricing/pricing-india).
Free pools in `cost-model.json` size quotas; they are not proof of a remaining
credit balance and must not be blindly subtracted once per project or day.

Historical counters do not change automatically when a catalog changes. Repair
only identified settled interactions with complete evidence, retain unknown or
truncated evidence at its original charge, back up the window document, apply
each credit once with an ETag check, preserve holds and unmatched spend, and
record the source IDs and old/new estimates with the correction. Never reset a
whole counter to zero to unblock the stack.

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

Paid corpus generation applies the same distinction to its safety cap. Its run
and cumulative INR budgets count the measured model-ledger delta plus Google calls
priced from the versioned planning catalog and attributed to that generation turn.
The spend ledger preserves the model and estimated-Google components separately;
Google Cloud Billing remains authoritative for the eventual billed amount.

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
- `POST /chat` with a deterministic fake graph
- `POST /chat/stream` with the same deterministic fake graph

Storage and view computation are replaced with deterministic representative data.
The chat scenarios assert that JSON and SSE terminal payloads agree on reply,
agent, and trip ID. No model, Cosmos, travel provider, email provider, or external
network call is made. Process-local chat concurrency, replay-rate, conversation,
and usage-cap admission state is substituted so repeated samples remain independent;
dedicated request-limit and conversation-limit tests own those safety contracts.
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
per-tool latency/error/cache-hit queries, and `chat_phase`, `workflow_operation`, and
`storage_operation` breakdowns. The hidden owner operations endpoint exposes bounded
process-local p50/p95/error aggregates for those timed operations; Log Analytics is the
durable cross-revision source. Those events reflect real hosted model, provider,
persistence, and cold-start behavior that the hermetic gate intentionally excludes.

Investigate a repeated production regression in this order:

1. Separate Container App cold starts from warm requests and confirm the sample count.
2. Use `chat_operation` outcomes and durations to locate the affected window.
3. Use `tool_call` p95, errors, and cache-hit rate to identify provider or cache changes.
4. Check Cosmos latency, normalized RU consumption, and HTTP 429 throttling.
5. Change code, cache policy, throughput, or hosting only when that evidence identifies
   the controlling cost or latency source.

Cosmos request-charge (RU) capture is implemented. Every point operation in
`storage_cosmos.py` passes a `response_hook` that records the service's
`x-ms-request-charge` onto that operation's `storage_operation` event as `ru`,
alongside the client-observed duration and write payload bytes it already carried.
Azure Cosmos metrics remain the authoritative source for account-level normalized RU
consumption and throttling; the per-operation `ru` field is what makes an individual
container or document shape attributable.

That field is also how the provisioned throughput stays honest. `ruPerSecond` in
`infra/billing-guardrails.json` is derived from the `cosmosSizing.tripOpProfile`
estimate in [`config/cost-model.json`](../../config/cost-model.json), not measured.
Compare observed `ru` per container against that profile when reviewing spend, and
correct the profile rather than the derived output — editing the guardrails file by
hand is what the derivation exists to prevent.

**Free-tier ceiling (owner policy, 2026-09-13).** The data account has
`enableFreeTier`, so the first 1000 RU/s provisioned across the whole account
are free; anything above that is billed every hour, whether or not it is used.
`infra/data.bicep` provisions two databases there. Their hard caps live in
`cosmosSizing.freeTierAllocationRuPerSecond`: canary 400 (Azure's floor) and prod
600, which sum to exactly 1000. Burst sizing (`burstDemandRuPerSecond` in the
guardrails file, 700 today) may ask for more, but `ruPerSecond` never exceeds the
cap, and `derive_limits.py` refuses caps that sum past the free tier. A burst
above the cap does not fail: Cosmos answers 429 with a retry-after of
milliseconds, the SDK retries, and the call is slower. The throttling alert
reports when that stops being occasional. Only a deliberate decision to pay
raises a cap. On 2026-09-13 both databases were deployed at 400 RU/s (800 total).

`storage_operation` is a quiet success event, so a local `logs/diagnostics`
file holds `ru` only for failed or slow operations; read successful charges from
Log Analytics. As of 2026-09-13 no environment had produced any: capture merged
that day, and its first version failed every call (see
`docs/ENGINEERING_LEARNINGS.md`). The 2026-09-13 profile revision therefore
measures document sizes by driving the code's own mutators rather than from
observed charges; replace it with observed `ru` once traffic exists.

### Partitioning

Partition key *values* cost nothing. Billing is provisioned RU/s plus storage;
the number of distinct logical partitions does not appear on the bill, and a point
read or write costs the same RU whatever its partition value. What partitioning
decides is how load can spread once Cosmos splits a container across several
*physical* partitions. It does that past roughly 10,000 RU/s or 50 GB of data, and
each logical partition value stays on exactly one physical partition. A value
every request names can then use only that partition's share of throughput, however
much RU/s is bought, and it is also capped at 20 GB. **At this account's size
(1000 RU/s, a few GB) every container is one physical partition, so today the
bucketing below changes neither cost nor throughput.** It removes a ceiling that
would only bind at a scale far beyond the free tier, and it keeps a
never-expiring cache away from the 20 GB limit. Its present costs are small:
one extra ~1 RU point read the first time each place is looked up (until the
legacy fallback is removed), and cross-partition fan-out on the two owner tooling
queries (`prod_cache_sync`, the cost dashboard), which is free while there is one
physical partition. Every container is partitioned on
`/user_id`. Data with no user writes a synthetic value into that path; changing
the value needs no container rebuild, but it is a data migration for rows already
stored.

- **`places_cache`**: the busiest container in a build, with reads fanned eight at
  a time. It used to keep every place under `_shared`. Each item now lives under
  `place-<first two hex chars of its SHA-1 id>`, giving 256 buckets derived from
  the id, so a place is still a point read (`src/tripplanner/place_cache_layout.py`).
  **Existing rows** were written with `ttl: -1` under `CACHE_STABLE_FOREVER=1`, so
  they never expire, and dropping them would re-buy every place from Google.
  Readers therefore fall back to `_shared` on a bucket miss and re-home what they
  find: the app cache through its background writer, and the secondary cache by
  merging on first write. `scripts/migrate_places_cache_partitions.py` moves the
  rest. It merges each row into its bucket with the shared cache merge policy,
  verifies the result, then deletes the legacy row only if its ETag is unchanged.
  It is a dry run without `--apply` and safe to re-run. Run it on every database
  after deploying: `tripplanner-local`, `tripplanner-cache`, canary and prod.
  `prod_cache_sync.py` refuses to run while legacy rows remain. Once every database
  reports zero legacy rows, the fallback read can be deleted, along with the 20
  fallback reads counted in `tripOpProfile`.
- **`trip_costs` window document**: stays one document per environment on
  purpose. It is the spend ceiling's single source of truth. Sharding it into N
  counters summed on read would let a reservation checked against one shard
  miss a concurrent reservation on another, so turns could together pass checks
  that together breach the ceiling. Contention is reduced instead.
  `cost_ledger._mutate_windows` funnels every mutation in the process through
  one group commit. The caller holding the commit lock applies every queued
  reserve, settle and release, in order, to a single read. Each sees the ones
  before it, and the result is written once. Within a process, collisions
  become batching rather than ETag conflicts. Across processes the ETag check
  still re-reads and re-applies with jittered backoff. Hosting runs
  `maxReplicas = 1`, so cross-process conflicts come only from a deploy overlap
  or an operator tool. Settled-interaction ids are stored as 16-hex digests,
  which cut the document from 11.6 KB to 8.1 KB; every commit rewrites the whole
  document, so write RU scales with its size. **Existing documents** keep their
  balances untouched. Ids already stored in full still count as settled and age
  out of the 200-entry list naturally.
- **`trip_costs` per-trip documents**: moved off the environment partition to
  `<environment>:trip_<id>`, taking one read and one write per settle off the
  partition admission uses. **Existing trip documents** are folded into the new
  location the next time that trip is costed, and the old copy is then deleted.
  The dashboard query covers both locations and de-duplicates by id, so a trip
  not costed since the change still appears.

`tool_cache` (`_global_`) and `shared_trips` (`_shared`) still use one synthetic
partition. `tool_cache` is the second-busiest container in the build profile and
is the next candidate; `shared_trips` is low volume.

## Cost review

Application LLM cost is available through the existing per-user monthly usage ledger
and `/usage` API. Estimates use the versioned catalog in
`validation/harness/pricing.py` (currently `2026-09-10`). That catalog is not an
invoice. Dated nearby-SKU comparison and per-itinerary planning figures live in
[../research/azure-openai-planning-model-2026-09.md](../research/azure-openai-planning-model-2026-09.md).
The local gate proves only that its own execution adds no model calls;
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
