# Backup and Recovery Drill

This runbook proves that the application data contract can be exported from
Azure Cosmos DB, verified as an offline artifact, and restored exactly into an
empty isolated database. It does not deploy the app, alter the source database,
or perform an Azure-native point-in-time restore.

## Recovery scope

The recoverable application set is all six runtime containers:

- `users`: preferences, active trip pointers, chat, usage, and operation ledgers.
- `trips`: saved trip plans.
- `places_cache`: durable place metadata cache.
- `shared_trips`: public share snapshots.
- `tool_cache`: provider search cache.
- `audit_events`: restricted audit records with remaining TTL preserved.

The backup artifact contains one JSONL file per container plus `manifest.json`.
The manifest records item counts, SHA-256 checksums, source host/database,
format version, and export time. It never records Cosmos keys or connection
strings. Protect the directory as personal data and do not commit it; `logs/`
is gitignored.

## Initial objectives

These are operational targets to validate during each drill, not guarantees
until repeated evidence exists:

| Objective | Initial target |
|---|---:|
| Recovery point objective (RPO) | Age of the selected backup artifact <= 24 hours |
| Recovery time objective (RTO) | Artifact validation and isolated restore <= 60 minutes |
| Drill frequency | Before a high-risk data release and at least quarterly |
| Content verification | 100% of six containers, item counts, checksums, and exact values |

A manual export only establishes an RPO from its `exported_at` timestamp. For a
continuous production RPO, separately configure and verify Azure Cosmos DB
native backup policy and point-in-time restore eligibility. That Azure account
change is outside this drill and requires explicit approval.

## Prerequisites

1. Create an empty isolated Cosmos database whose name contains `recovery`,
   `restore`, or `drill`.
2. Provision the same six containers with partition key `/user_id`; set
   `audit_events` default TTL to `7776000`.
3. Authenticate Azure CLI with read access to the source and data-plane write
   access to the isolated target.
4. Choose a new empty local artifact directory and report path under `logs/`.

The drill rejects `tripplanner-canary` and `tripplanner-prod` as targets, the
same source/target coordinates, missing containers, partial container scopes,
and any nonempty target container.

## Run the drill

Use explicit resource coordinates. This example is illustrative and must point
to a separately approved isolated target, never canary or production:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
python scripts/cosmos_copy.py `
  --src-resource-group rg-tripplanner-data `
  --src-account <SHARED_ACCOUNT> `
  --src-db tripplanner-prod `
  --dst-resource-group <ISOLATED_RECOVERY_RG> `
  --dst-account <ISOLATED_RECOVERY_ACCOUNT> `
  --dst-db tripplanner-recovery-drill `
  --recovery-drill `
  --backup-dir "logs/recovery/$stamp/backup" `
  --report-path "logs/recovery/$stamp/report.json"
```

The command performs these steps in order:

1. Reads every document from all six source containers.
2. Removes Cosmos system metadata and preserves remaining audit TTL.
3. Writes deterministic JSONL files and a checksummed manifest.
4. Reopens and verifies every artifact checksum, item count, and identity.
5. Confirms the target is isolated, complete, and empty.
6. Restores from the artifact without consulting the source again.
7. Compares every restored key and value against the artifact.
8. Writes a credential-free evidence report.

Any failure exits nonzero. Do not treat a partial report or console output as a
pass.

## Review evidence

A passing report must show:

- `status: passed`.
- Backup and restore counts for all six containers.
- Matching backup `total_items` and restore `restored_items`.
- `verification: checksum_and_exact_content`.
- A target database containing `recovery`, `restore`, or `drill`.
- Restore duration within the current RTO target.
- Backup `exported_at` age within the current RPO target.

Also perform one read-only application validation against the isolated target:
load preferences, saved trips, chat history, itinerary, map, and a share view
for a known drill identity. Do not send chat, email, or provider writes during
this check.

Record the date, source database, target database, report path, item counts,
RPO age, restore duration, operator, and any exception. Delete the isolated
target only after evidence review; retain the protected artifact according to
the owner's data-retention decision.

## Production recovery boundary

This drill never restores into production. A real incident recovery requires:

1. Freeze or redirect application writes.
2. Preserve incident evidence and identify the desired recovery point.
3. Obtain explicit owner approval for Azure-native restore or replacement
   database creation.
4. Restore into a new database first and run this exact verification contract.
5. Validate representative reads and identity isolation.
6. Cut over application configuration through the guarded deployment path.
7. Monitor, document the achieved RPO/RTO, and retain rollback access.

Never overwrite the live production database in place. Native Cosmos restore,
new Azure resources, configuration cutover, and cleanup are separate approved
operations.
