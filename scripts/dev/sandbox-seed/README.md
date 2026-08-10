# Sandbox seed fixtures

This folder holds optional, checked-in seed fixtures for sandboxes. Each fixture
is a JSON file captured from a real trip so its shape always matches the current
app data model — do **not** hand-author these, capture them (see below) so they
never drift from the live schema.

## How seeding works

`scripts/dev/sandbox_seed.py` populates a sandbox's isolated emulator database
(`tripplanner-sbx-<slug>`). By default it copies your everyday `tripplanner-local`
data (`--source local`), which is always current-schema. Use fixtures only when
you want a stable, curated starting set that does not depend on your local data:

```
python scripts/dev/sandbox_seed.py seed --database tripplanner-sbx-<slug> --source fixtures
```

`scripts/user/sandbox/Run-Sandbox.cmd` on Windows and
`scripts/mac/user/sandbox/Run-Sandbox.command` on macOS seed with
`--source local --if-empty` automatically, so a fresh sandbox opens with
realistic data and re-running never duplicates it.

## Representative seed set

Capture these four trips (from `tripplanner-local`) so sandboxes can exercise the
common shapes. Labels are suggestions; capture whatever real trips match.

| Label | Shape | Why it matters |
| --- | --- | --- |
| `S1-single-destination` | One city, a few days | Simplest happy path |
| `S2-multi-city` | Several cities, one region | Ordering, inter-city transit |
| `S3-multi-modal` | Air + train + road, many days | Stresses routing and details |
| `S4-minimal` | Empty or one-item trip | Empty states and first-run UX |

## Capturing a fixture

Run the everyday local stack once so `tripplanner-local` has the trip, then:

```
python scripts/dev/sandbox_seed.py list-source
python scripts/dev/sandbox_seed.py capture --trip-id <trip-id> --label S1-single-destination
```

This writes `S1-single-destination.json` here, containing the trip plus its owning
user docs with Cosmos system fields stripped. Commit the fixture to share it.

## Schema note

Fixtures capture the trip shape as it exists today; there is no product-level
`schema_version` field yet. If the trip model changes materially, re-capture the
fixtures rather than migrating them. A durable product-level schema version and
migration path is proposed separately under
`docs/reference/agent-proposals/tech-debt/`.
