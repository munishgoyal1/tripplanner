# Deployment Process — Production Approval Gates

## Environment Naming

### Resource Groups
- **Canary (Testing)**: `rg-tripplanner-canary`
- **Production**: `rg-tripplanner-prod`

### Resources
| Component | Canary | Prod |
|-----------|--------|------|
| Container App | `canary-app-*` | `prod-app-*` |
| Cosmos DB | Shared account / `tripplanner-canary` | Shared account / `tripplanner-prod` |
| Container App Env | `canary-env-*` | `prod-env-*` |
| Log Analytics | `canary-logs-*` | `prod-logs-*` |
| Failure alerting | Report only | Email Action Group + scheduled-query rule |
| Azure OpenAI (script-provisioned) | `aoaicanary*` | `aoaiprod*` |

Email/Communication services are optional and are not provisioned by `main.bicep`.
The shared account lives in `rg-tripplanner-data`; `data-stack.bicep` owns it,
while `main.bicep` can only reference it as an existing resource.

Azure Monitor failure email is separate from application email delivery.
`main.bicep` creates it only when production parameters set
`enableFailureAlerts=true`; canary never sends operational alert email.

## Deployment Workflow

### 0. Provision Shared Data (Explicit Azure Change)
```powershell
./infra/deploy-data.ps1 -SubscriptionId <sub-id> -DryRun
./infra/deploy-data.ps1 -SubscriptionId <sub-id>
```

The script refuses to create a second free-tier account when the subscription
already has a different one. Creation, migration, cutover, and cleanup follow
the separate approvals in `.azure/deployment-plan.md`.

### 1. Deploy to Canary (No Approval Required)
```powershell
./infra/deploy-canary.ps1 -SubscriptionId <sub-id>
```

The deployment automatically runs the read-only hosted smoke suite. Then run
the deep canary check to exercise Azure OpenAI through the deployed API:

```powershell
./infra/smoke-hosted.ps1 -Environment canary -Deep -SubscriptionId <sub-id>
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

## Recommended Promotion Flow

1. Build and push one immutable commit-SHA image.
2. Deploy that exact image tag to canary; do not rebuild between environments.
3. Require the automatic read-only smoke suite and the deep canary smoke to pass.
4. Manually validate Google sign-in, one representative planning turn, map and
  itinerary focus, saved-trip reload, and any feature changed by the release.
5. Bake canary while watching errors, latency, restarts, and throttling. Use
  30-60 minutes for a low-risk personal-app change, several hours for shared
  backend/config changes, and 24 hours for migrations or high-risk releases.
6. Present the tested image tag, smoke results, bake duration, observed errors,
  known risks, and rollback revision to the owner for explicit approval.
7. Deploy the same image tag to production through the approval gate.
8. Run automatic read-only production smoke tests, perform a short manual
  critical-flow check, and monitor closely for at least 15-30 minutes.
9. Roll back immediately when a critical smoke or user workflow fails.

The production deployment runs read-only hosted smoke tests automatically.
Deep production smoke writes one isolated chat turn and therefore requires a
separate acknowledgement:

```powershell
./infra/smoke-hosted.ps1 -Environment production -Deep -AllowProductionWrites
```

### Optional: Full Fresh Bootstrap
```powershell
./infra/bootstrap-environments.ps1 -SubscriptionId <sub-id> -ImageTag v0.X.Y -ProvisionAoai
```

**Requirements before running:**
- [ ] Canary has been tested and verified
- [ ] Read-only and deep canary smoke suites passed for the exact image tag
- [ ] Manual validation completed for changed and critical workflows
- [ ] Canary bake period completed with acceptable telemetry
- [ ] All critical features working in canary
- [ ] Bake-period telemetry reviewed with no blocking errors
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

