# Trip document `schema_version` and migration path

> Status: **candidate for owner review** — not approved. Deferred out of the
> feature-sandbox workflow (which uses a sandbox-local seed-freshness marker
> instead). This proposal makes schema versioning a durable product concern.

## 1. Pain

Trip documents have no explicit `schema_version`. Every reader infers shape from
the fields that happen to be present, so:

- **Migrations are manual and un-versioned.** `infra/rollback-prod.ps1` explicitly
  notes it cannot undo schema/data changes; there is no forward-migration step
  either. Any change to the trip shape is an ad-hoc, hand-run edit.
- **Canary/prod drift is invisible.** Nothing records which schema a stored trip
  was written against, so a mixed population (old + new docs) cannot be detected
  or reconciled safely.
- **Seed-drift detection is weak.** Sandboxes and fixtures must guess whether their
  copied data still matches the current model. Today the sandbox workflow works
  around this with a local marker/hash of the trip-shape model files, not a real
  document version.

Grounding: `grep` for `migrat` across the repo returns only guest→account identity
migration; trip documents carry no version field; `storage_cosmos.py` reads/writes
raw dicts keyed by `(user_id, id)` with no shape gate.

## 2. Bounded first version

Add an integer `schema_version` to trip documents and a single, explicit migration
seam. Keep it small and reversible.

1. **Constant.** Introduce `TRIP_SCHEMA_VERSION = 1` in the trip view-model/model
   boundary (`src/tripplanner/web/trip_view.py` or the trip model module).
2. **Stamp on write.** When a trip is persisted, set `doc["schema_version"] =
   TRIP_SCHEMA_VERSION` (both Cosmos and local JSON stores).
3. **Upgrade on read.** Add `migrate_trip(doc) -> doc` that applies ordered,
   idempotent steps from `doc.get("schema_version", 0)` up to the current version,
   returning an upgraded copy. Missing/absent = version 0 (legacy).
4. **One call site.** Route every load through `migrate_trip` in the storage read
   path so callers always see the current shape.

No behavior change at v1 (there are no upgrade steps yet); this only establishes
the field, the constant, and the seam so the *next* shape change ships a step.

## 3. Implementation notes (real files)

- `src/tripplanner/storage_cosmos.py` — stamp on `upsert`/write; run `migrate_trip`
  in `read_doc`/list paths. Keep `_strip_system_fields` behavior intact.
- Local JSON store (`src/tripplanner/storage_*` / `~/.tripplanner/`) — mirror the
  same stamp-on-write and migrate-on-read so both backends agree.
- `src/tripplanner/web/trip_view.py` — own `TRIP_SCHEMA_VERSION` and `migrate_trip`
  next to the view-model boundary that already normalizes trip shape.
- `scripts/dev/sandbox_seed.py` — once versions exist, seeding can compare source
  vs. current version and warn/re-capture instead of relying on a file hash.
- `scripts/cosmos_copy.py` — copies could optionally report the version spread of
  the source database as a drift check.

## 4. Benefits

- Safer canary/prod migrations: a real forward path plus a recorded version per doc.
- Reliable seed/fixture drift detection for the sandbox workflow.
- A documented place for every future trip-shape change, instead of ad-hoc edits.

## 5. Risk and effort

- **Effort:** S–M. The field + constant + seam is small; the care is in routing all
  reads through one migrate call and covering both storage backends.
- **Risk:** Low at v1 (no steps yet). Main risk is missing a read path, so a legacy
  doc reaches a caller un-migrated — mitigated by centralizing reads in the store.
- **Reversible:** Yes. The field is additive; removing it is a one-line revert while
  no upgrade steps exist.

## 6. Acceptance

- New and updated trips carry `schema_version` in both Cosmos and local stores.
- Loading a legacy doc (no field) yields a doc reported as the current version.
- `migrate_trip` is idempotent (running it twice is a no-op) and unit-tested.
- No user-visible behavior change at v1.

## 7. Out of scope

- Actual shape changes / concrete migration steps (added when the first real change
  lands).
- Versioning of non-trip documents (users, caches) — separate, if ever needed.
- Automated production data backfill tooling.
