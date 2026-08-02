# Azure Infrastructure

This folder owns the tripplanner Azure resource definitions and guarded helper
scripts. The canonical build, canary, production, monitoring, and rollback
procedure is [Canary and Production Deployment Flow](../docs/operations/deployment-flow.md).
Do not duplicate that release runbook here.

## Footprint

| Resource | Ownership | Low-usage cost posture |
| --- | --- | --- |
| Shared Cosmos DB account | `data-stack.bicep`, `data.bicep`, `modules/cosmos-data.bicep` | Lifetime free tier when available |
| Canary and production databases | 400 RU/s shared throughput each | 800 RU/s total |
| Container Apps | `main.bicep` plus environment parameters | Scale to zero |
| Log Analytics | `main.bicep` | First 5 GB/month free |
| Production failure alert | `main.bicep`, production parameters | Low-volume scheduled query and Action Group |
| Custom domains and managed TLS | `main.bicep`, `prod.bicepparam`, Namecheap DNS | Azure-managed certificates |

The target remains below the owner's ₹10,000/month Azure credit at personal-app
traffic. Cost claims must be verified from Azure billing rather than inferred
from this table.

## Environments

| Environment | Resource group | App prefix | Cosmos database | Purpose |
| --- | --- | --- | --- | --- |
| Local | None | Local processes | `tripplanner-local` emulator database | Development |
| Canary | `rg-tripplanner-canary` | `canary-*` | `tripplanner-canary` | Hosted testing |
| Production | `rg-tripplanner-prod` | `prod-*` | `tripplanner-prod` | Approved live releases |
| Shared data | `rg-tripplanner-data` | n/a | Shared account | Canary/prod data plane |

Production serves `aitripplanner.co` and `www.aitripplanner.co`. Namecheap owns
DNS; Bicep owns the existing Azure-managed certificates and hostname bindings.
Canary and production use separate ignored environment files and must never share
a database or fall back to local `.env` credentials.

## File Ownership

| File | Responsibility |
| --- | --- |
| `data-stack.bicep` | Subscription-scope shared data resource group orchestration |
| `data.bicep` | Shared Cosmos data-plane deployment |
| `modules/cosmos-data.bicep` | Cosmos account, databases, containers, throughput, and TTL |
| `main.bicep` | Container Apps, Log Analytics, configuration, domains, and production alerting |
| `canary.bicepparam` | Canary app and database binding |
| `prod.bicepparam` | Production app, database, domains, and alert binding |
| `deploy-data.ps1` | Validate, what-if, and deploy the shared data plane |
| `deploy-canary.ps1` | Build/deploy immutable canary image and run read-only smoke |
| `deploy-prod.ps1` | Promote the canary-tested image through the production approval gate |
| `push-image.ps1` | Publish Git-SHA and `latest` image tags to GHCR |
| `rollback-prod.ps1` | Activate the previous production Container Apps revision |
| `smoke-hosted.ps1` | Public read-only smoke and explicitly guarded deep smoke |
| `bootstrap-environments.ps1` | Fresh-subscription orchestration |
| `provision-aoai.ps1` | Provision or reuse Azure OpenAI resources |
| `set-cosmos-throughput.ps1` | Guarded throughput correction for old databases |
| `cleanup-obsolete-resources.ps1` | Approval-gated obsolete-resource cleanup |
| `queries/application-failures.kql` | Shared production alert and canary analysis query |

## Provisioning

Authenticate manually before any Azure operation:

```powershell
az login
```

Preview shared-data changes before applying them:

```powershell
.\infra\deploy-data.ps1 -SubscriptionId <sub-id> -DryRun
```

A fresh subscription can be prepared with:

```powershell
.\infra\bootstrap-environments.ps1 -SubscriptionId <sub-id> -ImageTag <sha> -ProvisionAoai
```

These commands create or change external resources. Follow their approval gates
and the canonical deployment runbook. Never deploy production without explicit
owner approval.

## Local Data Backend

Local SPA development defaults to the Docker Cosmos Emulator. The canonical
`scripts/dev/start-cosmos-emulator.ps1` helper and colocated Compose definition
own its local lifecycle. `dev-spa.ps1` sets the emulator endpoint, well-known key,
database name, and loopback TLS behavior only for its backend process. Persisted
emulator data must never be reset automatically.

Azure-backed local development is an explicit override:

```dotenv
COSMOS_DEV_BACKEND=azure
```

```powershell
.\scripts\dev\dev-spa.ps1 -CosmosBackend azure
```

The Azure local database is prepared in IaC but not deployed. Deploying it would
raise provisioned shared throughput from 800 RU/s to 1,200 RU/s, above the
lifetime free-tier throughput allowance.

## Data Movement and Recovery

`scripts/cosmos_copy.py` supports exact six-container copy and verification.
Credentials come from Azure CLI and are never written to files. Use direct copy
for migration only; it is not a backup.

For recoverability evidence, use the guarded offline artifact workflow documented
in [Backup and Recovery Drill](../docs/operations/backup-recovery.md). It rejects
canary, production, same-coordinate, nonempty, missing-container, and partial
restore targets. Real production recovery requires separate explicit approval.

Obsolete-resource cleanup requires the recorded cutover date, a seven-day wait,
resource-reference checks, and its own approval phrase. Inventory mode is safe for
review:

```powershell
.\infra\cleanup-obsolete-resources.ps1 `
  -CosmosAccounts <old-rg>/<old-account> `
  -ContainerRegistries <old-rg>/<old-acr> `
  -CutoverDate <timestamp> -InventoryOnly
```
