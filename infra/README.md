# Infrastructure — Trip Planner on Azure

Cheapest viable footprint for global hosting:

| Resource | Purpose | Free tier? |
|---|---|---|
| Log Analytics workspace | Required by Container Apps | First 5 GB/mo free |
| Cosmos DB (NoSQL) | Shared account; isolated canary/prod databases | **1000 RU/s + 25 GB free** (one per subscription) |
| Container Apps environment | Hosting fabric | n/a (env itself is free) |
| Container App | React SPA + FastAPI agent | **180k vCPU-sec + 2M req/mo free**, scales to zero |

Estimated cost at low usage: well under your ₹10,000/mo Azure free credit.
Stays at ~₹0 when idle thanks to scale-to-zero.

## Environments & Naming

### Shared Data Plane
- Resource Group: `rg-tripplanner-data`
- Cosmos DB: one lifetime free-tier account
- Databases: `tripplanner-canary` and `tripplanner-prod`, 400 RU/s shared throughput each

### Canary (Testing — No Approval Gate)
- Resource Group: `rg-tripplanner-canary`
- Container App: `canary-app-*`
- Cosmos database: `tripplanner-canary` in the shared account
- **Use for:** Feature testing, bug fixes, infrastructure changes, email verification
- **Deployment:** `./infra/deploy-canary.ps1` (no approval required)

### Production (Live — Manual Approval Required)
- Resource Group: `rg-tripplanner-prod`
- Container App: `prod-app-*`
- Cosmos database: `tripplanner-prod` in the shared account
- **Use for:** Tested, verified releases only
- **Deployment:** `./infra/deploy-prod.ps1` (requires explicit approval: type `APPROVE_PROD_DEPLOYMENT`)

### Migration Path
Transition to standardized naming by redeploying canary first, then production after approval.

## Prerequisites

- Azure subscription with its one Cosmos DB lifetime free-tier slot available
- Azure CLI logged in (`az login`)
- Docker installed locally
- GitHub Container Registry account for container images

## Local files

- `data-stack.bicep` + `data.bicep` — shared data RG/account/databases
- `modules/cosmos-data.bicep` — reusable Cosmos account/database/container module
- `main.bicep` — app environment resources; references existing shared Cosmos
- `canary.bicepparam` / `prod.bicepparam` — isolated hosted database bindings
- `cosmos-emulator.compose.yml` — official local emulator with persistent volume
- `DEPLOYMENT_PROCESS.md` — detailed workflow, approval gates, and logging
- `deploy-canary.ps1` — deploy/test new changes (no approval)
- `deploy-prod.ps1` — promote to production (manual approval required)
- `rollback-prod.ps1` — revert to previous stable revision if issues occur
- `provision-aoai.ps1` — create/reuse Azure OpenAI account + deployment and print `.env` values
- `bootstrap-environments.ps1` — one-command canary+prod bootstrap for a fresh subscription
- `deploy-data.ps1` — validate/what-if/deploy the shared free-tier data plane
- `start-cosmos-emulator.ps1` — start or readiness-check local Cosmos
- `set-cosmos-throughput.ps1` — idempotently reduce an old database to 400 RU/s
- `cleanup-obsolete-resources.ps1` — dependency-checked, approval-gated cleanup

## Fresh Subscription Quick Start

```powershell
# 1) Build and push app image first
$Env:CR_PAT = "<github_personal_access_token>"
$Env:CR_PAT | docker login ghcr.io -u munishgoyal1 --password-stdin
docker build -t ghcr.io/munishgoyal1/tripplanner:v0.X.Y .
docker push ghcr.io/munishgoyal1/tripplanner:v0.X.Y

# 2) (Optional but recommended) Provision AOAI for canary+prod
./infra/provision-aoai.ps1 -Environment canary -SubscriptionId <sub-id>
./infra/provision-aoai.ps1 -Environment prod -SubscriptionId <sub-id> -SkuName GlobalStandard -Capacity 50

# 3) Copy emitted AOAI endpoint/key/deployment into local .env

# 4) Bootstrap shared data plus both environments
./infra/bootstrap-environments.ps1 -SubscriptionId <sub-id> -ImageTag v0.X.Y
```

Notes:
- Deploy scripts are now parameterized, so you can target any subscription, region, RG, and name prefix.
- Production deployment still enforces manual approval (`APPROVE_PROD_DEPLOYMENT`).

## Hosted Smoke Tests

Canary and production deploy scripts automatically run the read-only hosted
suite after updating the image. It validates the public SPA, health endpoint,
environment-owned Google OAuth callback and redirect, Maps configuration,
anonymous auth, and isolated Cosmos-backed reads.

Run it independently with:

```powershell
./infra/smoke-hosted.ps1 -Environment canary -SubscriptionId <sub-id>
./infra/smoke-hosted.ps1 -Environment production -SubscriptionId <sub-id>
```

Before promotion, exercise Azure OpenAI through canary with an isolated smoke
identity:

```powershell
./infra/smoke-hosted.ps1 -Environment canary -Deep -SubscriptionId <sub-id>
```

Deep production smoke writes one isolated chat turn and is blocked unless
`-AllowProductionWrites` is supplied explicitly. See
`DEPLOYMENT_PROCESS.md` for bake periods, manual validation, evidence, and
rollback gates.

## Local Development Data Backend

Local SPA development defaults to the isolated Docker Cosmos Emulator. To
explicitly use the shared Azure account's `tripplanner-local` database, set:

```dotenv
COSMOS_DEV_BACKEND=azure
```

Azure mode resolves the shared account endpoint/key through the signed-in Azure
CLI at startup and never persists credentials. The equivalent one-run override is:

```powershell
./scripts/dev-spa.ps1 -CosmosBackend azure
```

The emulator path performs the startup/readiness check and sets the loopback
endpoint, well-known key, `tripplanner-local`, and `COSMOS_EMULATOR=1` only for
its backend process. Cosmos DB does not permit 200 RU/s manual throughput for a
shared-throughput database; the minimum is 400 RU/s. The Azure local database
is not deployed yet, so canary and production remain at 800 RU/s total. If the
400-RU/s local database is deployed, total provisioned throughput becomes
1,200 RU/s, 200 RU/s above the lifetime free-tier throughput allowance.

## Cross-Environment Data Copy

For restore/testing scenarios (prod -> canary/local, canary -> local):

```powershell
python scripts/cosmos_copy.py `
  --src-resource-group <OLD_RG> --src-account <OLD_ACCOUNT> --src-db tripplanner `
  --dst-resource-group rg-tripplanner-data --dst-account <SHARED_ACCOUNT> `
  --dst-db tripplanner-canary --dry-run
```

Remove `--dry-run` during the maintenance window. The utility copies and then
exactly verifies `users`, `trips`, `places_cache`, `shared_trips`, `tool_cache`,
and `audit_events`; credentials are obtained from Azure CLI and are not written
to files or command history.

Immediate old-account cost reduction remains an explicit Azure change:

```powershell
./infra/set-cosmos-throughput.ps1 `
  -ResourceGroup <OLD_RG> -AccountName <OLD_ACCOUNT> -DatabaseName tripplanner `
  -DryRun
# Remove -DryRun only after approval; type APPROVE_COSMOS_400_RU when prompted.
```

Deferred cleanup requires the recorded cutover date, enforces seven full days,
rejects the shared data resource group, and checks all Container App references:

```powershell
./infra/cleanup-obsolete-resources.ps1 `
  -CosmosAccounts <OLD_RG>/<OLD_ACCOUNT> `
  -ContainerRegistries <OLD_RG>/<OLD_ACR> `
  -CutoverDate 2026-07-24T12:00:00Z -InventoryOnly
```

## Deploy flow

### To Canary (Testing)
```powershell
# 1. Build & push image
$Env:CR_PAT = "<github_personal_access_token>"
$Env:CR_PAT | docker login ghcr.io -u munishgoyal1 --password-stdin
docker build -t ghcr.io/munishgoyal1/tripplanner:v0.X.Y .
docker push ghcr.io/munishgoyal1/tripplanner:v0.X.Y

# 2. Deploy to canary (no approval needed)
./infra/deploy-canary.ps1 -ImageTag v0.X.Y -SubscriptionId <sub-id>

# 3. Test: https://mgc-app-2wf5um7ulxycm.greensky-bff152b2.eastus2.azurecontainerapps.io
#    - Test chat, map, email endpoints
#    - Verify no logs errors
#    - Run full test suite locally
```

### To Production (Approved Release)
```powershell
# 1. Once canary is verified stable:
./infra/deploy-prod.ps1 -ImageTag v0.X.Y -SubscriptionId <sub-id>

# 2. When prompted, review the checklist and type:
#    > APPROVE_PROD_DEPLOYMENT

# 3. Deployment proceeds and is logged to logs/deployments-prod.log

# 4. Monitor: az containerapp logs show -g rg-tripplanner-prod -n <prod-app-name>
```

### If Issues in Production
```powershell
./infra/rollback-prod.ps1
# Type: ROLLBACK
# App reverts to previous revision in ~2-5 seconds
```

### Manual Deploy (Alternative)
If you prefer direct control:

```powershell
# 1. Build & push the container image to a public registry.
#    GHCR (free for public repos):
$Env:CR_PAT = "<github_personal_access_token>"
$Env:CR_PAT | docker login ghcr.io -u munishgoyal1 --password-stdin
docker build -t ghcr.io/munishgoyal1/tripplanner:latest .
docker push ghcr.io/munishgoyal1/tripplanner:latest

# 2. Export secrets to the shell (they're never written to a file).
$Env:AZURE_OPENAI_ENDPOINT  = "<from-portal>"
$Env:AZURE_OPENAI_API_KEY   = "<from-portal>"
$Env:DUFFEL_API_KEY         = "<duffel_test_token>"
$Env:GOOGLE_PLACES_API_KEY  = "<google-key>"
$Env:TAVILY_API_KEY         = "<tavily-key>"
$Env:CONTAINER_IMAGE        = "ghcr.io/munishgoyal1/tripplanner:latest"

# 3. Deploy.
$Env:COSMOS_ACCOUNT_NAME = az cosmosdb list -g rg-tripplanner-data --query "[0].name" -o tsv
az deployment group create `
  --resource-group rg-tripplanner-canary `
  --template-file infra/main.bicep `
  --parameters infra/canary.bicepparam `
  --parameters cosmosAccountName=$Env:COSMOS_ACCOUNT_NAME `
  --query "properties.outputs.containerAppUrl.value" -o tsv
```

The output URL is the live app — open it in a browser (FastAPI serves the
React SPA at the root and the API under `/api`).

## Subsequent image updates

After the first deployment, push a new image tag and either redeploy the
Bicep (idempotent) or update just the container:

```powershell
az containerapp update `
  --name <appName> `
  --resource-group rg-tripplanner-prod `
  --image ghcr.io/munishgoyal1/tripplanner:latest
```

