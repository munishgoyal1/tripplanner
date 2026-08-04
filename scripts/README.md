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
| `dev/sandbox.ps1` | Create, run, update, promote, ship, recycle, discard, or list isolated feature sandboxes |
| `dev/sandbox_seed.py` | Seed, drop, or capture data for a sandbox emulator database |
| `dev/ui-snapshot.ps1` | Preserve or inspect accepted UI tags |
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
| `sandbox/Ship-Sandbox.cmd` | Sync, validate, and open the PR; `-Approve` also merges and parks the sandbox |
| `sandbox/Recycle-Sandbox.cmd` | Claim the parked sandbox under a new slug, keeping its installed dependencies |
| `sandbox/Discard-Sandbox.cmd` | Remove a sandbox worktree, branch, and emulator database |
| `sandbox/List-Sandboxes.cmd` | List active sandboxes and their ports |
| `canary/Deploy-Canary.cmd` | Launch `infra/deploy-canary.ps1` to build, push, deploy, and smoke the current SHA on canary |
| `prod/Deploy-Prod.cmd` | Launch `infra/deploy-prod.ps1`, which still requires the typed `APPROVE_PROD_DEPLOYMENT` gate |
| `prod/Rollback-Prod.cmd` | Launch `infra/rollback-prod.ps1` to activate the previous production revision |

Keep root-level scripts that are direct setup, diagnostic, smoke, or data utility
entry points. Put implementation and source-control workflow under `dev/`,
regular owner-facing launchers under `user/`, sandbox launchers under
`sandbox/`, and the hosted deployment launchers under `canary/` and `prod/`.
Do not move cloud-mutating
operations out of `infra/` merely because they are implemented in PowerShell;
`canary/` and `prod/` hold only launchers for the gated scripts that live there.
