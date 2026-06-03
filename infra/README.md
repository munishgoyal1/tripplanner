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

## Prerequisites

- Azure subscription with the Cosmos DB Free Tier slot still available
- Existing resource group: `rg-multiagent-trip-planner` (eastus2)
- Azure OpenAI deployed: `aoai-multiagent-mugoy` (gpt-4.1 primary; gpt-4o and gpt-5 also available)
- Docker installed locally
- GitHub Container Registry account (or Docker Hub) for the image

## Local files

- `main.bicep` — all resources at RG scope
- `main.bicepparam` — pulls values from environment variables

## Deploy flow

```powershell
# 1. Build & push the container image to a public registry.
#    GHCR (free for public repos):
$Env:CR_PAT = "<github_personal_access_token>"
$Env:CR_PAT | docker login ghcr.io -u munishgoyal1 --password-stdin
docker build -t ghcr.io/munishgoyal1/multiagent:latest .
docker push ghcr.io/munishgoyal1/multiagent:latest

# 2. Export secrets to the shell (they're never written to a file).
$Env:AZURE_OPENAI_ENDPOINT  = "<from-portal>"
$Env:AZURE_OPENAI_API_KEY   = "<from-portal>"
$Env:DUFFEL_API_KEY         = "<duffel_test_token>"
$Env:GOOGLE_PLACES_API_KEY  = "<google-key>"
$Env:TAVILY_API_KEY         = "<tavily-key>"
$Env:CONTAINER_IMAGE        = "ghcr.io/munishgoyal1/multiagent:latest"

# 3. Deploy.
az deployment group create `
  --resource-group rg-multiagent-trip-planner `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
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
  --resource-group rg-multiagent-trip-planner `
  --image ghcr.io/munishgoyal1/multiagent:latest
```
