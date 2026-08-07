# User Commands

This folder contains the regular owner-facing launchers. Their implementation
stays under `scripts/dev/` so everyday commands remain easy to find.
Windows launchers live here; matching macOS launchers live under
`scripts/mac/user/` with the same base name and a `.command` extension.

| Command | Purpose |
| --- | --- |
| `Sync-MeTo-Latest.cmd` | Synchronize committed code into only the launcher worktree |
| `Sync-AllTo-Latest.cmd` | Integrate committed code, then synchronize MasterAgent and all three worker worktrees |
| `Start-Dev-Spa.cmd` | Start the local app stack without synchronizing code first |
| `Run-Latest.cmd` | Synchronize the launcher worktree, then start its local stack; optional dev SPA flags are forwarded |
| `Run-Worker-Latest.cmd <1\|2\|3>` | Merge only that worker into `master` without tests, then restart the canonical master stack |
| `Show-Prompts.cmd` | Read the owner prompt log back across all agent lanes, newest first |

By default, `Sync-MeTo-Latest.cmd` integrates all committed worker heads through
`master`, then updates only the launcher worktree. Pass `onlyfrommaster` to receive
the latest committed `master` without integrating sibling worktrees.

Run `Sync-AllTo-Latest.cmd` from MasterAgent or Agents 1-3 when every
worktree should receive the integrated `master`. Each worktree's staged,
unstaged, and untracked files are preserved in an exact safety stash. Git
`rerere` automatically reuses a previously recorded resolution; a new semantic
conflict retains the safety stash, reports the affected path, and does not stop
the other independent worktrees from being attempted.

`Run-Latest.cmd` keeps its no-argument behavior and accepts every optional
`dev-spa.ps1` parameter. Pass `all` (or `-All`) to invoke the existing
all-worktree synchronization before starting the stack:

```cmd
Run-Latest.cmd
Run-Latest.cmd -Watch -NoLabs
Run-Latest.cmd all -Watch
```

`Run-Latest.cmd` acts on the checkout that launches it. Run it from MasterAgent
for the canonical master stack; a worker copy syncs and runs that worker checkout.
For the deliberate fast path that publishes one known worker and refreshes master,
use:

```cmd
Run-Worker-Latest.cmd 2
```

This skips integration tests and does not update the other workers or sandboxes.
It still preserves Git conflict handling and refuses an invalid worker number.

On macOS, run the corresponding launcher from the repository root:

```bash
./scripts/mac/user/Run-Latest.command
./scripts/mac/user/Run-Latest.command -Watch -NoLabs
./scripts/mac/user/Run-Latest.command all -Watch
./scripts/mac/user/Run-Worker-Latest.command 2
```
