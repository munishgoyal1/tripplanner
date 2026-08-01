# Azure Deployment Plan

Status: Validated
Last updated: 2026-07-31

## 1. Objective And Constraints

Modernize tripplanner's data infrastructure so local development is free and
isolated, while canary and production share the subscription's Cosmos DB
lifetime free-tier allowance without sharing application data.

Constraints:

- Keep monthly Azure spend below the INR 10,000 credit.
- Preserve all production and canary data during migration.
- Preserve the Azure OpenAI resource in `rg-tripplanner-local`; never delete
  that resource group as part of Cosmos cleanup.
- Keep canary and production in separate Cosmos databases.
- Keep Container Apps at `minReplicas=0` and `maxReplicas=1`.
- Keep image hosting on GHCR; the two unused Basic ACRs are cleanup candidates.
- Do not deploy production or delete resources without explicit approval.
- A fresh clone must be bootstrappable from repository-owned Bicep and
  PowerShell scripts on any machine with Docker, PowerShell, Python, and Azure
  CLI. No IDE-specific configuration is required.

## 2. Measured Current State

The subscription currently has three independently billed Cosmos DB accounts:
local, canary, and production. Each account has one database with fixed shared
throughput of 1,000 RU/s. The Bicep template creates a new account per app
environment and hardcodes database throughput at 1,000 RU/s.

All three deployed accounts report `enableFreeTier=false`, even though the
parameter file requests free tier. Free tier cannot be enabled on an existing
account. The canary and production databases recorded effectively no traffic
in the measured period but still incurred fixed provisioned-throughput cost.

Measured 30-day costs:

| Cost source | Approximate cost |
| --- | ---: |
| Local Cosmos DB | INR 4,732 |
| Canary Cosmos DB | INR 4,732 |
| Production Cosmos DB | INR 4,732 |
| Two unused Basic Azure Container Registries | INR 822 |
| Other resources | INR 51 |
| Total | INR 15,069 |

The live Container Apps already use public GHCR images and scale to zero, so
Container Apps environments are not the material cost driver. The fixed Cosmos
throughput and unused ACRs are.

## 3. Target Architecture

### Local development

- Default to the official Linux-based Azure Cosmos DB Emulator vNext image
  through repository-owned Docker Compose.
- Keep the shared Azure data account's isolated `tripplanner-local` database as
  an explicit `COSMOS_DEV_BACKEND=azure` option only.
- Use the NoSQL gateway endpoint at `https://localhost:8081`, readiness endpoint
  at `http://localhost:8080/ready`, and Data Explorer at
  `https://localhost:1234`.
- Persist emulator data in a named Docker volume that is ignored by Git.
- Configure the Python SDK for gateway mode and disable certificate validation
  only when the endpoint is explicitly localhost/loopback and the local
  emulator flag is enabled. Hosted endpoints always retain TLS validation.
- Make `scripts/dev/dev-spa.ps1` resolve Azure account credentials at runtime and
  verify `tripplanner-local` exists in Azure mode; never persist credentials.
  Emulator mode starts/checks Docker and explicitly sets the loopback endpoint,
  well-known emulator key, and `tripplanner-local` database.
- Keep an explicit opt-in switch for using canary data, with a warning and no
  silent fallback from a failed emulator to local JSON or cloud Cosmos.

### Hosted

- Create one new Cosmos DB for NoSQL account in a dedicated
  `rg-tripplanner-data` resource group with lifetime free tier enabled.
- Create three databases in that account:
  - `tripplanner-local`: fixed shared throughput of 400 RU/s.
  - `tripplanner-canary`: fixed shared throughput of 400 RU/s.
  - `tripplanner-prod`: fixed shared throughput of 400 RU/s.
- The combined 1,200 RU/s exceeds the account's 1,000 RU/s lifetime free-tier
  provisioned-throughput allowance by 200 RU/s. This is an intentional tradeoff
  if Azure local persistence is deployed. Until then, the deployed canary and
  production databases remain at 800 RU/s total.
- Provision the same containers in each database with partition key `/user_id`:
  `users`, `trips`, `places_cache`, `shared_trips`, `tool_cache`, and
  `audit_events`. Configure `audit_events` default TTL to 7,776,000 seconds.
- Canary and production Container Apps receive the same account endpoint/key
  but different `COSMOS_DATABASE` values. Database separation prevents
  cross-environment reads even when user IDs and document IDs match.
- App environment Bicep references the shared account as an existing resource;
  it no longer creates or owns a Cosmos account or database.

### Why 400 RU/s

400 RU/s is the minimum fixed provisioned throughput for a shared-throughput
database; 200 RU/s is not a valid configuration. It cannot be reduced further
in provisioned mode. Serverless is an
account-level capability and cannot be mixed into this provisioned-throughput
account. Three isolated databases therefore require 1,200 RU/s total.

## 4. Repository Changes

### Infrastructure as code

- Add a subscription/resource-group orchestration template for the dedicated
  data resource group.
- Add a reusable Cosmos data-plane Bicep module that creates the free-tier
  account, both 400-RU/s databases, and their containers.
- Refactor the app-environment Bicep template to accept the shared Cosmos
  account name/resource group and environment-specific database name, reference
  that account as existing, and inject its endpoint/key into Container Apps.
- Add explicit canary and production parameter files. Remove the misleading
  per-environment `enableCosmosFreeTier` switch.
- Preserve existing secret injection behavior initially. Managed identity and
  Cosmos data-plane RBAC are a separate security change and are not required to
  realize this cost migration.

### Local development workflow

- Add a Docker Compose definition for the official emulator image with HTTPS,
  health check, Data Explorer, and persistent storage.
- Add a local bootstrap/check script that starts the emulator, waits for
  readiness, and verifies database access without printing credentials.
- Update `scripts/dev/dev-spa.ps1` so local development defaults to the emulator and
  cloud data remains explicit opt-in.
- Add emulator-aware SDK configuration and focused tests proving TLS bypass is
  loopback-only.

### Migration and operations

- Add an idempotent migration script that copies all documents container by
  container using the Cosmos data plane, preserving `id`, `user_id`, document
  bodies, and audit TTL fields where present.
- The migration script takes source and target account/database arguments,
  obtains credentials from Azure CLI at runtime, never stores keys in files,
  and supports `--dry-run` and `--verify-only` modes.
- Verification compares document counts per container and point-reads every
  copied `(user_id, id)` pair. Any mismatch blocks cutover.
- Update canary/prod deployment scripts to deploy app infrastructure against
  the shared data account and retain the existing production approval phrase.
- Add a cleanup script that inventories, confirms, and separately deletes old
  Cosmos accounts and unused ACRs. It must refuse to delete an account still
  referenced by a Container App.
- Replace the cloud-provisioning `provision-local-cosmos.ps1` workflow with the
  emulator workflow; retain a clearly named legacy migration helper only while
  old local data is being exported.

### Documentation

- Update `README.md`, `infra/README.md`, the canonical
  `docs/operations/deployment-flow.md`, `docs/CODEMAP.md`,
  `.github/copilot-instructions.md`, and the requirements baseline
  to describe the new ownership boundaries, commands, cost model, and gates.

## 5. Migration And Rollback

### Safety rules

- Resource creation and data copy are non-destructive.
- Cut over canary before production.
- Do not write to source and target concurrently during each final copy. Scale
  the relevant Container App to zero or otherwise place it in a short
  maintenance window for the final delta and verification.
- Keep each old account and database unchanged after cutover for a minimum
  seven-day rollback window.
- Never delete `rg-tripplanner-local`; only the obsolete Cosmos account within
  it becomes eligible for deletion after local data disposition is confirmed.

### Cutover sequence per environment

1. Reduce the old database from 1,000 RU/s to 400 RU/s for immediate savings.
2. Stop writes for the environment.
3. Copy all source documents to the matching target database.
4. Verify every container and document.
5. Deploy the Container App configuration with the new endpoint/database.
6. Run smoke tests for identity, preferences, saved trips, active trip, chat,
   share links, usage limits, caches, and audit events.
7. Resume traffic and monitor failures, 429s, normalized RU consumption, and
   request volume.

### Rollback

If validation or monitoring fails, stop writes, point the Container App back to
the old account/database using the retained deployment parameters, redeploy,
and resume traffic. Any writes accepted by the new database before rollback
must be copied back and verified first. Old resources remain available until
the rollback window and explicit cleanup approval are complete.

## 6. Planned Execution Milestones

1. **Repository implementation (complete):** IaC modules/parameters, emulator
  workflow, SDK configuration, migration/cleanup scripts, tests, and
  documentation are implemented. Final validation and commit/push are pending.
2. **Azure local database (prepared, not deployed):** validate and deploy the
  third `tripplanner-local` database and six containers only after explicit
  deployment approval. Confirm the expected 200-RU/s billable overage.
3. **Azure preflight:** Confirm subscription context, free-tier eligibility,
   provider registration, naming availability, permissions, Bicep validation,
   and `what-if`. Record evidence in this plan. No resource mutation.
4. **Immediate cost floor:** With explicit Azure-change approval, lower all old
   Cosmos databases to 400 RU/s. Verify throughput after update.
5. **Shared data plane:** Create `rg-tripplanner-data`, the new eligible
   free-tier account, databases, and containers. Confirm `enableFreeTier=true`
   and total provisioned throughput of 800 RU/s.
6. **Canary migration:** Copy, verify, cut over, smoke test, and monitor canary.
   Commit/push any operational documentation updates.
7. **Production migration:** Require `APPROVE_PROD_DEPLOYMENT`, take a final
   copy, verify, cut over, smoke test, and monitor production.
8. **Deferred destructive cleanup:** After at least seven stable days, show the
   exact old Cosmos accounts and ACRs with dependency checks and projected
   savings. Delete only after a separate explicit approval. Preserve all other
   resources and resource groups.

## 7. Validation Gates

### Repository validation

- Bicep build for every template and module.
- Bicep parameter build for every environment file.
- PowerShell parser validation for all changed scripts.
- Focused Cosmos storage/emulator and migration tests.
- Full backend pytest suite.
- Frontend tests/build only if frontend files change.
- Confirm no credentials, generated emulator data, migration exports, or user
  documents are tracked by Git.

Repository proof recorded on 2026-07-24:

- Shared data, app, module, and parameter Bicep compilation: passing.
- Changed PowerShell parser validation: passing.
- Focused storage/emulator/migration tests: 10 passing, including remaining
  audit TTL preservation.
- Full backend suite: 486 passing; one environment-only failure because the
  installed `websockets` distribution reports `Version=None` metadata.
- Ruff, Docker Compose config, PowerShell parsing, whitespace, stale-reference,
  and credential-pattern checks: passing.

### Azure preflight validation

- Active subscription and tenant match the intended account.
- Exactly zero existing free-tier Cosmos accounts, or otherwise stop and revise
  this plan before creation.
- `Microsoft.DocumentDB` and `Microsoft.App` providers are registered.
- Account name is globally available in East US 2.
- Deployment identity can create resource groups/resources and read Cosmos keys.
- `az deployment ... validate` succeeds.
- `what-if` shows only intended additions/updates and no deletion of live data.

### Post-deployment validation

- New account reports lifetime free tier enabled.
- Both databases report 400 RU/s shared throughput.
- All expected containers and partition keys exist; audit TTL is correct.
- Migration verification reports zero missing, extra, or mismatched documents.
- Canary and production read their own database and fail the isolation check
  against the other environment.
- Container Apps still use GHCR, scale to zero, and pass API/UI smoke tests.
- Azure Monitor shows no sustained throttling or application errors.

## 8. Production Failure Alerting Increment

### Objective and measured baseline

Add actionable failure detection without creating a second telemetry pipeline.
The application already emits PII-safe JSON events to Container Apps stdout,
and each hosted environment already retains that stream in its own Log Analytics
workspace for 30 days. No Application Insights resource or SDK is required.

Production currently has no Azure Monitor scheduled-query rule or Action Group.
Local development prints logs to its owning console, and canary has queryable Log
Analytics data but no repository-owned periodic diagnostic report.

### Proposed architecture

- Extend `infra/main.bicep` with an opt-in failure-alert contract. The default is
  disabled, so local and canary deployments do not create an Action Group or
  scheduled-query alert.
- Enable the contract only in `infra/prod.bicepparam`, with the production alert
  recipient set to `munishgoyal1@gmail.com`.
- Create one production Action Group email receiver and one Azure Monitor
  scheduled-query rule scoped to the existing production Log Analytics workspace.
- Evaluate every five minutes over a five-minute window and alert when at least
  one matching failure is present. Detect structured `chat_operation` errors,
  structured `tool_call` errors, and ordinary JSON log records at `ERROR` or
  `CRITICAL` level. Grouping and suppression should avoid one email per log line.
- Keep all alert payloads on the existing redacted operational stream. Never
  query the restricted `audit_events` container or include raw user content.
- Add a repository-owned diagnostic script that can analyze the same failure
  classes for canary through Azure CLI/Log Analytics and for local development
  from captured JSON log files. It writes a redacted Markdown report under an
  ignored `logs/diagnostics/` path and exits nonzero when failures are found, so
  it can be run manually or from Windows Task Scheduler without sending email.
- Keep diagnostic analysis read-only. The script may classify failures and print
  next-step KQL, but it must not mutate Azure resources or application data.

### Repository changes

- `infra/main.bicep` and `infra/prod.bicepparam`: production-only Action Group
  and scheduled-query alert.
- `scripts/analyze-errors.ps1`: shared local/canary diagnostic report command.
- Focused tests for environment gating, query coverage, local JSON parsing,
  report redaction, and failure exit behavior.
- `docs/operations/operations-slos.md`, deployment documentation, `docs/CODEMAP.md`,
  requirements/current-state documentation, and infrastructure ownership docs.

### Execution and approval boundaries

1. Implement and validate repository changes only after owner approval of this
   plan. Commit and push the worker branch; do not deploy.
2. Deploy to canary only through the normal guarded canary flow. Because alerting
   is disabled there, this validates template compatibility without email.
3. Inspect a canary diagnostic report and confirm that synthetic/local fixture
   failures are classified correctly before production promotion.
4. Production Action Group and alert creation require the existing interactive
   `APPROVE_PROD_DEPLOYMENT` gate. The production `what-if` output must show only
   the intended monitor resources and no deletions.
5. After approved deployment, verify Action Group delivery with an Azure Monitor
   test notification and verify the query against a controlled PII-safe failure
   event. Do not manufacture a user-facing production outage for this test.

### Validation gates

- Bicep build for `infra/main.bicep` and both hosted parameter files.
- Bicep diagnostics are clean after every infrastructure edit.
- PowerShell parser validation and focused analyzer tests pass.
- Production parameters enable alerting; canary parameters and defaults leave it
  disabled and require no recipient.
- The query matches chat, tool, and ordinary error records while excluding normal
  completed, replayed, capped, and successful tool events.
- No email address, credentials, raw principal, prompt, or audit content appears
  in generated diagnostic reports beyond the explicitly configured Action Group
  recipient in production IaC.
- Production deployment remains unexecuted until explicit approval at the
  existing production gate.
- Cost analysis no longer reports paid hosted provisioned-throughput charges
  after billing data catches up.

## 9. Validation Proof

Production deployment repair validation completed on 2026-07-31:

- The first approved production attempt failed in ARM before the image update;
  Azure rejected `autoMitigate: true` combined with `muteActionsDuration` on the
  scheduled-query alert. Production remained on its prior revision and image.
- The stateful alert retains automatic mitigation and no longer declares the
  incompatible stateless action-suppression duration.
- `infra/main.bicep` compiled with no diagnostics. Focused failure-alert and
  release-workflow tests passed (7 tests), and both deployment scripts passed
  PowerShell parser validation.
- Production `az deployment group validate` returned `Succeeded` for the
  corrected template. Production what-if returned one update and zero deletes.
- Both guarded deployment scripts now preserve Azure CLI stderr and check the
  native exit code before parsing JSON, so ARM failures surface their real error.
- The approved retry deployed production revision
  `prod-app-f3ddjudq2rdt4--0000014` on immutable image `10963d5`. Read-only smoke
  passed all nine checks through both the generated Container Apps hostname and
  `https://aitripplanner.co`; the smoke contract now validates the deployment-owned
  OAuth callback independently from the HTTP request hostname.
- Azure Monitor accepted a `logalertv2` test notification for the enabled
  production Action Group. Owner mailbox receipt remains to be confirmed.

Production failure alerting validation completed on 2026-07-30:

- `infra/main.bicep`, `infra/prod.bicepparam`, and
  `infra/canary.bicepparam` compiled with no diagnostics.
- Focused observability and error-analysis tests: 32 passed. Focused Ruff and
  changed PowerShell parser checks passed.
- Full backend suite: 636 passed with one existing Starlette deprecation warning.
- Production resource-group template validation returned `Succeeded` using the
  current deployed image and secrets loaded only into process memory.
- Production what-if was interrupted before returning a result. No deployment
  command ran and no Azure resource changed. A clean no-delete what-if remains
  required before this plan can move from `Ready for Validation` to `Validated`.

App release validation completed on 2026-07-28 for subscription
`2dd0a2f4-fc3a-4245-8e40-fadd0bbcbd5b`:

- Local and `origin/master` both resolved to source commit `07293c5` before
  recording this proof; the final release image must use the new commit SHA
  produced by this documentation update.
- `infra/main.bicep`, `infra/canary.bicepparam`, and `infra/prod.bicepparam`
  compiled successfully.
- Full backend suite: 540 passed. The corrupt local `websockets` metadata was
  repaired with the repository-compatible 14.2 wheel before rerunning.
- Frontend suite: 68 passed; TypeScript and Vite production build passed.
- Canary and production `az deployment group validate` commands passed.
- Canary and production `what-if` commands returned `Succeeded`, with only
  deploy/ignore operations and no resource deletions.
- The app uses anonymous pulls from public GHCR and key-based service access;
  no managed identity or Azure role assignments are declared by `main.bicep`,
  so no deployment-time RBAC propagation gate applies.
- Rollback baselines captured before deployment: canary revision
  `canary-app-zcebxnuakdwnu--0000014`; production revision
  `prod-app-f3ddjudq2rdt4--0000009`.

Validated at `2026-07-24T09:09:04Z` against subscription
`2dd0a2f4-fc3a-4245-8e40-fadd0bbcbd5b` and tenant
`d889d6d8-feaa-4837-937f-ddb9007ba8ef`:

- `az bicep build --file infra/data-stack.bicep --stdout`: passed.
- Azure context and provider preflight: intended subscription/tenant confirmed;
  `Microsoft.DocumentDB` and `Microsoft.App` registered.
- Lifetime free-tier preflight: zero existing free-tier Cosmos accounts.
- `az deployment sub validate`: passed for `infra/data-stack.bicep` and
  `infra/data.bicepparam`.
- `./infra/deploy-data.ps1 -DryRun`: 16 creations and no updates or deletions:
  one data resource group, one free-tier account, two 400-RU/s databases, and
  six `/user_id` containers per database. Audit TTL is 7,776,000 seconds.

## 10. Approval Gates

On 2026-07-24, the owner approved live Cosmos resource creation, throughput
changes, and canary migration after confirming the local emulator works. This
approval does not authorize production cutover or resource deletion.

Later gates:

1. Approve non-destructive Azure creation and old-database throughput reduction.
2. Approve canary maintenance window and cutover.
3. Enter `APPROVE_PROD_DEPLOYMENT` for production cutover.
4. Separately approve deletion of named old Cosmos accounts and ACRs after the
   rollback window.

## 11. Execution Record (2026-07-24)

Completed in one session after the owner explicitly approved all remaining
steps, including an immediate deletion that waives the 7-day rollback window:

- **Migration script fix:** `scripts/cosmos_copy.py` now enumerates source
  containers and skips any missing on the source (legacy canary/prod have five
  containers, not six — no `shared_trips`), so copies no longer fail.
- **Canary data copy:** legacy `canary-cosmos-zcebxnuakdwnu/tripplanner` → shared
  `tripplanner-data-qftmtl5pavmcu/tripplanner-canary`; 76 items copied and
  point-read verified (users 10, trips 7, places_cache 1, tool_cache 58,
  audit_events 0).
- **Prod data copy:** legacy `prod-cosmos-f3ddjudq2rdt4/tripplanner` → shared
  `tripplanner-prod`; 26 items copied and verified (users 4, trips 1,
  places_cache 1, tool_cache 20, audit_events 0).
- **Cutover (surgical, not full redeploy):** to avoid blanking API-key secrets
  from an incomplete local `.env`, both container apps were cut over by updating
  only the `cosmos-key` secret plus the `COSMOS_ENDPOINT` and `COSMOS_DATABASE`
  env vars. Canary → `tripplanner-canary`, prod → `tripplanner-prod`; both
  `GET /api/health` returned `{"status":"ok"}` on the new revision.
- **Legacy deletion:** owner accepted the loss of the rollback window and
  approved all three deletions. `localcosmos2cgsfp` and
  `canary-cosmos-zcebxnuakdwnu` were deleted. On 2026-07-26, direct inventory
  found the unused non-free-tier `prod-cosmos-f3ddjudq2rdt4` account still
  provisioning 400 RU/s; both apps were verified against the shared account
  before it was deleted. Final inventory contains only the free-tier
  `tripplanner-data-qftmtl5pavmcu` account with `tripplanner-canary` and
  `tripplanner-prod` at 400 RU/s each. Both app health endpoints returned `ok`.
- **Remaining obsolete-resource cleanup:** after explicit owner approval on
  2026-07-26, `canarytp32780` and `prodtp15831` were deleted after verifying
  both apps use GHCR and do not configure an ACR. The zero-deployment,
  unreferenced `foundry-trip-planner-resource/foundry-trip-planner` project and
  its parent AI Services account were also deleted. The deployed local,
  canary, and production OpenAI accounts were retained, as were canary
  Communication Services/Email because the canary app actively configures it.
  Final app health checks returned `ok`.
