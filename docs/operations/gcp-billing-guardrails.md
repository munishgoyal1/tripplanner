# Google Cloud Billing Guardrails

Reproducible setup for per-environment budgets, a global spend cap, hard API
quotas, and an automatic billing shutoff on Google Cloud. Written so the whole
arrangement can be recreated on a different Google account without rediscovering
the flag names and gotchas.

Azure spend is governed separately by
[deployment-flow.md](deployment-flow.md) and [performance-cost.md](performance-cost.md).
This document covers only Google Maps Platform and the Cloud Billing account
behind it.

## Apply from the repository

All account-specific identifiers and limits live in
[`infra/billing-guardrails.json`](../../infra/billing-guardrails.json). For a
new account, edit that file and authenticate once, then preview and apply:

```powershell
pwsh -File infra/gcp/apply-billing-guardrails.ps1 -WhatIf
pwsh -File infra/gcp/apply-billing-guardrails.ps1
```

Subsequent service-state, budget, and limit changes do not require an application
deployment or a function redeployment:

```powershell
pwsh -File infra/gcp/apply-billing-guardrails.ps1
```

The script is idempotent: it updates existing budgets and quota preferences and
does not duplicate alert policies. The detailed commands below explain and
troubleshoot what the script automates.

Quota applies never loosen an existing lower preference by default. Pass
`-AllowQuotaIncreases` only for a deliberate capacity increase.

## What a budget does and does not do

A Cloud Billing budget **only sends notifications**. Nothing in Google Cloud
stops spending on its own, and reported cost lags real usage by hours. Three
independent layers are therefore needed:

| Layer | Reacts in | Stops spend? | Blast radius |
| --- | --- | --- | --- |
| API quotas | real time | yes, rejects calls | one API in one project |
| Budget alerts | hours | no | informational |
| Billing shutoff function, when armed | hours | yes, detaches billing | every project on the account |

Quotas are the only real-time control. Treat the shutoff as a backstop for a
slow leak, not as protection against a runaway loop.

The application adds two earlier boundaries, and they do different jobs.

**Authorization.** Paid travel-provider calls are denied unless execution is
inside a named `user_interaction` or `corpus_generation` scope. Reusable view
builders, audits, tests, issue-fix validation, and background work cannot create
that scope, and the common outbound HTTP runtime rejects unscoped requests to
known billable Google hosts before opening the network client. This scope does
**not** cap how many calls an authorized request makes — see
[Spend ceiling](#spend-ceiling).

**Spend.** A measured INR ceiling (daily/weekly/monthly, Azure and Google
combined) refuses new turns once the environment has spent its budget. Unlike a
budget alert this reacts per turn rather than in hours, and unlike a quota it
covers both clouds at once.

| Layer | Reacts in | Stops spend? | Bounds |
| --- | --- | --- | --- |
| Paid-provider scope | real time | yes, denies the call | unauthorized callers |
| INR spend ceiling | per turn | yes, HTTP 429 | environment-wide money, both clouds |
| API quotas | real time | yes, rejects calls | one API in one project |

These complement rather than replace cloud quotas: quotas remain the protection
against a compromised process or key, where in-application controls cannot help.

`shutoffEnabled` in the central JSON is the arming switch. It is currently
`false`: the observation budget was lowered after this month's accrued spend had
already crossed it, so arming would immediately detach every funded project.
The active function and Eventarc trigger were removed; their source and corrected
IAM provisioning remain in the repository. Deploy only at the start of a fresh
billing period or with a threshold above already reported spend. Arming requires
setting `shutoffEnabled` to `true` and then running:

```powershell
pwsh -File infra/gcp/apply-billing-guardrails.ps1 `
  -DeployShutoffFunction `
  -ShutoffApproval APPROVE_ACCOUNT_WIDE_BILLING_SHUTOFF
```

The apply deletes any old function and trigger before updating the global
budget, then recreates Eventarc with an explicit trigger service account. This
prevents a stale failed delivery from surviving across a disarm/re-arm cycle.

## Current arrangement

Billing account `01AD51-0D422D-41459D`, currency **INR**.

| Environment | Project ID | Number |
| --- | --- | --- |
| local | `aitripplanner-local` | 462807288215 |
| canary | `aitripplanner-canary` | 776481421915 |
| prod | `project-8fc6cc28-590c-4f8b-987` | 153809333272 |
| ops tooling | `aitripplanner-ops` | 266614639212 |

Budget tooling lives in the separate `ops` project so its own cost does not
distort a per-environment number.

| Budget | Amount | Scope | Thresholds |
| --- | --- | --- | --- |
| `tripplanner-local-2000inr` | 24,000 INR | local project | 50 / 80 / 100% |
| `tripplanner-canary-2000inr` | 600 INR | canary project | 50 / 80 / 100% |
| `tripplanner-prod-2000inr` | 1,800 INR | prod project | 50 / 80 / 100% |
| `tripplanner-global-8000inr` | 26,400 INR | whole billing account | 50 / 80 / 90 / 100% → Pub/Sub |

Cloud Billing budgets are monthly; the global amount is always the exact sum of
the three per-environment amounts, so the account-wide alert stays meaningful
relative to what the environments can actually spend. Local development is
budgeted at 800 INR/day (raised 2026-09-11, see "Local testing headroom"
below), canary at 20 INR/day, and production at 60 INR/day -- each with its own
project-level budget so environment-specific alerts stay distinct.

### Local testing headroom

The local per-day budget and the local rows of the quota table below were
raised on 2026-09-11 after ordinary local development -- building and testing
2-3 trips back-to-back in one sitting -- was found to trip the app's
`places.googleapis.com` circuit breaker (`src/tripplanner/circuit_breaker.py`,
30-second fixed cooldown once open) purely from exhausting the previous
30-per-minute local quota, not from any runaway loop. Once the breaker opens it
blocks every Places call (search **and** photo-media share one breaker per
provider), so an ordinary trip switch could stall for 40-60+ seconds waiting
out the cooldown plus the rate limiter's own queued wait
(`places_cache.py`'s `_pace()`). Google's signed photo-media URLs are
short-lived and are not part of the durable place-metadata cache, so even a
"fully cached" trip re-resolves photo URIs -- and therefore re-consumes the
per-minute photo quota -- on every session.

Per-minute quotas are sized for **burst smoothness, not for cost**. Since
2026-09-12, local testing allows 90 Text Search and 120 Photo Media requests per
minute; Place Details stays at 40. Canary and production retain 60/60/40.
`quotaSizing.burstPerMinuteFloor` in `config/cost-model.json` accepts either a
shared integer or an explicit local/canary/prod object. Run
`python scripts/derive_limits.py` after changing it; the generated quota rows
also supply the application's per-process pacing limit.

The sizing target is one ordinary cold trip, with overlap allowed to wait:
40 itinerary places plus 18 guide suggestions per city across four cities is
112 one-photo places before deduplication. The regression burst uses 112 photo
calls and 80 searches (40 itinerary lookups, 12 city/category searches, and 28
additional planning lookups). The first burst fits without pacing sleep; a
second overlapping burst waits. This is a bounded capacity test, not a promise
that an arbitrarily long trip or an already-used quota window cannot throttle.
Daily quotas, spend ceilings, and quota alert sensitivity are unchanged.

Apply the two local quota preferences before restarting the local backend with
the updated generated configuration. The full guardrails apply command also
manages budgets and services; for this targeted change use `gcloud quotas
preferences update` for `tp-searchtextrequestperminuteperproject` and
`tp-getphotomediarequestperminuteperproject` in `aitripplanner-local`, then verify
their effective values through Cloud Quotas. Google counts all processes in the
project together; the app's in-memory pacing window is per process.

The owner's stated constraint -- testing spend should stay well under ~1,000
INR/day -- is now enforced directly rather than approximated by quotas, by
`COST_CEILING_INR_DAILY=1000` (see [Spend ceiling](#spend-ceiling)). Quotas
remain the real-time protection against a repeat of the 2026-08-27 incident
documented at the bottom of this file, because an in-application ceiling cannot
help against a leaked key or a compromised process.

The display names predate the lower observation-mode amounts. They are retained
so the idempotent apply updates the existing budgets instead of creating
duplicates. These budgets currently alert; the global automatic detach is
disarmed as described above.

## Prerequisites

```bash
brew install --cask google-cloud-sdk
export PATH=/opt/homebrew/share/google-cloud-sdk/bin:"$PATH"

gcloud auth login                      # user credentials
gcloud auth application-default login  # ADC, required by the Budgets API
```

Both sign-ins are needed. The Budgets and Quotas APIs authenticate through ADC
and additionally require a **quota project**, which is not set by default:

```bash
gcloud config set project "$OPS_PROJECT"
gcloud config set billing/quota_project "$OPS_PROJECT"
gcloud auth application-default set-quota-project "$OPS_PROJECT"
```

Without the `billing/quota_project` property every budget command fails with
`SERVICE_DISABLED` naming Google's own client project rather than yours, which
reads like a permissions problem and is not one.

## Recreate on a new account

Set the variables once:

```bash
export PATH=/opt/homebrew/share/google-cloud-sdk/bin:"$PATH"
export BA=<billing-account-id>          # gcloud beta billing accounts list
export OPS_PROJECT=<prefix>-ops
export ENV_PROJECTS="<local-id> <canary-id> <prod-id>"
export ALERT_EMAIL=<you@example.com>
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
```

### 1. Ops project and APIs

```bash
gcloud projects create "$OPS_PROJECT" --name="$OPS_PROJECT"
gcloud beta billing projects link "$OPS_PROJECT" --billing-account="$BA"
gcloud services enable \
  billingbudgets.googleapis.com cloudbilling.googleapis.com \
  cloudquotas.googleapis.com cloudresourcemanager.googleapis.com \
  iam.googleapis.com monitoring.googleapis.com \
  pubsub.googleapis.com cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com run.googleapis.com eventarc.googleapis.com \
  --project="$OPS_PROJECT"
gcloud components install alpha --quiet
```

Enable `eventarc` up front. The Cloud Function deploy otherwise stops on an
interactive prompt part way through.

### 2. Per-environment budgets

Budget amounts must use the billing account's own currency. Confirm it with
`gcloud billing budgets list --billing-account="$BA"` before assuming.

```bash
for pair in local:<num> canary:<num> prod:<num>; do
  gcloud billing budgets create --billing-account="$BA" \
    --display-name="tripplanner-${pair%%:*}-2000inr" \
    --budget-amount=2000INR \
    --calendar-period=month \
    --filter-projects="projects/${pair##*:}" \
    --threshold-rule=percent=0.5,basis=current-spend \
    --threshold-rule=percent=0.8,basis=current-spend \
    --threshold-rule=percent=1.0,basis=current-spend
done
```

`--filter-projects` takes the project **number**, not the project ID. Threshold
alerts email the billing account admins with no extra configuration.

### 3. Global budget and shutoff topic

```bash
gcloud pubsub topics create billing-shutoff --project="$OPS_PROJECT"

gcloud billing budgets create --billing-account="$BA" \
  --display-name="tripplanner-global-8000inr" \
  --budget-amount=8000INR \
  --calendar-period=month \
  --threshold-rule=percent=0.5,basis=current-spend \
  --threshold-rule=percent=0.8,basis=current-spend \
  --threshold-rule=percent=0.9,basis=current-spend \
  --threshold-rule=percent=1.0,basis=current-spend \
  --notifications-rule-pubsub-topic="projects/$OPS_PROJECT/topics/billing-shutoff"
```

The flag is `--notifications-rule-pubsub-topic`; older documentation shows
`--all-updates-rule-pubsub-topic`, which no longer exists. Creating the budget
grants `roles/pubsub.publisher` to `billing-budget-alert@system.gserviceaccount.com`
automatically, so do not try to add that binding by hand first.

### 4. Shutoff identity and function

```bash
gcloud iam service-accounts create billing-shutoff --project="$OPS_PROJECT"
SA="billing-shutoff@$OPS_PROJECT.iam.gserviceaccount.com"

gcloud beta billing accounts add-iam-policy-binding "$BA" \
  --member="serviceAccount:$SA" --role="roles/billing.admin"

for p in $ENV_PROJECTS "$OPS_PROJECT"; do
  gcloud projects add-iam-policy-binding "$p" \
    --member="serviceAccount:$SA" --role="roles/billing.projectManager"
done

gcloud functions deploy billing-shutoff --gen2 --runtime=python312 \
  --region=asia-south1 --source=infra/gcp/billing-shutoff \
  --entry-point=shutoff --trigger-topic=billing-shutoff \
  --service-account="$SA" \
  --set-env-vars="BILLING_ACCOUNT=$BA,GUARDED_BUDGET=tripplanner-global-8000inr" \
  --project="$OPS_PROJECT"
```

Source is [../../infra/gcp/billing-shutoff/main.py](../../infra/gcp/billing-shutoff/main.py).
It ignores messages from every budget except `GUARDED_BUDGET`, so the
per-environment budgets can share the topic later without triggering a shutoff.

### 5. Hard API quotas

List the settable limits before guessing at names; they differ per service.

```bash
gcloud quotas info list --service=places.googleapis.com \
  --project=<project> --format="value(quotaId)"
```

Apply a limit:

```bash
gcloud quotas preferences create --project=<project> \
  --service=places.googleapis.com \
  --quota-id=SearchTextRequestPerDayPerProject \
  --preferred-value=<n> \
  --preference-id=tp-searchtextrequestperdayperproject \
  --allow-high-percentage-quota-decrease \
  --allow-quota-decrease-below-usage
```

Both `--allow-*` flags are required when tightening a limit by more than ten
percent or below current usage, which is almost always the case when moving from
Google's generous defaults.

**The quota rows below are derived, not hand-set.** `scripts/derive_limits.py`
computes them from the INR ceilings in `config/environments/*.env` plus
`config/cost-model.json`, and `tests/test_limits_derivation.py` fails if the
checked-in values drift. Edit the ceiling or the cost model, then run:

```powershell
python scripts/derive_limits.py
```

Two sizing rules, deliberately different:

- **Daily quotas are cost-derived**, sized as this environment's slice of the
  pooled free monthly allowance *plus* what the daily INR ceiling can buy beyond
  it. They sit **above** the budget on purpose: the ceiling must refuse first, so
  a quota never throttles a legitimately complex trip. A quota's job is to stop a
  compromised key or a runaway loop, not to manage spend.
- **Per-minute quotas are not cost-derived.** They exist so `places_cache._pace`
  can self-pace under the same ceiling Google enforces without tripping the
  provider circuit breaker. Sizing them for cost is what produced the 40-60 second
  stalls described under "Local testing headroom", so they come from
  `quotaSizing.burstPerMinuteFloor` and are identical across environments.

Cache hits do not consume these limits. Lower-volume API surfaces remain pinned
low so a leaked key cannot spend the cloud allowance through an unused operation.

| Quota | local | canary | prod |
| --- | --- | --- | --- |
| `SearchTextRequestPerDayPerProject` | 849 | 441 | 674 |
| `SearchTextRequestPerMinutePerProject` | 60 | 60 | 60 |
| `GetPlaceRequestPerDayPerProject` | 456 | 375 | 421 |
| `GetPlaceRequestPerMinutePerProject` | 40 | 40 | 40 |
| `SearchNearbyRequestPerDayPerProject` | 10 | 2 | 3 |
| `SearchNearbyRequestPerMinutePerProject` | 10 | 10 | 10 |
| `AutocompletePlacesRequestPerDayPerProject` | 60 | 5 | 20 |
| `AutocompletePlacesRequestPerMinutePerProject` | 20 | 20 | 20 |
| `GetPhotoMediaRequestPerDayPerProject` | 1,217 | 1,217 | 1,217 |
| `GetPhotoMediaRequestPerMinutePerProject` | 60 | 60 | 60 |
| `BillableDefaultPerDayPerProject` (Places JavaScript) | 400 | 20 | 50 |
| `BillableDefaultPerMinutePerProject` (Places JavaScript) | 60 | 60 | 60 |
| `ComputeRoutesRequestsPerDay` | 200 | 20 | 50 |
| `ComputeRoutesRequestsPerMinutePerProject` | 60 | 60 | 60 |
| `ComputeRouteMatrixCellsPerDay` | 1,000 | 100 | 250 |
| `ComputeRouteMatrixCellsPerMinutePerProject` | 240 | 240 | 240 |
| `BillableDefaultPerDayPerProject` (Static Maps) | 200 | 20 | 50 |
| `BillableDefaultPerMinutePerProject` (Static Maps) | 60 | 60 | 60 |
| `BillableDefaultPerDayPerProject` (Maps JavaScript) | 500 | 50 | 100 |
| `BillableDefaultPerMinutePerProject` (Maps JavaScript) | 90 | 90 | 90 |

`requiredServices` must equal the union of `browserServices` and
`serverServices`. The release contract requires every callable service to have
both a project-level daily cap and a project-level per-minute cap. Add quota
definitions before adding an API to either credential surface.

Unused API surfaces are pinned low deliberately. An API nobody calls should not
be able to spend money if a key leaks.

### 6. Quota-exceeded alerts

```bash
for p in $ENV_PROJECTS; do
  ch=$(gcloud beta monitoring channels create --project="$p" \
    --display-name="Owner email" --type=email \
    --channel-labels=email_address="$ALERT_EMAIL" \
    --format="value(name)" 2>/dev/null | tail -1)
  gcloud alpha monitoring policies create --project="$p" \
    --policy-from-file=quota-policy.json --notification-channels="$ch"
done
```

Discard stderr when capturing the channel name. `gcloud` prints a `WARNING:`
line on an empty filter result that otherwise lands inside the variable and
produces a misleading `Projects instance not found` error.

Each environment policy watches `serviceruntime.googleapis.com/quota/exceeded`
on resource type `consumer_quota`, aligned with `ALIGN_COUNT_TRUE` over five
minutes and grouped by quota metric and service. Titles and documentation carry
`[local]`, `[canary]`, or `[prod]`; local/canary are `WARNING` and production is
`ERROR`. Any rejected request still opens an incident because a hard limit was
actually hit, but recovered incidents auto-close after one hour. Reapplying the
script updates an existing environment policy and migrates the legacy generic
`Maps API quota exceeded` display name instead of leaving stale settings.

The severity-by-environment map, the five-minute alignment period, and the
one-hour auto-close above are not hardcoded in the script — they're read from
`gcpQuotaAlertPolicies` in
[`infra/billing-guardrails.json`](../../infra/billing-guardrails.json), the
single config file for every Azure + GCP alert (billing and infra-health
alike). Change severity or timing there and re-run
`apply-billing-guardrails.ps1`.

## Cost model

Prices below are Google Maps Platform **India** rates, USD per 1,000 calls, from
[the India price list](https://developers.google.com/maps/billing-and-pricing/pricing-india).
Verify them before relying on any number here; Google revises them.

| SKU | Free per month | Then |
| --- | --- | --- |
| Text Search Essentials (IDs only) | unlimited | free |
| Text Search Pro | 35,000 | $9.60 |
| Text Search Enterprise + Atmosphere | 7,000 | $12.00 |
| Place Details Essentials (IDs only) | unlimited | free |
| Place Details Enterprise + Atmosphere | 7,000 | $7.50 |
| Compute Routes Essentials | 70,000 | $1.50 |
| Static Maps | 70,000 | $0.60 |

The free allowances are pooled across **all projects on the billing account**,
not granted per project. Three environments share one allowance.

**The billed SKU is chosen by the request's field mask, not by the endpoint.**
Asking for `rating` promotes a call to Pro; asking for `reviews` or
`editorialSummary` promotes it to Enterprise + Atmosphere, the most expensive
tier. Resolving a place name to an ID and coordinates with an IDs-only mask is
free and unbounded.

The application does **not** cap how many Places calls an authorized scope may
make. Per-scope counters (three Text Search, one review-details, three photo-media)
were retired: they were a proxy for money that throttled quality on legitimately
complex trips, and this document and the deployed configuration had already
drifted 14x apart on what those counters actually were. Spend is bounded instead
by a measured INR ceiling — see [Spend ceiling](#spend-ceiling) below.

What remains is the **authorization scope**, not a budget: a paid Places call is
permitted only inside a named `user_interaction` or `corpus_generation` scope,
which reusable view builders, audits, tests and background warming cannot create.
That gate is the actual 2026-08-27 fix and is unchanged.

Agent discovery results still seed the structured UI cache, routine metadata
omits `editorialSummary`, and unfocused views never fetch reviews.

**The agent's Text Search calls are Pro tier, not Essentials.** Its field masks
request `rating`, `userRatingCount`, `priceLevel` and `websiteUri`
([`tools/google_places.py`](../../src/tripplanner/tools/google_places.py)), any of
which promotes the call past Essentials — `http_client.google_operation` classifies
them correctly. In practice these calls are still free because Text Search Pro
carries a 35,000/month allowance pooled across the billing account, and
`config/cost-model.json` reserves a share of that pool per environment. Once a
share is exhausted the SKU bills at list price and the INR ceiling absorbs it.

### Spend ceiling

One control governs cost, in **INR**, covering Azure OpenAI and Google Cloud
together, environment-wide and identical in local, canary and production:

```dotenv
COST_CEILING_INR_DAILY=1000
COST_CEILING_INR_WEEKLY=5000
COST_CEILING_INR_MONTHLY=10000
```

Enforced by [`cost_ledger.py`](../../src/tripplanner/cost_ledger.py) against the
`estimated_cost_usd` that `provider_usage.record_call` already persists for every
Azure and Google call, converted once via `cost_model.usd_to_inr`. A turn reserves
a pessimistic estimate at admission and reconciles it to actual spend when its
usage batch flushes, so concurrent turns cannot collectively pass a ceiling none
of them individually breaches. A billable call with no price estimate is charged
the rolling P95 rather than zero.

The three windows are not multiples of each other on purpose: daily is a burst
allowance, monthly is the binding constraint. At the ~INR 42 average trip this
model predicts, INR 10,000/month is roughly 13 full testing days.

Per-trip cost, provider-call breakdown, LLM turn counts and anomaly flags are
visible in the owner-only operations dashboard. An expensive trip is something to
investigate there, not a reason to reintroduce a call budget.

This is a catalog estimate, not billed cost; provider billing exports remain
authoritative.

The estimator currently uses conservative global Places list prices before
monthly free allowances, taxes, and account-specific discounts. India pricing
must be verified against the billing account before changing those rates;
the India free-pool assumptions used for quota sizing do not establish billing
eligibility. A lower displayed estimate is not itself a reduction in usage.

As of 2026-09-12, trip view and successful switch requests attach the resolved
trip identity before provider work. The matching destination overview is also
attributed; browsing a different destination is not charged to the active trip.
Google HTTP 429 attempts remain visible as failures, with `quota_rejected`
billing status and zero estimated spend. Historical rows are not rewritten, so
older per-trip totals can still have missing attribution or rejected-call estimates.

Quota alerts retain `limit_name` as well as `quota_metric` and service, so an
email distinguishes per-minute bursts from daily exhaustion. Quotas and spend
ceilings remain unchanged by the photo deduplication/accounting fix. Photo pacing
still uses process-local state: independent processes sharing a project can
collectively reach its quota. Measure remaining bursts before raising headroom;
deduplication does not establish a project-wide rate limiter or a INR 20 trip cost.

### Google API capability gates

One checked-in environment-profile flag owns the desired state for each paid
capability. There is no duplicate desired-state boolean in
[`infra/billing-guardrails.json`](../../infra/billing-guardrails.json):

```dotenv
ENABLE_GOOGLE_PLACES=0
ENABLE_GOOGLE_MAPS=0
```

Checked-in `config/environments/local.env`, `canary.env`, and `prod.env` own the
non-secret switches. Ignored `.env`, `.env.canary`, and `.env.prod` contain the
keys as secret overlays. A key alone never activates a paid request.

| Capability | Application surfaces | GCP Service Usage APIs |
| --- | --- | --- |
| Places | server Places API, browser autocomplete and place details | `places.googleapis.com` |
| Maps | interactive base map, Google Routes fallback, itinerary Static Maps | `maps-backend.googleapis.com`, `routes.googleapis.com`, `static-maps-backend.googleapis.com` |

The local browser key has **no HTTP referrer restriction**. Maps JavaScript
cost is bounded by API-target allowlists (Maps/Places only) and the project
quotas above. Canary and production browser keys remain origin-restricted.
An empty `gcp.environments[local].browserReferrers` list causes
`infra/gcp/apply-billing-guardrails.ps1` to `--clear-restrictions` on
`aitripplanner-local-browser`, then re-apply the API-target allowlist. A JSON
edit does not take effect until that script runs.

Checked-in `config/environments/*.env` currently set both Places and Maps
application flags to on. Hosted Bicep parameters pass the same flags into
Container Apps.

#### Emergency no-deployment control

`disable` updates the checked-in profile and immediately disables the relevant
GCP services. The Service Usage change stops new calls regardless of the
application flag, key, or currently running Container Apps revision. It does not
deploy or restart the application:

```powershell
# Windows
scripts\win\user\google\Google-Places-Control.cmd disable prod

# macOS
./scripts/mac/user/google/Google-Places-Control.command disable prod
```

Maps has the parallel owner command:

```powershell
# Windows
scripts\win\user\google\Google-Maps-Control.cmd disable all

# macOS
./scripts/mac/user/google/Google-Maps-Control.command disable all
```

Use `status all` for a read-only desired/cloud comparison and `apply all` to
repair cloud drift from the profiles. `on`/`off` are aliases for
`enable`/`disable`. Enabling is spend-bearing and requires the final argument
`APPROVE_GOOGLE_PLACES_SPEND` or `APPROVE_GOOGLE_MAPS_SPEND`, respectively.

Changing Service Usage is sufficient for an emergency off. A local process must
restart to consume a profile change. A hosted runtime must be deployed to create
a revision with the new flag; control scripts never perform that deployment.
Production deployment remains a separate owner-approved operation.

### 2026-08-27 incident evidence

Google Service Runtime `api/request_count` gives the following daily aligned
request buckets. These are measured requests, not billing estimates:

| Project | Bucket ending | Places requests |
| --- | --- | ---: |
| production | 2026-08-24 | 5,854 |
| local | 2026-08-25 | 140 |
| production | 2026-08-25 | 15,111 |
| local | 2026-08-26 | 128 |
| production | 2026-08-26 | 1,768 |
| local | 2026-08-27 | 14,847 |
| production | 2026-08-27 | 158 |
| production | 2026-08-28 | 45 |
| canary | entire comparison window | 0 |

The local spike ran from approximately 13:00Z through 16:00Z on 27 August.
All 14,847 requests were `Places.SearchText` through one local API credential;
14,846 returned HTTP 200 and one returned HTTP 500. The retry change made that
evening could therefore account for at most one additional request and was not
the spike's cause.

The direct cause was unbounded cold-cache enrichment across live sandbox and
evaluation runs. At 18:35 IST the audit launcher began importing the primary
Places key into sandbox processes; at 18:46 IST every sandbox run began copying
the complete primary `.env`. The trip view then synchronously prefetched every
gallery item and scheduled whole-trip and destination-guide warming. Each lane
had an isolated cache, so identical places were cold again in every concurrent
lane. The incident coincided with repeated audit-fix integration activity over
314 corpus trips. The billing snapshot showed 14,920 Text Search units, or 47.5
per corpus trip; Service Runtime independently records 14,847 local calls in
the spike. Google does not retain this application's process or run ID, so the
remaining 73-unit difference and an exact per-lane allocation cannot be proven
retrospectively.

The incident-time field mask included `editorialSummary`, selecting Text Search
Enterprise + Atmosphere rather than a cheap ID-only search. Earlier production
traffic had already consumed the billing account's pooled monthly allowance,
so the local burst arrived mostly or entirely in the paid tier. At the documented
India catalog rate of USD 12 per 1,000 calls, 14,847 calls are approximately USD
178.16 before allowance, credits, tax, and currency conversion. This is a catalog
estimate, not the billed amount. A billing report moving from roughly INR 6,000
to INR 11,000 and then INR 17,000 without corresponding new request metrics is
consistent with delayed usage ingestion and credit allocation; the finalized
billing export or invoice remains authoritative.

No continuing caller was observed after the shutdown check: local and canary
had no 28 August requests, production's final point ended at 08:46:51Z, and no
local corpus, validation, or pytest process was running. Service Usage and the
checked-in application gate are now disabled in all environments. Routes,
Static Maps, and browser Maps are separate services and were not changed.

## Verify

```bash
gcloud billing budgets list --billing-account="$BA" \
  --format="table(displayName,amount.specifiedAmount.units,budgetFilter.projects.list())"
# While shutoffEnabled=false this must return no rows.
gcloud functions list --gen2 --regions=asia-south1 --project="$OPS_PROJECT" \
  --filter="name:billing-shutoff"
gcloud quotas preferences list --project=<project> \
  --format="table(service,quotaId,quotaConfig.preferredValue,quotaConfig.grantedValue)"
```

When armed, additionally verify the function is active and the reported Eventarc
trigger identity has `roles/run.invoker` on its Cloud Run service.

## Recover after a shutoff

The function detaches billing from every project, so everything stops at once
and nothing re-enables itself. Recovery is deliberately manual:

1. Find the cause in Cloud Billing reports before restoring anything.
2. Re-link each project: `gcloud beta billing projects link <project> --billing-account="$BA"`.
3. Confirm the quota that leaked is tightened, otherwise the same spend repeats.

Re-linking restores billing but does not undo the spend that triggered it.

## Provisioning drift

Projects created through the Maps Platform console wizard get the **legacy** API
bundle (`places-backend`, `directions-backend`, `distance-matrix-backend`,
`geocoding-backend`, plus the mobile and embed SDKs). Projects created by hand
get only what you enable. That is how this account ended up with prod missing
`places.googleapis.com` while local and canary had it, despite canary otherwise
tracking prod closely.

Project provisioning is not covered by any deployment gate, so it drifts
silently and surfaces later as environment-only API failures. Compare enabled
services across environments whenever one environment alone misbehaves:

```bash
for p in $ENV_PROJECTS; do
  echo "=== $p ==="
  gcloud services list --enabled --project="$p" --format="value(config.name)" \
    | grep -Ei "places|maps|routes|geocod|static"
done
```
