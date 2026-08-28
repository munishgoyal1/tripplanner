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

The application now caps a planning/view scope at three Text Search calls, one
review-details call, and three photo-media calls, with one photo maximum per
place. Agent discovery results seed the structured UI cache, routine metadata
omits `editorialSummary`, and unfocused views never fetch reviews. At global
first-paid-tier list prices, the configured cold ceiling is roughly USD 0.142
(about INR 12.50 at the planning assumption of INR 88/USD) before cache reuse.
This is a catalog estimate, not billed cost; provider billing exports remain
authoritative, and Azure OpenAI/Routes remain outside this figure.

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

The browser key is still a referrer-restricted credential for Maps JavaScript
and browser Places. The server key still authenticates server-side Places,
Routes, and Static Maps. Flags own capabilities rather than credentials because
Service Usage is project-wide, not key-specific. When Maps is on and Places is
off, the SPA loads the base map without the Places JavaScript library.

All three checked-in environments currently set both capabilities to off.
Hosted Bicep parameters pass the same flags into Container Apps.

#### Emergency no-deployment control

`disable` updates the checked-in profile and immediately disables the relevant
GCP services. The Service Usage change stops new calls regardless of the
application flag, key, or currently running Container Apps revision. It does not
deploy or restart the application:

```powershell
# Windows
scripts\win\user\Google-Places-Control.cmd disable prod

# macOS
./scripts/mac/user/Google-Places-Control.command disable prod
```

Maps has the parallel owner command:

```powershell
# Windows
scripts\win\user\Google-Maps-Control.cmd disable all

# macOS
./scripts/mac/user/Google-Maps-Control.command disable all
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
