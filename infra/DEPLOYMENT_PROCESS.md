# Deployment Process — Production Approval Gates

## Environment Naming

### Resource Groups
- **Canary (Testing)**: `rg-multiagent-canary`
- **Production**: `rg-multiagent-prod`

### Resources (per environment)
| Component | Canary | Prod |
|-----------|--------|------|
| Container App | `multiagent-app-canary` | `multiagent-app-prod` |
| Cosmos DB | `multiagent-cosmos-canary` | `multiagent-cosmos-prod` |
| Container App Env | `multiagent-env-canary` | `multiagent-env-prod` |
| Log Analytics | `multiagent-logs-canary` | `multiagent-logs-prod` |
| Email Service | `mes-multiagent-canary` | `mes-multiagent-prod` |
| Communication Service | `acs-multiagent-canary` | `acs-multiagent-prod` |

## Deployment Workflow

### 1. Deploy to Canary (No Approval Required)
```powershell
./infra/deploy-canary.ps1
```

**Use this for:**
- Testing new features
- Bug fixes
- Infrastructure updates
- API changes
- Email endpoint verification

**Canary apps live at:**
- https://mgc-app-2wf5um7ulxycm.greensky-bff152b2.eastus2.azurecontainerapps.io (current)
- https://multiagent-app-canary.{env}.azurecontainerapps.io (post-rename)

### 2. Promote to Production (Manual Approval Required)
```powershell
./infra/deploy-prod.ps1
```

**Requirements before running:**
- [ ] Canary has been tested and verified
- [ ] All critical features working in canary
- [ ] No errors in canary logs for 24+ hours
- [ ] Email endpoint tested end-to-end (test send successful)
- [ ] Database migrations (if any) validated
- [ ] Secrets/config parity confirmed
- [ ] Rollback plan documented

**Process:**
1. Script displays a readiness checklist
2. Prompts: **Type `APPROVE_PROD_DEPLOYMENT` to proceed**
3. If approved, deploys and logs the action
4. If declined, aborts safely (no changes)

**Example:**
```powershell
PS> ./infra/deploy-prod.ps1
═══════════════════════════════════════════════════════════
  🚀 PRODUCTION DEPLOYMENT — APPROVAL GATE
═══════════════════════════════════════════════════════════

Pre-deployment checklist:
 ☐ Canary tested & stable
 ☐ All critical features verified
 ☐ No canary errors (last 24h)
 ☐ Email endpoint test: PASSED
 ☐ Database migrations: OK
 ☐ Secrets config: VERIFIED
 ☐ Rollback plan: DOCUMENTED

Ready to deploy to PRODUCTION?
Type exactly: APPROVE_PROD_DEPLOYMENT

> APPROVE_PROD_DEPLOYMENT
✓ Approval confirmed. Proceeding...
[deployment runs]
```

### 3. Rollback (If Needed)
```powershell
./infra/rollback-prod.ps1
```

Reverts prod to the previous stable revision without downtime.

## Deployment History

All prod deployments logged to `logs/deployments-prod.log`:
```
[2026-06-19 14:32] Deployed by munishgoyal1@gmail.com | Image: ghcr.io/munishgoyal1/multiagent:v0.42.5 | Approval: APPROVED
[2026-06-20 09:15] Deployed by munishgoyal1@gmail.com | Image: ghcr.io/munishgoyal1/multiagent:v0.43.0 | Approval: APPROVED
```

## Current Transition State

**Production (active):**
- RG: `rg-multiagent-trip-planner`
- App: `multiagent-app-rb4t6btfs5x5m`
- Cosmos: `multiagent-cosmos-rb4t6btfs5x5m`
- Email: `mes-multiagent-prod`, `acs-multiagent-prod` ✓

**Canary (testing):**
- RG: `rg-multiagent-trip-planner-canary`
- App: `mgc-app-2wf5um7ulxycm`
- Cosmos: `mgc-cosmos-2wf5um7ulxycm`
- Email: `mes-multiagent-canary`, `acs-multiagent-canary` ✓

**Migration Plan (future):**
- Rename prod RG → `rg-multiagent-prod` (or recreate)
- Rename canary RG → `rg-multiagent-canary` (or recreate)
- Align resource names with standard naming scheme
- Scheduled for next major release to minimize disruption
