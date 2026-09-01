# Cloud Account Migration

This directory owns repeatable, approval-gated migration of the Tripplanner Azure
and Google Cloud estate to new account and billing boundaries. Azure and Google
have separate operational flows because Azure copies data into newly provisioned
resources while Google moves existing projects in place.

## Azure

The shared `Invoke-CloudMigration.ps1` orchestrator currently owns Azure migration:
inventory, target provisioning, exact Cosmos copy and verification, DNS cutover,
and allowlisted source resource-group retirement. Copy `migration.example.json`
to an ignored path such as `logs/migration/config.json`, fill every Azure target
value, and keep `google.enabled` false.

Use one stable run ID so each phase can verify prior evidence:

```powershell
$run = Get-Date -Format "yyyyMMdd-HHmmss"
pwsh -File infra/migration/Invoke-CloudMigration.ps1 `
  -ConfigPath logs/migration/config.json -RunId $run -Cloud azure -Phase preflight
pwsh -File infra/migration/Invoke-CloudMigration.ps1 `
  -ConfigPath logs/migration/config.json -RunId $run -Cloud azure -Phase inventory
```

Later Azure write phases retain their exact approvals. Deleting source resource
groups is irreversible, and subscription cancellation remains a manual billing
owner action after the scripts prove that no managed resources remain. The final
Cosmos backup under `logs/migration/<run>/azure/` is the recovery artifact.

## Google Cloud

The Google workflow moves existing projects in place. This preserves project IDs,
project numbers, API keys, OAuth clients, project-owned resources, and data. It
discovers every project linked to the source billing account so an undocumented
project cannot continue charging the old account unnoticed.

Start with a read-only inventory from the source account:

```powershell
pwsh -File infra/migration/google/migrate-google-account.ps1 -Phase Plan
```

Create the target Google Cloud organization, billing account, and payment profile,
then fill `target.organization` and `target.billingAccount` in
`google/google-account-migration.json`. Run the stages in order:

```powershell
pwsh -File infra/migration/google/migrate-google-account.ps1 `
  -Phase Grant `
  -GrantApproval GRANT_GOOGLE_MIGRATION_CONTROL

# Switch the one active gcloud account and ADC quota project to the target login.
gcloud config configurations activate <target-configuration>
gcloud auth application-default login

pwsh -File infra/migration/google/migrate-google-account.ps1 `
  -Phase Cutover `
  -CutoverApproval MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING

pwsh -File infra/migration/google/migrate-google-account.ps1 -Phase Verify
```

Before retirement, move the GA4 property to an Analytics account controlled by the
target login and transfer the target payment profile. GA4 keeps measurement ID
`G-VNTSQG9SWZ`, streams, configuration, and reporting data. Google does not expose
these account-level operations through `gcloud`, so the script deliberately cannot
claim they happened.

After production OAuth, Maps, Places, Routes, budgets, quotas, and GA4 Realtime have
been checked under the target login:

```powershell
pwsh -File infra/migration/google/migrate-google-account.ps1 `
  -Phase Retire `
  -RetireApproval RETIRE_OLD_GOOGLE_ACCOUNT `
  -ManualCompletionApproval CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED
```

For a later repeat migration, prepare source and target named `gcloud`
configurations and target ADC in advance. The complete sequence then has one entry
point while retaining every exact approval:

```powershell
pwsh -File infra/migration/google/migrate-google-account.ps1 `
  -Phase All `
  -SourceGcloudConfiguration tripplanner-source `
  -TargetGcloudConfiguration tripplanner-target `
  -GrantApproval GRANT_GOOGLE_MIGRATION_CONTROL `
  -CutoverApproval MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING `
  -RetireApproval RETIRE_OLD_GOOGLE_ACCOUNT `
  -ManualCompletionApproval CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED
```

`All` is appropriate only after GA4 and payment-profile transfer has already been
completed and target ADC is authenticated. First-time migration should use the
stages separately so production can be validated before retirement.

Cutover is retry-safe. Its checkpoint is the complete Plan-time project set; on a
retry, projects already moved or linked to target billing are skipped, while a new
project attached to source billing or a checkpoint project linked to an unexpected
billing account stops the run for investigation.

Retirement first reruns verification, then removes the old principal's direct
project, source-organization, and source-billing roles. The old billing account has
no linked projects at that point and therefore no resource usage to charge. Close it
in Google Cloud Console; the installed `gcloud` CLI has no billing-account closure
operation.

Reports are written under `google/reports/` and are ignored by Git. They are
checkpoints for resume and audit, not credentials. Never commit OAuth secrets, API
key values, payment details, access tokens, or ADC files.

`aitripplanner-local-507305` is explicitly excluded in the checked-in Google
manifest following owner confirmation that it is an unused dummy project. The
workflow still discovers all source-billed projects and blocks on any other new
or inaccessible project. Closing or deleting that excluded dummy project remains
a separate owner action if its billing link can incur charges.

The generic cloud orchestrator intentionally does not implement Google migration.
Use the guarded Google command above so fixed project lists cannot omit a billed
project and source retirement cannot run without its dedicated verification gates.
