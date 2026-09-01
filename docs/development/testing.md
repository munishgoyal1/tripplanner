# Testing and Validation

Use the narrowest test set that exercises a changed ownership boundary while
editing. Complete suites remain publication and release gates; they are not the
default feedback loop after every small change.

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
Changes to `trip_view.py`, `map_view.py`, or `day_journey.py` select all six owner
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
| Publication | Sandbox promotion, multiagent integration, or branch convergence | Complete backend and applicable frontend/mobile suites |
| Release | Canary or production preparation | Publication tier plus build, smoke, and release-specific gates |

The `integration` marker means a test crosses real internal component boundaries
while external dependencies remain isolated. It is not a product-domain label.
Do not use broad domain markers such as `trip` or `provider`; changed-path policy
and exact targets are more precise and easier to keep current.

## Complete publication commands

```powershell
python -m pytest -q
python -m ruff check src tests scripts/dev/test_selection.py
npm --prefix frontend run typecheck
npm --prefix frontend run test:all
npm --prefix frontend run build
```

Run mobile typecheck and lint when `mobile/` or the shared client changes. Paid
providers and hosted stores remain prohibited in automated tests; shared pytest
fixtures block outbound network and select hermetic local storage by default.
