# Cloud Account Migration

This directory owns repeatable, resumable migration of the complete Tripplanner
Azure and Google Cloud estate to new account and billing boundaries. It does not
silently infer targets, copy credentials into source control, or retire a source
before target validation evidence exists.

## Safety model

- `preflight` and `inventory` are read-only.
- `provision` creates target resources only and requires
  `APPROVE_TARGET_PROVISIONING`.
- `data` copies and exactly verifies all eight Cosmos containers and requires
  `APPROVE_DATA_COPY`.
- `validate` runs target smoke and records evidence.
- `cutover` freezes source serving, performs a final data copy, invokes the
  configured DNS hook, and requires `APPROVE_CLOUD_CUTOVER`.
- `retire` removes source access and billing. Azure first stops services and,
  when configured, deletes only the allowlisted resource groups because merely
  disabling network access does not stop fixed charges. Google relinks projects
  in place to preserve globally unique IDs, then removes the old principal and
  configured budgets. It requires `APPROVE_SOURCE_RETIREMENT`.

Deleting Azure resource groups is irreversible. The final Cosmos backup under
`logs/migration/<run>/azure/` is the recovery artifact; protect it as personal
data. Subscription cancellation and closure of an old Google billing account are
billing-owner operations and remain manual after the scripts prove zero managed
resources remain.

## Configure

Copy `migration.example.json` to an ignored location such as
`logs/migration/config.json`. Fill the target tenant, subscription, billing
account, globally unique names, immutable image tag, and Google identities.
Authenticate both Azure tenants into the Azure CLI and both Google identities
into gcloud before running preflight. Never put keys or passwords in the JSON.

Target hosted secrets continue to come from ignored `.env.canary` and
`.env.prod`. Preserve `WEB_SESSION_SECRET` during cutover if existing browser
sessions must remain valid; rotate provider credentials after stabilization.

## Run

Use one stable run ID so every phase can verify prior evidence:

```powershell
$run = Get-Date -Format "yyyyMMdd-HHmmss"
pwsh -File infra/migration/Invoke-CloudMigration.ps1 `
  -ConfigPath logs/migration/config.json -RunId $run -Phase preflight
pwsh -File infra/migration/Invoke-CloudMigration.ps1 `
  -ConfigPath logs/migration/config.json -RunId $run -Phase inventory
```

After reviewing inventory, run individual write phases with their exact approval
phrase. Approval phrases are case-sensitive. A rehearsed migration can resume
all phases with one command:

```powershell
pwsh -File infra/migration/Invoke-CloudMigration.ps1 `
  -ConfigPath logs/migration/config.json -RunId $run -Phase all -Resume `
  -Approval <approval-for-the-current-gated-phase>
```

For operational safety, one approval never authorizes a later phase. `all`
therefore stops at the first phase whose approval was not explicitly supplied;
rerun it with the next approval and the same run ID. Completed checkpoints are
idempotent and retained as evidence.

## Naming and rollback

Google project IDs move in place and retain names. Azure resource-group and
logical names are retained, while global endpoints and names must be target-
unique during coexistence. Bicep-derived Container Apps suffixes change because
they depend on target resource IDs. Do not delete source resources merely to
force identical global names; that removes rollback before validation.

The DNS hook is deliberately external because Namecheap credentials and record
ownership do not belong in this repository. Configure `azure.dns.cutoverHook`
to an owner-controlled executable or leave it blank; cutover then stops before
claiming success and prints the target hostname for manual DNS work.
