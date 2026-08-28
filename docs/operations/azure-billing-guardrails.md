# Azure Billing Guardrails

Reproducible setup for per-environment and subscription-wide budgets on the
personal Azure subscription. Azure budgets notify but do not stop resources;
the Visual Studio subscription spending limit is the only complete hard stop.

## Apply from the repository

Account identifiers, resource groups, currencies, thresholds, and amounts live
in [`infra/billing-guardrails.json`](../../infra/billing-guardrails.json). For a
new account, edit that file, sign in, preview, and apply:

```powershell
az login
pwsh -File infra/azure/apply-billing-guardrails.ps1 -WhatIf
pwsh -File infra/azure/apply-billing-guardrails.ps1
```

The script is idempotent. Re-run it after changing limits; Azure budget `PUT`
operations converge existing resources rather than creating duplicates.

Review both clouds against the configured limits with:

```powershell
pwsh -File infra/show-billing-status.ps1
pwsh -File infra/show-billing-status.ps1 -Cloud azure
```

For immediate owner control across all known Tripplanner Azure resource groups:

```powershell
./scripts/win/user/azure/Azure-Services-Control.cmd status prod
./scripts/win/user/azure/Azure-Services-Control.cmd disable prod
./scripts/win/user/azure/Azure-Services-Control.cmd enable prod APPROVE_AZURE_SPEND
./scripts/win/user/azure/Azure-Services-Control.cmd disable all
```

Use the matching `scripts/mac/user/azure/Azure-Services-Control.command` launcher
on macOS. Disable stops Container Apps, converts recurring Container Apps Jobs
to manual while retaining their original trigger, stops active job executions,
and blocks public access to OpenAI, Cosmos DB, and Azure Managed Redis. Enable
reverses those controls. Both actions discover resources only in the resource
groups declared in `billing-guardrails.json`, verify the personal account and
subscription, and never delete resources or data. Disable is immediate and does
not require approval; enable remains spend approval-gated.

To stop all hosted canary and production serving without changing dependency
access or data, use `Emergency-Bringdown down all`. It stops Container Apps,
suspends recurring jobs, and stops active executions. `Emergency-Bringdown up all
APPROVE_AZURE_SPEND` reverses it. DNS and endpoints can still resolve while the
apps are stopped, and provisioned services can continue billing.

Azure OpenAI has an additional application-level consent gate. Every model
client requires `ENABLE_AZURE_OPENAI=1`; credentials alone are insufficient.
The controller updates that flag in each selected checked-in environment profile
and reports whether it agrees with the OpenAI account's public-network state.
Cloud blocking or restoration is immediate. The profile change takes effect in
local processes after restart and in canary or production after deployment; the
controller does not deploy the application. Current profiles explicitly use `1`
to preserve operation, while an absent flag defaults to disabled. Communication
Services and Email intentionally have no application flag because they are
usage-metered and do not share OpenAI's automated runaway-spend exposure.

This is a unified orchestrator, not a universal Azure billing switch. Managed
Redis, Cosmos throughput and storage, Container Apps environments, Log Analytics,
and other provisioned resources can continue billing while access is disabled.
The `local`, `canary`, and `prod` scopes control resources in that environment's
resource group. The Cosmos account in `rg-tripplanner-data` serves all three, so
only an `all` operation changes its network access; a single-environment operation
leaves shared Cosmos available to avoid taking down the other environments.
Communication Services and Email are usage-metered and expose no reversible
account-wide pause; stopping the hosted apps removes their hosted caller but does
not invalidate independently held credentials.

## Current arrangement

Subscription `2dd0a2f4-fc3a-4245-8e40-fadd0bbcbd5b`, billing currency **INR**.
The script verifies and selects this subscription before writing anything.

| Budget | Amount | Scope | Alerts |
| --- | --- | --- | --- |
| `tripplanner-local-2000inr` | 2,000 INR | `rg-tripplanner-local` | 50 / 80 / 100% actual, 100% forecast |
| `tripplanner-canary-2000inr` | 2,000 INR | `rg-tripplanner-canary` | 50 / 80 / 100% actual, 100% forecast |
| `tripplanner-prod-2000inr` | 2,000 INR | `rg-tripplanner-prod` | 50 / 80 / 100% actual, 100% forecast |
| `tripplanner-global-8000inr` | 8,000 INR | whole subscription | 50 / 80 / 90 / 100% actual, 100% forecast |

Alerts email `munishgoyal1@gmail.com` through the
`tripplanner-budget-alerts` action group in `rg-tripplanner-data`.

## What Azure can cap

Azure Cost Management budget data can lag actual usage. A budget cannot disable
billing, stop a Container App, reduce Foundry model capacity, or delete a cache.
Unlike Google Cloud, Azure exposes no operation that detaches billing from all
resources at a chosen amount.

This Visual Studio Enterprise subscription reports `spendingLimit: On`. Azure
disables the subscription when its included monthly credit is exhausted. That
is a real hard stop, but its amount is controlled by the subscription offer,
not by `tripplanner-global-8000inr`.

An automated budget response would necessarily be partial and destructive: it
could scale Container Apps to zero and reduce model deployment capacity, taking
production offline, while continuously billed resources such as Azure Managed
Redis would continue charging until deleted. It is therefore intentionally not
part of the portable script.

## Changing limits

Edit only [`infra/billing-guardrails.json`](../../infra/billing-guardrails.json):

```json
{
  "azure": {
    "globalBudget": { "name": "tripplanner-global-8000inr", "amount": 8000 },
    "environments": [
         { "name": "local", "resourceGroup": "rg-tripplanner-local", "budgetName": "tripplanner-local-2000inr", "budget": 2000 }
    ]
  }
}
```

Keep `budgetName` stable when changing `budget`; that is how the scripts update
the existing budget instead of creating a second one. Re-run the apply script,
then use the status script to confirm current spend against the new limits.

## Port to another Azure account

1. Update `subscriptionId`, currency, action-group resource group, email, and
   environment resource groups in `infra/billing-guardrails.json`.
2. Ensure the signed-in identity can create action groups and Cost Management
   budgets at subscription and resource-group scopes.
3. Run with `-WhatIf` and verify every target belongs to the intended account.
4. Apply and confirm that the script reports the subscription's spending-limit
   state.
5. Run `infra/show-billing-status.ps1 -Cloud azure` to establish the initial
   cost baseline.

Never copy the current subscription ID into a work account. This repository's
configured subscription belongs to the personal account only.
