# Testing and Validation

Use the narrowest test set that exercises a changed ownership boundary while
editing.

**The complete suites are suspended from the local lane gates.** They no longer
run on merge, promote, or branch-lane publish. They run periodically on master
through [`suite-health.ps1`](#suite-health), classified against a checked-in
known-failure baseline. See [Suite health](#suite-health) for why, and for the
one-word way to turn them back on.

## Select tests for a change

The selector combines direct source-to-test naming, colocated frontend tests,
explicit cross-boundary policy, and executable proofs from
[`EXPECTED_BEHAVIORS.md`](../EXPECTED_BEHAVIORS.md). It prints every command and
why it was selected.

```powershell
# All staged, unstaged, and committed changes relative to the branch baseline
python scripts/dev/test_selection.py --base origin/master

# One ownership boundary
python scripts/dev/test_selection.py --path src/tripplanner/web/trip_view.py

# One reported behavior contract
python scripts/dev/test_selection.py --behavior EB-PLAN-001

# Machine-readable output for automation
python scripts/dev/test_selection.py --base origin/master --json
```

Run the commands exactly as printed. In a sandbox, set `PYTHONPATH` to that
worktree's `src` for Python commands because the shared environment installs the
primary checkout. The selector is fail-closed: an unknown executable path chooses
the complete applicable suite rather than returning no tests.

The policy lives in [`test-selection.json`](../../scripts/dev/test-selection.json).
Every listed target and every test link in `EXPECTED_BEHAVIORS.md` is checked by
[`test_test_selection.py`](../../tests/test_test_selection.py). Add a focused rule
when a new boundary cannot be inferred; do not weaken the fallback.
Multiagent coordination tests are ownership-split across `test_multiagent_core.py`,
`test_multiagent_dispatch.py`, `test_multiagent_audit.py`,
`test_multiagent_publication.py`, and `test_multiagent_state.py`; changes to the
controller or its pure core select the complete focused set.

The former monolithic trip test module is split by ownership: persistence,
load/save, preferences, and profile learning live in `test_trip_persistence.py`;
plan state and mutations in `test_trip_plan.py`; provider-formatting and fallback
helpers in `test_trip_providers.py`; Cosmos dispatch in `test_trip_cosmos.py`; and
saved-trip identity and lifecycle in `test_trip_saved.py`. Shared imports and the
autouse storage-isolation fixture live in `tests/support/trip.py`. Trip production
boundaries select all five modules so moving a test does not narrow validation.

The trip-view projection tests are likewise ownership-split across
`test_trip_view_summary_weather_budget.py`, `test_trip_view_itinerary_rendering.py`,
`test_trip_view_map_focus.py`, `test_trip_view_journeys_transfers.py`,
`test_trip_view_places_gallery.py`, and
`test_trip_view_verification_freshness.py`. Shared deterministic Places fixtures
and trip samples live in `tests/support/trip_view.py`; that support module contains
no test functions and is registered once by the root pytest configuration.
Changes to `trip_view.py`, `itinerary_view.py`, `place_guide.py`,
`destination_overview.py`, `map_view.py`, or `day_journey.py` select all six owner
modules plus the trip-view API contract tests so cross-projection behavior remains
covered.

## Direct focused commands

Pytest accepts a file, class, function, or parametrized node:

```powershell
python -m pytest -q tests/test_graph_policy.py
python -m pytest -q tests/test_graph_policy.py::test_a_broad_new_trip_must_still_save_before_the_phase_budget_traps_it
python -m pytest -q -k "trip_conflict and not cosmos"
```

Vitest accepts a colocated test file or test-name filter:

```powershell
npm --prefix frontend exec vitest run -- src/components/ChatPanel.test.tsx
npm --prefix frontend exec vitest run -- src/App.test.tsx -t "refreshed itinerary"
```

## Validation tiers

| Tier | Purpose | Required scope |
| --- | --- | --- |
| Iteration | Fast feedback while editing | Selector output plus lint/typecheck for changed files |
| Milestone | One coherent behavior or refactor boundary | All directly owned tests and linked expected-behavior proofs |
| Publication | Sandbox promotion, multiagent integration, or branch convergence | Selector output and ruff. Typecheck, build, and the complete suites are **not** run locally; see the floor below and Suite health |
| Suite health | Periodic full-suite truth on master | Complete backend and frontend suites via `suite-health.ps1`, classified against the baseline |
| Release | Canary or production preparation | Publication tier, plus a current suite-health run with zero NEW failures, plus smoke and release-specific gates |

The `integration` marker means a test crosses real internal component boundaries
while external dependencies remain isolated. It is not a product-domain label.
Do not use broad domain markers such as `trip` or `provider`; changed-path policy
and exact targets are more precise and easier to keep current.

## Local publication floor

What actually runs at a merge, promote, or branch-lane publish — about two
seconds, where it used to be over twenty minutes:

```powershell
python -m ruff check --select E9,F63,F7,F82 src tests
```

That is the whole local gate. Everything else is measured, not assumed:

| Check | Measured on this machine | Where it runs now |
| --- | --- | --- |
| `ruff` (narrow selection) | 1.9s | Local gate, and CI |
| `npm run typecheck` (`tsc -b`) | 143.9s | CI only — every PR and every master push |
| `npm run build` (`tsc -b` + `vite build`) | 230s cold, 500s under load | CI only — every PR and every master push |
| `pytest` (complete) | 20m 22s at `-n 2` | Suite health only |
| `vitest` (complete) | not separately measured | Suite health only |

Typecheck and build are suspended locally because CI already runs both on a
dedicated runner for every pull request *and* every push to master, so paying for
them again on a loaded developer machine buys minutes of delay and no new
information. Breakage still surfaces — asynchronously, within minutes, without
blocking a merge.

The narrow ruff selection is CI's, not the project's full config. `ruff check src
tests` under the configured `E,F,I,N,W,UP` currently reports around 145 findings
on master, mostly `E501`; gating on it would be red from the first run. That
backlog is real, and it is a cleanup task rather than a merge gate.

When every web gate is suspended the gate skips the frontend entirely rather than
running `npm install` in a fresh worktree to do nothing with it.

Run mobile typecheck and lint when `mobile/` or the shared client changes. Paid
providers and hosted stores remain prohibited in automated tests; shared pytest
fixtures block outbound network and select hermetic local storage by default.

## Suite health

The complete suites are suspended from the lane gates. The measured reason: the
last recorded gate run took **20m 22s** for 2082 backend tests at `-n 2` and
still failed on seven of them. Every merge either paid twenty minutes to fail or
was waved through with `-SkipValidation`, so the cost was real and the protection
was not.

They are paid for instead in one deliberate pass:

```powershell
pwsh scripts/dev/suite-health.ps1                 # measure master, report
pwsh scripts/dev/suite-health.ps1 -UpdateBaseline # accept the current failures
```

This fast-forwards the primary checkout to `origin/master`, runs both complete
suites — neither one aborting the other — and classifies every failure against
[`test-health-baseline.json`](../../scripts/dev/test-health-baseline.json):

| Bucket | Meaning |
| --- | --- |
| NEW | Failed now, absent from the baseline. **The only red signal.** |
| KNOWN | Failed now and recorded, reported with its age and category |
| FIXED | Recorded but passing now; retire it with `-UpdateBaseline` |
| MISSING | Recorded, and did not run at all — renamed, deleted, or skipped |

`MISSING` is never folded into `FIXED`. Deleting a failing test is the cheapest
way to make a system like this lie, and that bucket is what catches it.

`first_seen`, `owner`, `note`, and `category` survive every update, so the debt
ages visibly instead of resetting. An entry whose `first_seen` is months old is
the point of the file, not a bug in it.

Reports land in `logs/suite-health/<timestamp>/` with `report.md` and
`report.json`, and `logs/suite-health/latest.json` points at the newest. Read the
JSON for numbers; this document deliberately records none, because a transcribed
failure list goes stale within a week.

To work the backlog, hand the report to a dedicated session with the
`/fix-suite-health` command. It reads the report rather than re-running the
suites, and it prohibits the cheap fake fixes — deleting tests, `skip`/`xfail`,
widening timing budgets, weakening assertions.

`category` distinguishes `real` from `flaky-under-load`. Several known failures
pass serially and fail only under concurrent load; their fix is isolation or a
budget that reflects real contention, never a logic change.

### Turning the suites back on

[`scripts/dev/validation-policy.json`](../../scripts/dev/validation-policy.json)
is the single source of truth for all three gate call sites — `sandbox.ps1`,
`full-2way-sync.ps1`, and `multiagent.py`. No test invocation was deleted; every
command still sits at its call site behind a `Test-GateEnabled` check.

| Scope | How |
| --- | --- |
| Permanently, everywhere | Set that gate's `state` to `required`. One word. |
| One invocation | `sandbox.ps1 -Merge <lane> -FullSuites` |
| One shell or agent session | `$env:TRIPPLANNER_FULL_SUITES = "1"` |
| One gate only | `lint`, `typecheck`, `build`, `pytest` and `vitest` are independent entries |

A missing or malformed policy file fails closed: every gate runs.

The expected end state is a partial return — `vitest` first, `pytest` once the
backlog is clear — which is why the gates are independent entries.

## Complete suite commands

These are what suite health runs. Running them by hand produces no baseline diff,
so prefer the script:

```powershell
python -m pytest -q -n 2
npm --prefix frontend run test:all
```

`-n 2` is a fixed worker count, not `-n auto`: this suite is usually run on a
machine already busy with other sandboxes or dev stacks, and claiming every
logical core measured slower than serial from the resulting contention. A
higher fixed count (`-n 4`) was tried and reverted: worker-vs-worker
contention under that same real concurrent load flaked tests with their own
timing or iteration budgets (trip_rebalance's search budget, the
performance-baseline p95 gate) even though they pass reliably alone. CI runs
on a dedicated GitHub runner and uses `-n auto` there instead.
