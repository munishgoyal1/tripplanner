# Scripts

This folder owns local setup, developer workflow, diagnostics, smoke checks,
performance measurement, and data-movement utilities. Azure resource definition,
deployment, promotion, rollback, throughput changes, and destructive cloud
maintenance remain in [`../infra/`](../infra/README.md) with their approval gates.

## Entry points

| Path | Purpose |
| --- | --- |
| `setup-dev-machine.ps1` | Install or restore local development prerequisites |
| `open-agent-windows.ps1` | Open the persistent agent workspaces |
| `analyze-errors.ps1` | Generate local or canary error reports |
| `cosmos_copy.py` | Guarded Cosmos data copy and verification utility |
| `hosted_smoke.py` | Read-only hosted HTTP smoke implementation |
| `performance_baseline.py` | Hermetic endpoint performance baseline |
| `smoke_test.py` | Local provider credential and connectivity smoke |
| `dev/dev-spa.ps1` | Canonical local FastAPI, SPA, Labs, and emulator launcher |
| `dev/agent-worktree.ps1` | Create, open, list, or remove coding-agent worktrees |
| `dev/sandbox.ps1` | Create, run, update, promote, ship, discard, or list isolated feature sandboxes |
| `dev/sandbox_seed.py` | Seed, drop, or capture data for a sandbox emulator database |
| `dev/ui-snapshot.ps1` | Preserve or inspect accepted UI tags |
| `dev/lib/run-log.ps1` | Shared last-run transcript logging for every entry-point script |
| `dev/start-cosmos-emulator.ps1` | Start or verify the local Cosmos emulator |
| `dev/check-local-cosmos.ps1` | Report the local emulator connection coordinates |
| `user/Sync-MeTo-Latest.cmd` | Synchronize committed code into the launcher worktree |
| `user/Sync-AllTo-Latest.cmd` | Integrate committed code, then synchronize master and all three workers |
| `user/Start-Dev-Spa.cmd` | Start the canonical local stack without synchronizing first |
| `user/Run-Latest.cmd` | Owner-facing synchronize-and-run launcher |
| `sandbox/New-Sandbox.cmd` | Create an isolated feature sandbox (branch, worktree, ports, DB) |
| `sandbox/Run-Sandbox.cmd` | Seed and run a sandbox on its isolated ports |
| `sandbox/Update-Sandbox.cmd` | Merge the latest `master` into a sandbox branch |
| `sandbox/Promote-Sandbox.cmd` | Push a sandbox branch for review (never auto-merges) |
| `sandbox/Ship-Sandbox.cmd` | Sync, validate, and open the PR; `-Approve` also merges and discards the sandbox |
| `sandbox/Discard-Sandbox.cmd` | Remove a sandbox worktree, branch, and emulator database |
| `sandbox/List-Sandboxes.cmd` | List active sandboxes and their ports |
| `parked/Recycle-Sandbox.cmd` | Parked, not wired into any flow: reuse a shipped sandbox instead of creating one |
| `canary/Deploy-Canary.cmd` | Launch `infra/deploy-canary.ps1` to build, push, deploy, and smoke the current SHA on canary |
| `prod/Deploy-Prod.cmd` | Launch `infra/deploy-prod.ps1`, which still requires the typed `APPROVE_PROD_DEPLOYMENT` gate |
| `prod/Rollback-Prod.cmd` | Launch `infra/rollback-prod.ps1` to activate the previous production revision |

Every entry point above writes its latest run to
`<primary-checkout>/logs/last-run/<name>.log`, overwritten each run, next to an
append-only `runs.log` index. Any lane, worker, or sandbox reads the same files,
so the last run of any script can be debugged from anywhere. Each log opens with
a `[time]` start stamp and closes with the outcome and elapsed time.

A transcript only records what PowerShell itself writes, so an unpiped native
process (`docker`, `az`, `npm`) writes past it to the console and leaves nothing
in the log. Run long external tools through `Invoke-LoggedNative` from
`dev/lib/run-log.ps1`, which streams both output streams through PowerShell and
records the command, exit code, and duration.

Keep root-level scripts that are direct setup, diagnostic, smoke, or data utility
entry points. Put implementation and source-control workflow under `dev/`,
regular owner-facing launchers under `user/`, sandbox launchers under
`sandbox/`, and the hosted deployment launchers under `canary/` and `prod/`.
Do not move cloud-mutating
operations out of `infra/` merely because they are implemented in PowerShell;
`canary/` and `prod/` hold only launchers for the gated scripts that live there.
