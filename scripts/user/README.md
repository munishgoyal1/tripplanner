# User Commands

This folder contains the regular owner-facing launchers. Their implementation
stays under `scripts/dev/` so everyday commands remain easy to find.

| Command | Purpose |
| --- | --- |
| `Sync-Latest.cmd` | Synchronize committed code into only the launcher worktree |
| `Run-Latest.cmd` | Synchronize the launcher worktree, then start its local stack |

Run `Sync-Latest.cmd all` from a worker to include committed sibling worktree
changes through `master`. Without `all`, a worker receives only `master`; Agent 3
always integrates all committed worker heads.
