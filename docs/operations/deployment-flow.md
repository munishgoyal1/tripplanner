# Canary and Production Deployment Flow

This is the developer runbook for building, testing, promoting, and rolling
back the hosted web application. The short version is two commands, separated
by validation and an explicit production decision:

```powershell
# Build one immutable image, deploy it to canary, and run read-only smoke.
.\infra\deploy-canary.ps1

# After deep smoke, manual validation, and bake: promote the same SHA.
.\infra\deploy-prod.ps1
```

Production is deliberately not part of the canary command. The approval phrase
`APPROVE_PROD_DEPLOYMENT` is a required human gate.

## Prerequisites

Run the developer-machine setup once:

```powershell
.\scripts\setup-dev-machine.ps1
```

It installs or verifies Git, Python 3.11, Node.js LTS, Docker Desktop, and the
Azure CLI; restores Python and frontend dependencies; creates `.env` only when
missing; and builds the frontend. Add `-IncludeMobile` to restore Expo packages.
It does not start servers, authenticate accounts, create Azure resources, or
write secrets.

Before releasing, authenticate manually:

```powershell
az login
gh auth refresh -h github.com -s write:packages
```

The image publisher establishes a fresh GHCR login before building. It uses
`GHCR_TOKEN`, `CR_PAT`, or `GITHUB_TOKEN` when set; otherwise it uses the active
GitHub CLI token only when that token belongs to `munishgoyal1` and includes
`write:packages`. Provider and OAuth settings remain in the uncommitted `.env`;
hosted environment-owned Azure OpenAI keys and OAuth callback bases are resolved
by the deployment scripts.

## Artifact and Resource Ownership

| Item | Authoritative location |
| --- | --- |
| Source and release commit | GitHub private repository |
| Container image | `ghcr.io/munishgoyal1/tripplanner:<short-sha>` |
| Convenience image pointer | `ghcr.io/munishgoyal1/tripplanner:latest` |
| Image push history | Local ignored `logs/image-pushes.log` in the primary checkout |
| Canary deployment history | Local ignored `logs/deployments-canary.log` in the primary checkout |
| Production/rollback history | Local ignored `logs/deployments-prod.log` in the primary checkout |
| Last run of any script | Local ignored `logs/last-run/<script>.log` in the primary checkout, overwritten per run |
| App infrastructure | `infra/main.bicep` plus environment `.bicepparam` |
| Production DNS | Namecheap records for `aitripplanner.co` and `www` |
| Production TLS/domain bindings | Existing Azure managed certificates declared by `infra/main.bicep` |
| Shared data infrastructure | `infra/data-stack.bicep`, `infra/data.bicep`, modules |
| Backup/recovery procedure | `docs/operations/backup-recovery.md` plus ignored `logs/recovery/` evidence |
| Canary data | Shared Cosmos account, `tripplanner-canary` database |
| Production data | Shared Cosmos account, `tripplanner-prod` database |
| Runtime revisions/logs | Azure Container Apps and Log Analytics |
| Production failure alert | `infra/main.bicep`, production parameters, Azure Monitor |

The SHA tag is the promotion identity. `latest` is pushed for convenience but
must not be used as production evidence because it can move between canary and
production. Local deployment logs are operational aids, not durable artifacts;
Git history, GHCR, Azure revisions, and Log Analytics are the durable record.

## Release Flow

### 1. Validate the source milestone

Run tests and builds appropriate to the changed surface. Infrastructure changes
also require Bicep validation and Azure what-if. Commit and push before building
so the image's SHA identifies its contents.

### 2. Deploy canary with one command

```powershell
.\infra\deploy-canary.ps1
```

The script:

1. Resolves the current Git short SHA.
2. Validates Bicep, the shared Cosmos account/database, Azure OpenAI access, and
   the environment-owned OAuth callback.
3. Runs Azure what-if and blocks any delete operation.
4. Builds one Docker image and pushes the SHA plus `latest` to GHCR. The manual
  GitHub Actions workflow may perform this image publication only; it has no
  Azure credentials or deployment step.
5. Applies `main.bicep` and canary parameters.
6. Updates the Container App to the immutable SHA image.
7. Runs the public read-only hosted smoke suite.
8. Prints and logs the tested image tag.

To redeploy an already-pushed artifact or apply infrastructure changes without
building a new image:

```powershell
.\infra\deploy-canary.ps1 -NoBuild -ImageTag <sha>
```

### 3. Run the deep canary gate

```powershell
.\infra\smoke-hosted.ps1 -Environment canary -Deep
```

Deep smoke adds one isolated proposal-only Azure OpenAI turn and expects a PONG
response. It proves model endpoint, deployment, API version, key, and chat path.

### 4. Validate and bake canary

Manually verify Google sign-in, a representative planning turn, itinerary/map/
details synchronization, saved-trip reload, and every changed workflow. Review
Container App errors, restarts, latency, and throttling during a risk-based bake:

- 30-60 minutes for a narrow personal-app change.
- Several hours for shared backend, auth, provider, or configuration changes.
- 24 hours for migrations or a high-risk release.

Record the SHA, smoke results, manual checks, bake duration, observed errors,
known risks, and current production rollback revision before approval.
For a high-risk data change, attach a passing isolated recovery-drill report
from [Backup and Recovery Drill](backup-recovery.md); a plan without evidence
does not satisfy the production checklist.

### 5. Promote the exact image to production

```powershell
.\infra\deploy-prod.ps1
```

The script resolves the current Git SHA by default, checks that the exact image
is currently deployed to canary, and checks the primary checkout's successful
canary history for smoke evidence. If either check is missing, it tells the owner
why and runs the canary deployment and read-only smoke before displaying the
production readiness checklist. An explicit `-ImageTag <sha>` replays that
immutable artifact through the same gate without rebuilding it. `-DryRun` reports
an unmet canary gate without changing canary. `-Build` is rejected because a
production-side rebuild would invalidate canary evidence.

After the canary gate passes, the script requires the exact interactive phrase
`APPROVE_PROD_DEPLOYMENT`, applies production Bicep parameters, blocks
infrastructure deletes through what-if, updates production to that SHA image,
runs read-only hosted smoke, and logs the approver and result.

Production parameters preserve `aitripplanner.co` and `www.aitripplanner.co`
with Azure-managed TLS and set `OAUTH_REDIRECT_BASE` to
`https://aitripplanner.co/api`. The generated Container Apps hostname remains
enabled as rollback access. A production what-if must show no certificate or
custom-domain replacement before approval.

### 6. Monitor and roll back when needed

Perform a short production critical-flow check and monitor for at least 15-30
minutes. Run the release-observation and tool-health KQL from
[Production Observability and SLOs](operations-slos.md). A low-volume window is
insufficient evidence for the rolling SLO, so release judgment combines smoke,
one representative accepted chat operation, and the observed error stream. If
a critical smoke or user workflow fails:

```powershell
.\infra\rollback-prod.ps1
```

The rollback command requires `ROLLBACK` and activates the prior Container Apps
revision. It does not undo Cosmos writes or schema/data migrations.

The production Bicep deployment also owns the failure Action Group and
scheduled-query alert. Verify its first-delivery test after an approved
deployment. During canary bake, run
`.\scripts\analyze-errors.ps1 -Environment canary -Hours 24`; canary produces a
local report and never emails the production recipient.

## Hosted Smoke Suite

Both deployment scripts run the read-only suite through the public URL. It uses
an isolated environment-specific identity and no provider writes. The checks are:

1. React shell and every referenced JavaScript/stylesheet asset are served.
2. Health reports `status=ok`.
3. OpenAPI contains the critical chat, trip, preference, auth, and health routes.
4. Google OAuth is enabled, callback ownership matches the target environment,
   and login emits a Google redirect with a secure state cookie.
5. Maps browser configuration is enabled.
6. Anonymous session behavior is correct.
7. Cosmos-backed trips, preferences, usage, trip view, chat history, itinerary,
   map, tool metrics, and guest summary match their response contracts.

Run read-only smoke independently:

```powershell
.\infra\smoke-hosted.ps1 -Environment canary
.\infra\smoke-hosted.ps1 -Environment production
```

Deep production smoke writes one isolated chat turn and is blocked unless both
the production target and write acknowledgement are explicit:

```powershell
.\infra\smoke-hosted.ps1 -Environment production -Deep -AllowProductionWrites
```

Read-only smoke is a deterministic deployment gate, not a replacement for
provider checks or manual workflow validation. A smoke failure stops the script
but does not automatically activate the prior revision; investigate canary or
run the guarded production rollback immediately.

## Infrastructure Changes

Azure Portal edits are not authoritative. Every infrastructure change must be
captured in Bicep and the owning idempotent script in the same commit:

- App, identity, environment, configuration, and secret wiring:
  `main.bicep`, environment parameters, and both deployment scripts.
- Production custom domains and managed certificates: `main.bicep` and
  `prod.bicepparam`; Namecheap remains authoritative for the required A, CNAME,
  and `asuid` verification records.
- Shared Cosmos account, databases, containers, throughput, or TTL:
  `data-stack.bicep`, `data.bicep`, modules, and `deploy-data.ps1`.
- Fresh-subscription orchestration: `bootstrap-environments.ps1`.
- Azure OpenAI provisioning: `provision-aoai.ps1`.

Hosted secrets are also environment-owned. Canary requires ignored
`.env.canary`; production requires ignored `.env.prod`; local development uses
ignored `.env`. The deployment scripts refuse to fall back to local `.env`, so
an environment's OAuth and Maps credentials cannot be injected into another
environment by a later release.

Optional provider settings follow the same boundary. Set `LITEAPI_*`,
`VIATOR_*`, `DUFFEL_API_KEY`, `GOOGLE_PLACES_API_KEY`, and
`OPENROUTESERVICE_*` in the target environment file only. The environment
parameter files pass them into `main.bicep`; nonblank API keys become Container
Apps secrets and blank keys are omitted, leaving that provider inactive. Never
copy local provider values into canary or production automatically.

Validate shared-data changes separately and obtain approval before applying
them. Then deploy canary through the normal flow, validate and bake, and promote
the same application image to production. Never allow canary and production to
share a database or import local `.env` values for environment-owned settings.
