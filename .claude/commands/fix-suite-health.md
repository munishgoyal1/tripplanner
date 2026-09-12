---
description: Work through the current suite-health report and fix the failing tests properly.
---

You are fixing the accumulated test debt that the lane gates no longer catch,
because the complete suites are suspended from local validation (see
`scripts/dev/validation-policy.json`). This is the one-pass, deep-investigation
session that suspension is paying for. Do it properly.

## Read first, do not re-run

1. `scripts/dev/test-health-baseline.json` — the checked-in known-failure record.
2. `logs/suite-health/latest.json` and the `report.md` beside it — the newest run.

**Do not run the complete suites.** They have already run; that is the entire
point. Run individual node ids only.

If no report exists, or the newest is stale against current `origin/master`, ask
the owner to run `pwsh scripts/dev/suite-health.ps1` first. Do not run it
yourself without being asked — it takes over twenty minutes and rewrites nothing
useful if the tree is not the one the owner meant.

## Order of work

1. **NEW** — failures absent from the baseline. These regressed most recently
   and have the freshest context. Always first.
2. **KNOWN with `category: "real"`** — oldest `first_seen` first. An entry that
   has been failing for months is the one most likely to be hiding a genuine
   defect everyone has learned to ignore.
3. **KNOWN with `category: "flaky-under-load"`** — these pass serially and fail
   under concurrent load. Their fix is isolation, a budget that reflects real
   contention, or removing the shared resource — *not* logic changes. Read
   `docs/development/testing.md` on why `-n 2` rather than `-n 4` before
   touching any timing budget.
4. **MISSING** — the node id did not run at all. Find out why: renamed, deleted,
   or skipped. Report it; never quietly retire it.

## Method, per failure

- Reproduce with the exact node id, serially, before changing anything:
  `python -m pytest -q -p no:cacheprovider "<node id>"`
- Find the root cause. Read the code under test, not just the assertion.
- Fix the cause. Re-run that node id, then the file it lives in.

## Prohibited without explicit written justification

These are the cheap fake fixes that make the baseline lie. If one is genuinely
correct, record why in that entry's `note` field and call it out in your summary:

- Deleting a test, or the assertion that fails.
- `@pytest.mark.skip`, `xfail`, `.skip`, `.todo`.
- Widening a timing or iteration budget to make a slow test pass.
- Weakening an assertion (`assertEqual` → `assertAlmostEqual`, exact → `in`,
  dropping a field from a compared structure).
- Adding a retry or a sleep.

## Finish

1. Re-run only the affected node ids.
2. `pwsh scripts/dev/suite-health.ps1 -UpdateBaseline` to retire what you fixed.
   This is a full run, so do it once, at the end.
3. Commit on a `claude/<slug>` branch created in a new worktree from current
   `origin/master`; the primary checkout stays on `master`. See
   `docs/development/agent-workflow.md`.
4. Close with the response structure `AGENTS.md` requires: Original prompt,
   Root cause (RCA), Summary, Next actions, Learning note.

State plainly which failures you did not fix and why. A partial fix reported
honestly is worth far more here than a baseline massaged into looking green.
