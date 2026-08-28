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
| `tripplanner-local-2000inr` | 100 INR | local project | 50 / 80 / 100% |
| `tripplanner-canary-2000inr` | 100 INR | canary project | 50 / 80 / 100% |
| `tripplanner-prod-2000inr` | 500 INR | prod project | 50 / 80 / 100% |
| `tripplanner-global-8000inr` | 1,000 INR | whole billing account | 50 / 80 / 90 / 100% → Pub/Sub |

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

Places limits are sized for observation mode. Local and canary are disabled and
also pinned to one request as defense in depth. Production supports roughly two
cold trips per day at the incident's observed 47.5 Text Searches per trip:

| Quota | local | canary | prod |
| --- | --- | --- | --- |
| `SearchTextRequestPerDayPerProject` | 1 | 1 | 100 |
| `SearchTextRequestPerMinutePerProject` | 1 | 1 | 30 |
| `GetPlaceRequestPerDayPerProject` | 1 | 1 | 100 |
| `GetPlaceRequestPerMinutePerProject` | 1 | 1 | 30 |
| `SearchNearbyRequestPerDayPerProject` | 1 | 1 | 20 |
| `AutocompletePlacesRequestPerDayPerProject` | 1 | 1 | 50 |
| `GetPhotoMediaRequestPerDayPerProject` | 1 | 1 | 200 |
| `ComputeRoutesRequestsPerDay`, `ComputeRouteMatrixCellsPerDay` | 6,000 | 1,000 | 1,000 |
| `BillableDefaultPerDayPerProject` (Static Maps) | 6,000 | 1,000 | 1,000 |

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

The policy watches `serviceruntime.googleapis.com/quota/exceeded` on resource
type `consumer_quota`, aligned with `ALIGN_COUNT_TRUE` over five minutes and
grouped by `metric.label.quota_metric`, so the mail names the limit that broke.

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

At roughly 58 Places calls per trip on the rich masks in
[google_places.py](../../src/tripplanner/tools/google_places.py), a generated
trip costs about **USD 0.52 (about INR 46)** in Maps calls alone. Budget
arithmetic follows directly: a 1,000 INR monthly alert amount is only about 22
such trips. Corpus runs in the hundreds of trips per day are only
affordable after moving grounding lookups to IDs-only masks.

### Production-only Places gate

Google Places is intentionally enabled only in the production GCP project.
Local and canary keep `places.googleapis.com` disabled at the Google Service
Usage layer. `placesEnabled` in
[`infra/billing-guardrails.json`](../../infra/billing-guardrails.json) is the
central owner-facing desired state for that cloud control. The application adds
a second, fail-closed gate:

```dotenv
ENABLE_GOOGLE_PLACES=0
GOOGLE_PLACES_API_KEY=
```

Both values are required before the application makes a Places request.
`.env`, `.env.canary`, and `.env.prod` are the owner-facing application runtime
files; they contain non-secret switches as well as secret values. `.env.example`
is their committed schema and safe defaults. The current files set local and
canary off and production on. Hosted Bicep parameters enforce the same policy,
while the key remains a secret input. Google Routes and browser Maps have
separate runtime paths and are not disabled by the Places switch.

#### Emergency no-deployment control

Disabling the API in Google Service Usage stops new Places calls regardless of
the application flag, key, or currently running Container Apps revision. It does
not deploy or restart the application:

```powershell
# Windows
scripts\win\user\Google-Places-Control.cmd disable prod

# macOS
./scripts/mac/user/Google-Places-Control.command disable prod
```

Read all current states with `status all`. An explicit `enable` is spend-bearing
and therefore requires the final argument `APPROVE_GOOGLE_PLACES_SPEND`.
An immediate enable/disable is an override; for durable policy, first edit
`placesEnabled` in the central JSON and run:

```powershell
pwsh -File infra/gcp/set-google-places-access.ps1 `
  apply all APPROVE_GOOGLE_PLACES_SPEND
```

Changing only Service Usage is sufficient for an emergency **off**. Turning an
environment **on** still requires all three independent gates: cloud Service
Usage enabled, `ENABLE_GOOGLE_PLACES=1`, and a valid Places key. A hosted runtime
flag change creates a Container Apps revision; it is not an in-place toggle.

The 2026-08-27 local incident recorded 14,920 Text Search calls while 314 corpus
trips were under audit-fix/evaluation activity: **47.5 Text Searches per trip**.
That is an observed cold, isolated-sandbox-cache amplification figure, not the
deterministic audit's intended behavior and not an unavoidable production trip
cost. Pytest blocks outbound traffic and the final audit renderer uses stored
place facts. The incident occurred because concurrent live sandbox/evaluation
enrichment had the copied local key, separate per-lane caches, and automatic
place warming; Google monitoring did not preserve a process or run ID that
would identify each historical request more narrowly.

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
