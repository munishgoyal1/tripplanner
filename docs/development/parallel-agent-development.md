# Sandbox-first coding-agent development

The active workflow uses the primary `tripplanner` checkout on `master` and a
fresh, task-named sandbox for each isolated feature or UX Lab. A sandbox starts
from `origin/master`, carries one coherent change, and returns only through its
validated promotion flow. Fixed worker lanes are retired from active development.

## Active workflow

Create a sandbox from the primary checkout:

```powershell
.\scripts\sandbox\New-Sandbox.cmd route-cache-fix "Route cache correction" -NoOpen
.\scripts\sandbox\Serve-Sandbox.cmd route-cache-fix
.\scripts\sandbox\Promote-Sandbox.cmd route-cache-fix
```

On macOS, use the matching `.command` launchers under `scripts/mac/sandbox/`.
Each sandbox has an isolated worktree, branch, port slot, and local emulator
database. `Update-Sandbox` merges current `origin/master` into an in-flight
sandbox. Promotion is the only path from sandbox code into `master`.

The primary checkout owns the canonical local app stack. Before starting it,
run `scripts/user/Run-Latest.cmd` on Windows or
`scripts/mac/user/Run-Latest.command` on macOS. Sandboxes use their own ports
and server-free validation by default.

## Archived worker workflow

The last worker-enabled workflow is preserved remotely as the annotated tag and
remote branch `archive/drop-workersconcept-use-sandboxes`, both pointing to the
same baseline. From primary `master`, run:

```powershell
.\scripts\dev\restore-parallel-workers.ps1
```

The command fetches the archive tag and creates or reopens the detached worktree
`<primary>.worktrees/archive-parallel-workers`. It is for temporary reference or
an exceptional parallel session and never changes current `master`.

Do not merge the archive branch into a newer `master`. If fixed worker lanes ever
become a permanent need again, create a new branch from current `master` and
selectively modernize the required worker scripts against the archive reference.
