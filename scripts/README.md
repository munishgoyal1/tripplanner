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
| `prod_cache_sync.py` | Merge-only local central cache and production Cosmos synchronizer; fixed to shared Places and global tool-cache partitions |
| `dev/corpus_cache.py` | Reviewable Places corpus save/status utility; `--sync` remains an explicit lane/central recovery import rather than a startup requirement |
| `prod-cache-sync.ps1` | Guarded operator entry point for cache status, pull, push, and two-way synchronization |
| `hosted_smoke.py` | Read-only hosted HTTP smoke implementation |
| `performance_baseline.py` | Hermetic endpoint performance baseline |
| `smoke_test.py` | Local provider credential and connectivity smoke |
| `dev/dev-spa.ps1` | Canonical local FastAPI, SPA, Labs, and emulator launcher |
| `dev/sandbox.ps1` | Create, run, update, promote, discard, or list isolated feature sandboxes; linked Lab sandboxes version successful iterations and promotion |
| `dev/full-2way-sync.ps1` | Convergence sync for every local branch, including sandbox, multiagent, and unattached branches; automatically replays recorded conflict resolutions across every lane type; pass `sbx` for registered sandboxes only |
| `dev/resolve-all-recorded-conflicts.ps1` | Recovery-only scan of every attached worktree; replays recorded Git `rerere` resolutions, commits completed merges, and reports new conflicts without fetching, aborting, or pushing |
| `dev/sandbox_seed.py` | Seed, drop, or capture data for a sandbox emulator database |
| `dev/debug_store_cli.py` | Internal CLI behind the Trip Flight Recorder launchers |
| `dev/debug-store.ps1` | Dispatcher the Trip Flight Recorder launchers call |
| `dev/build-corpus.ps1` | Generate paid Trip Quality Corpus records; choose one scope per run: `--country india` for trips within India or `--market india` for both domestic and outbound Indian-traveler scenarios |
| `dev/trip_audit.py` | Run every quality rule over the available trip evidence and report what is new |
| `dev/trip-audit.ps1` | Dispatcher the Run-Quality-Audit launchers call |
| `dev/multiagent.py` | Multiagent controller: dispatch routine and explicitly approved issues to bounded workers, integrate, and open one batch PR |
| `dev/multiagent_core.py` | Pure selection, collision, fingerprint, and lease logic behind the controller |
| `dev/multiagent.ps1` | Dispatcher the multiagent launchers call |
| `dev/capture-screens.ps1` | Capture screenshots, API view-models, console output, and DOM from a running local stack |
| `dev/ui-snapshot.ps1` | Preserve or inspect accepted UI tags |
| `dev/record-lab-implementation.ps1` | Append an agent Lab state version; defaults to implementation evidence and owner review, with `-State` for park, discard, completion, or reopen |
| `dev/lib/run-log.ps1` | Shared last-run transcript logging for every entry-point script |
| `dev/start-cosmos-emulator.ps1` | Start or verify the local Cosmos emulator |
| `dev/check-local-cosmos.ps1` | Report the local emulator connection coordinates |
| `win/user/run/Start-Dev-Spa.cmd` | Windows launcher for the canonical local stack without synchronizing first |
| `win/user/run/Run-Latest-Master.cmd` | Windows owner-facing synchronize-and-run launcher for primary `master` |
| `win/user/sync/Sync-Sbxs-FromMaster.cmd [sandbox]` | Windows launcher to fast-forward primary `master`, then update every sandbox or only the selected one |
| `win/user/sync/Sync-Across-MasterSbx.cmd [sandbox]` | Rare, gated cross-lane sync: merge every sandbox (or only the selected one) into `master`, then bring all sandboxes back up to it. Prints the exact commits and requires typing `APPROVE_SANDBOX_TO_MASTER` |
| `win/user/sync/Full-2Way-Sync.cmd [all\|sbx]` | Converge every local branch by default without hiding active edits. Clean committed lanes publish to `master`; dirty lanes take non-overlapping updates and defer publication; recorded conflicts auto-resolve across sandbox, multiagent, and standalone lanes. Pass `sbx` for registered sandboxes only. Re-runnable |
| `win/user/sync/Resolve-All-Recorded-Conflicts.cmd` | Manually scan all attached worktrees and finish every pending merge covered by a recorded resolution; new conflicts remain visible and are summarized |
| `win/user/google/Google-Places-Control.cmd` | Inspect or synchronize Places profile and GCP Service Usage state; paid enable is approval-gated |
| `win/user/google/Google-Maps-Control.cmd` | Inspect or synchronize Maps, Routes, and Static Maps state; paid enable is approval-gated |
| `win/user/azure/Azure-Services-Control.cmd [status|disable|enable] [all|local|canary|prod]` | Report or control one Tripplanner Azure environment or the whole allowlisted estate; disable stops hosted callers and blocks environment-owned service access without deleting data, while enable is spend approval-gated |
| `win/user/quality/Show-TripRecorder.cmd [query] [--days N]` | List or search Trip Flight Recorder entries by number, destination, keyword, or label |
| `win/user/quality/Maintain-TripRecorder.cmd` | Repair descriptors, reassign duplicate numbers, trim revisions, and report recorder health |
| `win/user/quality/Restore-TripRecorder.cmd [sandbox] [days]` | Restore recorded trips into an emulator; sandbox `0` or omitted means primary `master`, days defaults to 7 |
| `win/user/quality/Clear-TripRecorder.cmd --confirm CLEAR_DEBUG_STORE` | Delete the whole Trip Flight Recorder and restart numbering |
| `win/user/quality/Run-Quality-Audit.cmd` | Run the Trip Quality Audit, always write dated JSON/Markdown evidence under `audit/reports/`, and exit non-zero on findings the baseline does not hold |
| `win/user/quality/Run-Quality-Audit.cmd --all` | Show every finding, not only new ones |
| `win/user/quality/Run-Quality-Audit.cmd --accept` | Record the current findings as known |
| `win/user/quality/Build-Quality-Corpus.cmd` | Spend a bounded budget on planner-generated trips using the running stack for the checkout where the launcher is invoked; retained trips meet the corpus richness floor, empty drafts get one repair turn, three consecutive barren turns fail fast, and output reports accepted yield plus average time and stops |
| `win/user/quality/Quality-Corpus-Cache.cmd` | Inspect, save, restore, or synchronize the Places grounding behind the Trip Quality Corpus |
| `win/user/quality/Refresh-Quality-Corpus.cmd` | Spend the configured corpus budget on fresh planner trips, retain them globally, then write the normal dated quality report |
| `win/user/multiagent/Start-Multiagent.cmd` | Start the coordinator detached and open the coordinator chat; dispatches routine queued work, audit bugs, and approved gated work |
| `win/user/multiagent/Multiagent-Status.cmd` | Controller, slots, assignments, issues waiting on an owner decision, and recovery commands |
| `win/user/multiagent/Plan-Multiagent.cmd` | Dry run: what would be dispatched now, and why the rest is held |
| `win/user/multiagent/Pause-Multiagent.cmd` | Stop dispatching; running workers finish |
| `win/user/multiagent/Resume-Multiagent.cmd` | Resume dispatching |
| `win/user/multiagent/Stop-Multiagent.cmd` | Stop the controller and its workers, keeping worktrees, branches, and transcripts |
| `win/user/multiagent/Open-Coordinator.cmd` | Open the owner-facing coordinator chat in VS Code |
| `win/user/multiagent/Run-Quality-Issue-Producer.cmd [--dry-run]` | Run the read-only Trip Quality Audit and propose every new deduplicated finding group as an inert `owner:proposed` issue; never accepts the baseline |
| `win/user/quality/Capture-Screens.cmd [-Sandbox n] [-Label name]` | Capture UI evidence for a quality finding: screenshots, `/trip/view` and map JSON, console errors, and DOM |
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
| `win/user/sandbox/Discard-Sandbox.cmd` | Preserve and publish the lane's trip snapshot and warmed place cache, then remove its worktree, branches, and emulator database (refuses while work is not in `master`; pass `-DeleteRemoteBranch:$false` to retain the remote branch) |
| `win/user/sandbox/List-Sandboxes.cmd` | List every sandbox with its number, purpose, promotion status, URLs, branch, worktree, database, and whether it is serving |
| `win/canary/Deploy-Canary.cmd` | Launch `infra/deploy-canary.ps1` to build, push, deploy, and smoke the current SHA on canary |
| `win/prod/Deploy-Prod.cmd` | Launch `infra/deploy-prod.ps1`, which still requires the typed `APPROVE_PROD_DEPLOYMENT` gate |
| `win/prod/Rollback-Prod.cmd` | Launch `infra/rollback-prod.ps1` to activate the previous production revision |
| `win/prod/Sync-Prod-Cache.cmd` | Inspect or merge eligible cache entries between local `tripplanner-cache` and production; production writes require `APPROVE_PROD_CACHE_SYNC` |
| `mac/` | macOS `.command` equivalents for every `win/` Windows `.cmd` launcher |

The macOS launchers preserve the Windows names with a `.command` extension and
the same subfolder layout. For example, use
`scripts/mac/user/run/Run-Latest-Master.command`,
`scripts/mac/user/sandbox/New-Sandbox.command`, or
`scripts/mac/canary/Deploy-Canary.command`. They forward all arguments to the
same PowerShell owners and retain the existing deployment approval gates.
Launchers under `user/sync`, `user/run`, and `user/google` print their purpose,
syntax, options, safety notes, and examples when their first argument is `help`
or `?`; help mode never invokes the underlying operation. In zsh, quote or
escape the wildcard as `'?'` or `\?`, or use the simpler `help` form.

## Production cache synchronization

`Sync-Prod-Cache` is an owner-triggered merge, not a database copy. Its fixed
allowlist is `places_cache/_shared` plus `tool_cache/_global_` when the target
profile enables `CACHE_WARM_EVERYTHING`. It never reads or writes `user:*`
partitions, application containers, or deletes. Newer Places metadata, reviews,
and signed photo URLs are selected independently; tool results use `cached_at`
with the original Cosmos timestamp as a legacy fallback. Expired evidence is
skipped rather than made fresh by copying, and writes use source snapshot ETags.
The first successful apply takes complete partition snapshots and atomically
records a per-source, per-container Cosmos `_ts` watermark. Later runs query only
a five-minute overlap behind each watermark, fetch complete documents only for
candidate IDs, and still compare destination content before writing. A checkpoint
advances only after every planned write verifies and no ETag conflict occurs. An
interruption, verification failure, malformed checkpoint, or conflict therefore
causes a conservative re-read on the next run; it cannot skip an unverified delta.
Changing either cache-policy profile also invalidates the checkpoint and forces
a full scan so newly eligible old evidence is reconsidered.

Local request-time cache reuse does not require this operator synchronizer.
With `SECONDARY_DURABLE_CACHE_ENABLED=1`, the application point-reads the central
`tripplanner-cache` database only after a primary cache miss and writes eligible
shared/global results back best-effort. Canary and production profiles disable
that secondary connection; this command remains the approval-gated boundary for
moving eligible evidence between local central storage and production.

Run the matching launcher from `scripts/mac/prod/` or `scripts/win/prod/`:

```powershell
# Merge both ways. This is the default and prompts for the approval keyword.
./Sync-Prod-Cache.command
./Sync-Prod-Cache.command -Approval APPROVE_PROD_CACHE_SYNC

# Production to the local central emulator cache.
./Sync-Prod-Cache.command -Direction Pull

# Local central cache to production, or explicitly select both ways.
./Sync-Prod-Cache.command -Direction Push -Approval APPROVE_PROD_CACHE_SYNC
./Sync-Prod-Cache.command -Direction Both -Approval APPROVE_PROD_CACHE_SYNC

# Preview the default two-way merge without writing either side or prompting.
./Sync-Prod-Cache.command -WhatIf

# Ignore saved watermarks and rebuild them from complete snapshots.
./Sync-Prod-Cache.command -WhatIf -FullScan
```

The launcher accepts only the approved personal Azure identity and Visual Studio
Enterprise subscription. It retrieves the shared account credential through the
authenticated Azure CLI, keeps it in the child process environment only, removes
it after the run, and writes a credential-free JSON report under
`logs/cache-sync/`. The local Cosmos emulator must be running. Every apply is
idempotent and can be rerun after reported ETag conflicts.
The stable checkpoint is `logs/cache-sync/checkpoint.json`; `-CheckpointPath`
can isolate another operator state, `-WatermarkOverlapSeconds` can widen the
clock-safety window, and `-FullScan` provides deterministic recovery. Dry runs
never advance a checkpoint. Reports include scan mode and watermarks, candidates,
unchanged and stale counts, insert/replace outcomes, per-item delta status,
request counts, request-unit charges, and JSON payload bytes for metadata queries,
point reads, writes, and verification reads. Payload bytes describe serialized
documents, not HTTP framing or Azure bandwidth billing.

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
