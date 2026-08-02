# User Commands

This folder contains the regular owner-facing launchers. Their implementation
stays under `scripts/dev/` so everyday commands remain easy to find.

| Command | Purpose |
| --- | --- |
| `Sync-MeTo-Latest.cmd` | Synchronize committed code into only the launcher worktree |
| `All-SyncTo-Latest.cmd` | Integrate committed code, then synchronize all three worktrees |
| `Start-Dev-Spa.cmd` | Start the local app stack without synchronizing code first |
| `Run-Latest.cmd` | Synchronize the launcher worktree, then start its local stack |

Run `Sync-MeTo-Latest.cmd all` from a worker to include committed sibling worktree
changes through `master`. Without `all`, a worker receives only `master`;
MasterAgent always integrates all committed worker heads.

Run `All-SyncTo-Latest.cmd` from MasterAgent, Agent 1, or Agent 2 when every
worktree should receive the integrated `master`. Each worktree's staged,
unstaged, and untracked files are preserved in an exact safety stash. Git
`rerere` automatically reuses a previously recorded resolution; a new semantic
conflict retains the safety stash, reports the affected path, and does not stop
the other independent worktrees from being attempted.
