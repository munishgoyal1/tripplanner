# Scripts

This folder owns local setup, developer workflow, diagnostics, smoke checks,
performance measurement, and data-movement utilities. Azure resource definition,
deployment, promotion, rollback, throughput changes, and destructive cloud
maintenance remain in [`../infra/`](../infra/README.md) with their approval gates.

## Entry points

| Path | Purpose |
| --- | --- |
| `setup-dev-machine.ps1` | Restore app prerequisites; `-FullAgentEnvironment` also configures VS Code/Copilot |
| `setup-dev-machine-macos.sh` | Restore the full macOS toolchain and VS Code/Copilot profile |
| `analyze-errors.ps1` | Generate local or canary error reports |
| `cosmos_copy.py` | Guarded Cosmos data copy and verification utility |
| `hosted_smoke.py` | Read-only hosted HTTP smoke implementation |
| `performance_baseline.py` | Hermetic endpoint performance baseline |
| `smoke_test.py` | Local provider credential and connectivity smoke |
| `dev/dev-spa.ps1` | Canonical local FastAPI, SPA, Labs, and emulator launcher |
| `dev/sandbox.ps1` | Create, run, update, promote, discard, or list isolated feature sandboxes; linked Lab sandboxes version successful iterations and promotion |
| `dev/full-2way-sync.ps1` | Convergence sync that keeps active WIP visible, publishes clean committed lanes, and reports overlaps or deferred publication |
| `dev/sandbox_seed.py` | Seed, drop, or capture data for a sandbox emulator database |
| `dev/debug_store_cli.py` | Show, maintain, restore, or tear down the local debug trip store |
| `dev/debug-store.ps1` | Dispatcher the debug-store launchers call |
| `dev/build-corpus.ps1` | Generate paid planner corpus trips; use `--market india-domestic` or `--market india-outbound` for India-origin weighted scenarios (`--country india` remains a domestic alias) |
| `dev/trip_audit.py` | Run every trip rule over the local corpus and report what is new |
| `dev/trip-audit.ps1` | Dispatcher the Audit-Trips launchers call |
| `dev/multiagent.py` | Multiagent controller: dispatch owner-approved issues to bounded workers, integrate, and open one batch PR |
| `dev/multiagent_core.py` | Pure selection, collision, fingerprint, and lease logic behind the controller |
| `dev/multiagent.ps1` | Dispatcher the multiagent launchers call |
| `dev/capture-screens.ps1` | Capture screenshots, API view-models, console output, and DOM from a running local stack |
| `dev/ui-snapshot.ps1` | Preserve or inspect accepted UI tags |
| `dev/record-lab-implementation.ps1` | Append an agent Lab state version; defaults to implementation evidence and owner review, with `-State` for park, discard, completion, or reopen |
| `dev/lib/run-log.ps1` | Shared last-run transcript logging for every entry-point script |
| `dev/start-cosmos-emulator.ps1` | Start or verify the local Cosmos emulator |
| `dev/check-local-cosmos.ps1` | Report the local emulator connection coordinates |
| `win/user/Start-Dev-Spa.cmd` | Windows launcher for the canonical local stack without synchronizing first |
| `win/user/Run-Latest-Master.cmd` | Windows owner-facing synchronize-and-run launcher for primary `master` |
| `win/user/Sync-Sbxs-FromMaster.cmd [sandbox]` | Windows launcher to fast-forward primary `master`, then update every sandbox or only the selected one |
| `win/user/Sync-Across-MasterSbx.cmd [sandbox]` | Rare, gated cross-lane sync: merge every sandbox (or only the selected one) into `master`, then bring all sandboxes back up to it. Prints the exact commits and requires typing `APPROVE_SANDBOX_TO_MASTER` |
| `win/user/Full-2Way-Sync.cmd` | Converge committed lane history without hiding active edits. Clean committed lanes publish to `master`; dirty lanes take non-overlapping updates and defer publication. Re-runnable |
| `win/user/debug/Show-DebugStore.cmd [query] [--days N]` | List or search archived local trips by number, destination, keyword, or label |
| `win/user/debug/Maintain-DebugStore.cmd` | Repair descriptors, reassign duplicate numbers, trim revisions, and report store health |
| `win/user/debug/Restore-DebugStore.cmd [sandbox] [days]` | Restore archived trips into an emulator; sandbox `0` or omitted means primary `master`, days defaults to 7 |
| `win/user/debug/Clear-DebugStore.cmd --confirm CLEAR_DEBUG_STORE` | Delete the whole debug store and restart numbering |
| `win/user/validation/Audit-Trips.cmd` | Audit every stored trip; exits non-zero on findings the baseline does not hold |
| `win/user/validation/Audit-Trips.cmd --all` | Show every finding, not only new ones |
| `win/user/validation/Audit-Trips.cmd --accept` | Record the current findings as known |
| `win/user/multiagent/Start-Multiagent.cmd` | Start the coordinator detached and open the coordinator chat; dispatches only issues carrying `owner:ready` |
| `win/user/multiagent/Multiagent-Status.cmd` | Controller, slots, assignments, issues waiting on an owner decision, and recovery commands |
| `win/user/multiagent/Plan-Multiagent.cmd` | Dry run: what would be dispatched now, and why the rest is held |
| `win/user/multiagent/Pause-Multiagent.cmd` | Stop dispatching; running workers finish |
| `win/user/multiagent/Resume-Multiagent.cmd` | Resume dispatching |
| `win/user/multiagent/Stop-Multiagent.cmd` | Stop the controller and its workers, keeping worktrees, branches, and transcripts |
| `win/user/multiagent/Open-Coordinator.cmd` | Open the owner-facing coordinator chat in VS Code |
| `win/user/multiagent/Run-Audit-Producer.cmd [--dry-run]` | Run the read-only trip audit and propose issues for what is new; never accepts the baseline |
| `win/user/debug/Capture-Screens.cmd [-Sandbox n] [-Label name]` | Capture UI evidence for a bug: screenshots, `/trip/view` and map JSON, console errors, and DOM |
| `win/user/sandbox/New-Sandbox.cmd` | Create an isolated feature sandbox (branch, worktree, ports, DB) from latest `master`; add `-LabId <id>` for a Lab implementation |
| `win/user/sandbox/Run-Sandbox.cmd` | Seed and run a sandbox on its isolated ports (holds the terminal) |
| `win/user/sandbox/Run-All-Sandboxes.cmd` | Seed and run every registered sandbox in independent background processes |
| `win/user/sandbox/Serve-Sandbox.cmd` | Start a sandbox detached, wait for API, SPA, and Labs readiness, and record a linked changed iteration with `-IterationSummary` (stamped with the lane, commit, UTC time, and `-SessionTitle`) |
| `win/user/sandbox/Stop-Sandbox.cmd` | Stop a served sandbox and free its ports |
| `win/user/sandbox/Update-Sandbox.cmd` | Merge the sandbox's remote head and current `origin/master` into its local branch, then push that sandbox branch; never promotes to `master` |
| `win/user/sandbox/Rename-Sandbox.cmd <sandbox> <new-name>` | Rename a sandbox's name part; its branch, worktree, and database follow while the number keeps its ports |
| `win/user/sandbox/Resolve-SandboxConflicts.cmd` | Finish a manually resolved sandbox merge and push the sandbox branch |
| `win/user/sandbox/Merge-Sandbox.cmd` | Same gates as promotion, but keeps the sandbox: fetch latest `master`, auto-resolve conflicts, validate, push, open the PR, merge, verify it landed, then resynchronize the sandbox so work continues in the same lane |
| `win/user/sandbox/Promote-Sandbox.cmd` | End to end: sync, validate, push, open the PR, merge into `master`, verify the merge landed, and discard the sandbox |
| `win/user/sandbox/Discard-Sandbox.cmd` | Remove a sandbox worktree, local and remote branches, and emulator database (refuses while work is not in `master`; pass `-DeleteRemoteBranch:$false` to retain the remote branch) |
| `win/user/sandbox/List-Sandboxes.cmd` | List every sandbox with its number, purpose, promotion status, URLs, branch, worktree, database, and whether it is serving |
| `win/canary/Deploy-Canary.cmd` | Launch `infra/deploy-canary.ps1` to build, push, deploy, and smoke the current SHA on canary |
| `win/prod/Deploy-Prod.cmd` | Launch `infra/deploy-prod.ps1`, which still requires the typed `APPROVE_PROD_DEPLOYMENT` gate |
| `win/prod/Rollback-Prod.cmd` | Launch `infra/rollback-prod.ps1` to activate the previous production revision |
| `mac/` | macOS `.command` equivalents for every `win/` Windows `.cmd` launcher |

The macOS launchers preserve the Windows names with a `.command` extension and
the same subfolder layout. For example, use
`scripts/mac/user/Run-Latest-Master.command`,
`scripts/mac/user/sandbox/New-Sandbox.command`, or
`scripts/mac/canary/Deploy-Canary.command`. They forward all arguments to the
same PowerShell owners and retain the existing deployment approval gates.

Every entry point above writes its latest run to
`<primary-checkout>/logs/last-run/<name>.log`, overwritten each run, next to an
append-only `runs.log` index. The primary checkout and every sandbox read the same files,
so the last run of any script can be debugged from anywhere. Each log opens with
a `[time]` start stamp and closes with the outcome and elapsed time.

A transcript only records what PowerShell itself writes, so an unpiped native
process (`docker`, `az`, `npm`) writes past it to the console and leaves nothing
in the log. Run long external tools through `Invoke-LoggedNative` from
`dev/lib/run-log.ps1`, which streams both output streams through PowerShell and
records the command, exit code, and duration.

One process owns a transcript for as long as it runs, so a second run of the same
script cannot open that file. `Start-RunLog` falls back to `<name>.pid<id>.log`
rather than losing the transcript, and prunes those private files after three
days. A script that already redirects its own output (the detached sandbox
runner) sets `TRIPPLANNER_RUN_LOG=0` so it never holds the shared file open.

## Sandboxes

A sandbox is numbered when it is created, and the number is its port slot: `#1`
serves 8100/5273/5275, `#2` serves 8110/5283/5285. The name is
`<number>-<short-name>`, which also names the branch, the worktree, and the
emulator database. Keep the short name under 20 characters.

```powershell
.\scripts\user\sandbox\New-Sandbox.cmd lab16-chatdock "Assistant dock rework"
.\scripts\user\sandbox\List-Sandboxes.cmd
.\scripts\user\sandbox\Serve-Sandbox.cmd 1
```

On macOS, use the matching launchers:

```bash
./scripts/mac/user/sandbox/New-Sandbox.command lab16-chatdock "Assistant dock rework"
./scripts/mac/user/sandbox/List-Sandboxes.command
./scripts/mac/user/sandbox/Serve-Sandbox.command 1
./scripts/mac/user/sandbox/Run-All-Sandboxes.command
```

`Run-All-Sandboxes` starts every registered sandbox concurrently, using the same
seed and foreground `Run` path as an individual sandbox. It returns immediately;
per-sandbox stdout and stderr are written under `logs/sandbox/run-all/`.

Every verb except `New-Sandbox` accepts the number, the full name, or the short
name without its number prefix.

Discard waits briefly for Windows to release stopped sandbox processes before it
reports a locked worktree directory. A genuinely incomplete cleanup remains in
the sandbox registry, so rerunning discard safely retries only the remaining work.

Keep root-level scripts that are direct setup, diagnostic, smoke, or data utility
entry points. Put implementation and source-control workflow under `dev/`,
regular Windows owner-facing launchers under `win/user/`, including sandbox launchers under
`win/user/sandbox/`, and the hosted deployment launchers under `win/canary/` and `win/prod/`.
Keep macOS launcher equivalents under the matching folder in `mac/`.
Do not move cloud-mutating
operations out of `infra/` merely because they are implemented in PowerShell;
`win/canary/` and `win/prod/` hold only launchers for the gated scripts that live there.
