# Infrastructure — Trip Planner on Azure

Cheapest viable footprint for global hosting:

| Resource | Purpose | Free tier? |
|---|---|---|
| Log Analytics workspace | Required by Container Apps | First 5 GB/mo free |
| Cosmos DB (NoSQL) | Persist preferences + trips | **1000 RU/s + 25 GB free** (one per subscription) |
| Container Apps environment | Hosting fabric | n/a (env itself is free) |
| Container App | React SPA + FastAPI agent | **180k vCPU-sec + 2M req/mo free**, scales to zero |

Estimated cost at low usage: well under your ₹10,000/mo Azure free credit.
Stays at ~₹0 when idle thanks to scale-to-zero.

## Environments & Naming

### Canary (Testing — No Approval Gate)
- Resource Group: `rg-tripplanner-canary`
- Container App: `canary-app-*`
- Cosmos DB: `canary-cosmos-*`
- **Use for:** Feature testing, bug fixes, infrastructure changes, email verification
- **Deployment:** `./infra/deploy-canary.ps1` (no approval required)

### Production (Live — Manual Approval Required)
- Resource Group: `rg-tripplanner-prod`
- Container App: `prod-app-*`
- Cosmos DB: `prod-cosmos-*`
- **Use for:** Tested, verified releases only
- **Deployment:** `./infra/deploy-prod.ps1` (requires explicit approval: type `APPROVE_PROD_DEPLOYMENT`)

### Migration Path
Transition to standardized naming by redeploying canary first, then production after approval.

## Prerequisites

- Azure subscription with the Cosmos DB Free Tier slot still available
- Resource groups:
  - `rg-tripplanner-prod` (production, eastus2)
  - `rg-tripplanner-canary` (canary, eastus2)
- Azure OpenAI deployed: `aoai-tripplanner-mugoy` (gpt-4.1 primary; gpt-4o and gpt-5 also available)
- Docker installed locally
- GitHub Container Registry account for container images

## Local files

- `main.bicep` — all resources at RG scope
- `main.bicepparam` — environment variables for each deployment
- `DEPLOYMENT_PROCESS.md` — detailed workflow, approval gates, and logging
- `deploy-canary.ps1` — deploy/test new changes (no approval)
- `deploy-prod.ps1` — promote to production (manual approval required)
- `rollback-prod.ps1` — revert to previous stable revision if issues occur

## Deploy flow

### To Canary (Testing)
```powershell
# 1. Build & push image
$Env:CR_PAT = "<github_personal_access_token>"
$Env:CR_PAT | docker login ghcr.io -u munishgoyal1 --password-stdin
docker build -t ghcr.io/munishgoyal1/tripplanner:v0.X.Y .
docker push ghcr.io/munishgoyal1/tripplanner:v0.X.Y

# 2. Deploy to canary (no approval needed)
./infra/deploy-canary.ps1 -ImageTag v0.X.Y

# 3. Test: https://mgc-app-2wf5um7ulxycm.greensky-bff152b2.eastus2.azurecontainerapps.io
#    - Test chat, map, email endpoints
#    - Verify no logs errors
#    - Run full test suite locally
```

### To Production (Approved Release)
```powershell
# 1. Once canary is verified stable:
./infra/deploy-prod.ps1 -ImageTag v0.X.Y

# 2. When prompted, review the checklist and type:
#    > APPROVE_PROD_DEPLOYMENT

# 3. Deployment proceeds and is logged to logs/deployments-prod.log

# 4. Monitor: az containerapp logs show -g rg-tripplanner-trip-planner -n tripplanner-app-rb4t6btfs5x5m
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
az deployment group create `
  --resource-group rg-tripplanner-canary `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
  --parameters namePrefix=canary-tripplanner `
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

