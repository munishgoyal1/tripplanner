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
| `dev/ui-snapshot.ps1` | Preserve or inspect accepted UI tags |
| `dev/start-cosmos-emulator.ps1` | Start or verify the local Cosmos emulator |
| `dev/check-local-cosmos.ps1` | Report the local emulator connection coordinates |
| `user/Sync-MeTo-Latest.cmd` | Synchronize committed code into the launcher worktree |
| `user/All-SyncTo-Latest.cmd` | Integrate committed code, then synchronize master and both workers |
| `user/Run-Latest.cmd` | Owner-facing synchronize-and-run launcher |

Keep root-level scripts that are direct setup, diagnostic, smoke, or data utility
entry points. Put implementation and source-control workflow under `dev/`, and
regular owner-facing launchers under `user/`. Do not move cloud-mutating
operations out of `infra/` merely because they are implemented in PowerShell.
