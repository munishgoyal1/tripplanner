# Lane 3 Script Audit Shortlist

**Review date:** 2026-08-15  
**Lane:** `sandbox/3-bugfixes`  
**Status:** Review list only; no implementation approved

This shortlist is derived from the two active engineering backlog entries and the
current script/log behavior. `LOW DISRUPTION` means the change is additive or
diagnostic, should not alter normal successful behavior, and is a good candidate for
owner signoff as a small first increment.

## Recommended first picks

| Priority | Disruption | Fix | Why it matters | Likely owner |
| --- | --- | --- | --- | --- |
| P0 | LOW DISRUPTION | Quiet expected readiness retries and emit one bounded timeout | Normal `Connection refused` polling is currently logged as terminating errors, hiding the actual failure and making healthy startup look broken. | `scripts/dev/dev-spa.ps1`, sandbox runner probes |
| P0 | LOW DISRUPTION | Add one structured terminal outcome to every run log | Logs frequently end with startup or pipeline noise without a clear completed/failed/interrupted result, elapsed time, or recovery command. | Shared run-log helpers and owner launchers |
| P0 | LOW DISRUPTION | Print an actionable owner error with stable error code and exact recovery command | Current failures expose PowerShell internals but often omit what changed, what is safe, and what remains untouched. | Shared script error/reporting helper |
| P1 | LOW DISRUPTION | Add verified process/port ownership diagnostics before cleanup | Port-number cleanup can terminate an unrelated process. Reporting PID, command, start time, and worktree first reduces accidental disruption. | `scripts/dev/dev-spa.ps1`, sandbox lifecycle helpers |
| P1 | LOW DISRUPTION | Make runtime preflight print executable, version, source root, and `PYTHONPATH` | The same machine currently selects runtimes differently across scripts, producing misleading missing-module and wrong-worktree failures. | Shared runtime resolver |

## Higher-disruption fixes

| Priority | Disruption | Fix | Why it matters |
| --- | --- | --- | --- |
| P0 | MEDIUM | Decouple remote promotion success from dirty/stale primary checkout state | A remote PR can merge successfully while local primary state blocks or misreports promotion. This needs transaction-boundary changes. |
| P0 | HIGH | Freeze and verify one exact candidate SHA through push, PR merge, and remote containment | Prevents validation of one commit followed by landing another commit. Requires promotion-flow redesign and broader tests. |
| P0 | HIGH | Add repository lock, atomic sandbox registry writes, and resumable promotion phases | Prevents concurrent promotions or interrupted bookkeeping from corrupting `sandboxes.json` or replaying remote operations. |
| P1 | MEDIUM | Own complete child process trees for detached stacks and recover partial stacks | Addresses exit 137/orphaned-server behavior but changes startup/stop lifecycle substantially. |
| P2 | MEDIUM | Add cross-platform lifecycle smoke matrix | Important for macOS/Windows parity, but requires a host test harness and CI or operator matrix. |
| P2 | MEDIUM | Correct paid/destructive command disclosures and approval gates | Necessary for corpus generation, restore, seed, drop, and cleanup; should follow the low-risk reporting work. |

## Recommended signoff sequence

1. Approve the five `LOW DISRUPTION` diagnostics as one small reliability increment.
2. Re-run sandbox 2 and sandbox 3 lifecycle flows and compare logs before selecting
   the promotion transaction redesign.
3. Select one P0 promotion-boundary item and one process-lifecycle item for the next
   implementation increment.
4. Keep the remaining items deferred until their owner impact and recovery behavior
   are explicitly agreed.

No item in this document is implemented or moved to `docs/implemented/` by this
review. That happens only after the approved scope is complete and validated.
