# Return Azure hosting to the personal subscription

Issue: https://github.com/munishgoyal1/tripplanner/issues/362

## Owner request
Migrate local, canary and prod Azure resources from the organizational account
back to the existing personal-account subscription. Reuse compatible existing
target resources. Copy Cosmos and other inventoried data. Never delete source
resources. Keep Google outside this Azure migration.

## Acceptance
- Independently verify each account, tenant and subscription before any writes.
- Inventory both subscriptions; classify every source resource and data store.
  Reuse target resources only after comparing identity, region, SKU and data.
- Source preservation is a hard configuration guard before any retire action.
  Bulk workflows cannot invoke retirement when preservation is selected.
- Authentication can use separate AZURE_CONFIG_DIR directories. Credentials are
  never committed or printed; each command selects the intended account.
- Full Cosmos copy discovers all containers, checks partition/schema compatibility,
  preserves expiry and verifies contents. Source key is read-only where possible.
- Existing target data must be backed up/compared before an approved overwrite;
  no automatic deletion of extra target items to force verification to pass.
- Freeze writes only for final synchronization and traffic cutover after target
  validation. Preserve source as rollback; record data divergence after cutover.
- Data that cannot be transparently moved (historical platform logs, managed
  certificates, service identities) needs an explicit preservation/recreation plan.
- Local remains the local runtime/emulator; migrate its cloud dependencies.
- Exact models/SKUs/quotas, deployed image and DNS ownership come from live
  inventory, not the old manifest. New managed identity code needs a compatible
  image; never deploy the manifest's stale image with changed authentication.

## Validation
Focused behavioral tests for preservation, auth routing, full-container copy and
expiry; PowerShell parsing and infrastructure compilation. Azure what-if must
have no deletes. Run target smoke and data verification before traffic cutover.
Source and target live acceptance remain pending authenticated access.
