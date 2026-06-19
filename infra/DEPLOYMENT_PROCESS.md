# Deployment Process — Production Approval Gates

## Environment Naming

### Resource Groups
- **Canary (Testing)**: `rg-tripplanner-canary`
- **Production**: `rg-tripplanner-prod`

### Resources (per environment)
| Component | Canary | Prod |
|-----------|--------|------|
| Container App | `canary-app-*` | `prod-app-*` |
| Cosmos DB | `canary-cosmos-*` | `prod-cosmos-*` |
| Container App Env | `canary-env-*` | `prod-env-*` |
| Log Analytics | `canary-logs-*` | `prod-logs-*` |
| Azure OpenAI (script-provisioned) | `aoaicanary*` | `aoaiprod*` |

Email/Communication services are optional and are not provisioned by `main.bicep`.

## Deployment Workflow

### 1. Deploy to Canary (No Approval Required)
```powershell
./infra/deploy-canary.ps1 -SubscriptionId <sub-id>
```

**Use this for:**
- Testing new features
- Bug fixes
- Infrastructure updates
- API changes
- Email endpoint verification

**Canary apps live at:**
- https://canary-app.{env}.azurecontainerapps.io (after cutover)

### 2. Promote to Production (Manual Approval Required)
```powershell
./infra/deploy-prod.ps1 -SubscriptionId <sub-id>
```

### Optional: Full Fresh Bootstrap
```powershell
./infra/bootstrap-environments.ps1 -SubscriptionId <sub-id> -ImageTag v0.X.Y -ProvisionAoai
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
[2026-06-19 14:32] Deployed by munishgoyal1@gmail.com | Image: ghcr.io/munishgoyal1/tripplanner:v0.42.5 | Approval: APPROVED
[2026-06-20 09:15] Deployed by munishgoyal1@gmail.com | Image: ghcr.io/munishgoyal1/tripplanner:v0.43.0 | Approval: APPROVED
```

## Current Transition State

Current baseline uses standardized RGs + prefix names:

- Canary: `rg-tripplanner-canary`, `canary-*`
- Production: `rg-tripplanner-prod`, `prod-*`

