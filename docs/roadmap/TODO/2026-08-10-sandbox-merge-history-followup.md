# Deferred TODO: Sandbox Merge-Heavy History Clarification

Status: Deferred by owner request on 2026-08-10
Owner intent: Persist context so next session can resume without re-discussing background.

## Owner Prompt (verbatim)
"hold on to this, log it in details with context as needed as a TODO so that when i next ask you we need not discuss this again we can simply pick it from here the point we left it at. , put TODO folder under docs/roadmap


Going forward for any deferred items i will ask you to place a tood"

## What Was Being Discussed
The owner asked why sandbox branches (example: sbx-1) now show many merge-based PR/commit patterns that look unusual versus the prior worker setup.

## Root Cause Summary
1. Sandbox sync now uses merge-based updates from master into each long-lived sandbox branch.
2. The updated sync invariant requires every sandbox local and remote branch to contain current master after sync.
3. Long-lived sandbox branches naturally accumulate repeated "merge master into sandbox" commits over time.
4. GitHub branch/PR views surface those merge relationships prominently, so history appears noisier.

## Why Earlier Worker Flow Looked Cleaner
1. Worker branches/worktrees were often shorter-lived and reset/recreated more frequently.
2. Fewer repeated sync cycles landed on the same branch history.
3. Some prior flows effectively produced a more linear visual history (at the cost of less durable isolated lanes).

## Important Clarification
This is expected behavior under the current policy and not a sync correctness failure.
- Correctness objective: no sandbox (local or remote) should be behind master after sync.
- Side effect: increased merge-commit density in sandbox histories.

## Options Previously Offered (pending owner choice)
1. Rebase-based sandbox sync:
   - Pros: cleaner linear sandbox history.
   - Cons: rewrites sandbox history and is riskier for shared remote sandbox branches.
2. Keep merge sync, squash at promotion:
   - Pros: preserve robust sandbox safety while keeping master cleaner.
   - Cons: sandbox branch history remains merge-heavy until promotion.
3. Periodic sandbox recreation after promotions:
   - Pros: lowest long-tail history buildup and very clean branch shape.
   - Cons: requires stronger discipline/automation around recreation cadence.

## Recommended Default If No Further Direction
Use option 2 (merge sync for safety + squash at promotion) because it preserves robust synchronization invariants while minimizing master branch noise.

## Resume Checklist For Next Session
1. Confirm preferred policy (Option 1, 2, or 3).
2. If policy changes, update sync/promotion scripts and docs consistently.
3. Validate with real Sync-All run and confirm post-sync invariant messages remain intact.
4. Record policy decision in canonical docs as appropriate.

## Related Context
- Prompt log updated in docs/reference/owner-inputs/prompts/master.txt.
- This file is intended as a carry-forward TODO artifact for deferred decisions.
