# Cosmos managed identity and read-only debugging

Issue: https://github.com/munishgoyal1/tripplanner/issues/359

## Outcome
Hosted application credentials come from a dedicated managed identity scoped to
its environment database, with no Cosmos key copied into Container Apps. A
separate operator command reads a single user's trip and optional chat using an
Azure CLI identity granted Cosmos Data Reader on the necessary containers.

## Scope and constraints
- Keep local emulator key authentication and explicit legacy local key/connection
  string compatibility; managed identity mode never falls back to either.
- Use a user-assigned identity so its database role can be provisioned before the
  app revision. Keep the existing scheduled demo job identity compatible.
- Database/container provisioning, TTL and indexing belong to IaC for hosted
  identity connections. Emulator initialization stays convenient.
- Debugging requires endpoint, database, user ID and trip ID explicitly. It has
  no discovery, query, write, schema initialization, or production-key retrieval.
- The reader uses AzureCliCredential, not the app identity/credential chain.
- Data Reader is enforced by Azure RBAC. User/trip limits are application guards,
  not row-level Azure permissions; Reader still accesses its whole container.
- No Azure deployment, key rotation, account-wide local-auth disabling, or changes
  to legacy cache-copy utilities in this milestone.

## Acceptance and validation
- App Bicep has a managed identity, database-scoped contributor assignment,
  explicit identity client ID and managed-identity flag; no cosmos-key injection.
- Identity authentication wins over stale keys/connection strings, and errors do
  not trigger fallback. Hosted identity initialization only gets existing proxies.
- Reader only point-reads the exact IDs/partition; chat is opt-in. No active trip
  read that could expose an unrelated trip. Missing items have a clear result.
- Focused tests prove credential routing and resource/read-only boundaries.
- Compile Bicep offline and run repository lint plus relevant regression tests.
- Document reader role provisioning/removal, required data-stack ordering, old
  revision/secret cleanup, role propagation and canary-to-prod validation.
- Live acceptance is deferred until Azure sign-in and authorized rollout.

## Implementation evidence
- 55 focused tests passed (identity, debugger, storage, trips, demo, migration).
- Both Bicep entry points compiled; compiled app includes role ordering and no
  Cosmos secret, and debugging grants are container-scoped Data Reader.
- Critical repository lint and full lint for changed Python files passed.
  Full repository Ruff reports 186 existing findings in unchanged files.
- No Azure deployment or role grant performed; live rollout is pending.
