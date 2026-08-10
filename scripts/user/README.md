# User Commands

This folder contains the regular owner-facing launchers. Their implementation
stays under `scripts/dev/` so everyday commands remain easy to find.
Windows launchers live here; matching macOS launchers live under
`scripts/mac/user/` with the same base name and a `.command` extension.

| Command | Purpose |
| --- | --- |
| `Start-Dev-Spa.cmd` | Start the local app stack without synchronizing code first |
| `Run-Latest.cmd` | Fast-forward primary `master` from `origin/master`, then start its local stack; optional dev SPA flags are forwarded |
| `Sync-MeTo-Latest.cmd <sandbox>` | Fast-forward primary `master`, then update one sandbox from it |
| `Sync-AllTo-Latest.cmd` | Fast-forward primary `master`, then update every registered sandbox from it |
| `sandbox/Resolve-SandboxConflicts.cmd <sandbox>` | Finish a manually resolved sandbox merge and push its branch |
| `Show-Prompts.cmd` | Read the master owner prompt log |

`Run-Latest.cmd` is only for the primary `master` checkout. It fast-forwards
from `origin/master` and accepts every optional `dev-spa.ps1` parameter:

```cmd
Run-Latest.cmd
Run-Latest.cmd -Watch -NoLabs
```

For an isolated feature, use the sandbox launchers. On macOS, run the
corresponding primary launcher from the repository root:

```bash
./scripts/mac/user/Run-Latest.command
./scripts/mac/user/Run-Latest.command -Watch -NoLabs
./scripts/mac/user/Sync-MeTo-Latest.command 2
./scripts/mac/user/Sync-AllTo-Latest.command
```

When `Update-Sandbox` stops on a semantic merge conflict, resolve the marked
files in that sandbox, then run `scripts/user/sandbox/Resolve-SandboxConflicts.cmd <sandbox>`
on Windows or `scripts/mac/user/sandbox/Resolve-SandboxConflicts.command <sandbox>` on macOS.
