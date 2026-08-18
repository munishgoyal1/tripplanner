# Sandbox development

Use the primary `tripplanner` checkout on `master` and a fresh, task-named sandbox for each isolated feature or UX Lab. A sandbox starts from `origin/master`, carries one coherent change, and returns only through its validated promotion flow.

Create a sandbox from the primary checkout:

```powershell
.\scripts\user\sandbox\New-Sandbox.cmd route-cache-fix "Route cache correction" -NoOpen
.\scripts\user\sandbox\Serve-Sandbox.cmd route-cache-fix
.\scripts\user\sandbox\Promote-Sandbox.cmd route-cache-fix
```

On macOS, use the matching `.command` launchers under `scripts/mac/user/sandbox/`. Each sandbox has an isolated worktree, branch, port slot, and local emulator database. `Update-Sandbox` merges current `origin/master` into an in-flight sandbox. Promotion is the only path from sandbox code into `master`.

`Rename-Sandbox <sandbox> <new-name>` changes only the name part of a sandbox.
Its branch, worktree folder, and database name follow, while the number keeps its
ports, so a new name may repeat the number but cannot change it. Renaming
requires the sandbox to be stopped and conflict-free, publishes the new branch
before deleting the old one, and leaves the previous emulator database in place —
the renamed sandbox seeds a fresh one on its next run.

`Merge-Sandbox` lands finished work without ending the lane. It runs the same
validation, pull request, merge, and verification steps as promotion, then
resynchronizes the sandbox onto the updated base and leaves it registered and
active. Nothing is discarded, no promotion is recorded, and UX Lab records are
untouched. It fetches the latest base before syncing and again after the pull
request lands, and runs the sandbox conflict resolver automatically on both
syncs, so a conflict git can already settle never stalls the merge. Use it when a
sandbox has more work ahead of it; use `Promote-Sandbox` when the lane is
finished.

The primary checkout owns the canonical local app stack. Before starting it, run `scripts/win/user/Run-Latest-Master.cmd` on Windows or `scripts/mac/user/Run-Latest-Master.command` on macOS. Sandboxes use their own ports and server-free validation by default.

Promotion requires the primary `master` checkout to be clean and exactly equal
to `origin/master` before the pull request is merged. After GitHub merges the
pull request, promotion fast-forwards the primary checkout before recording
completion or discarding the sandbox. A stale or locally-ahead primary checkout
stops the promotion instead of creating a divergent history.

After a successful `Sync-Sbxs-FromMaster`, each registered sandbox may be ahead of
`master`, but both its local branch and its pushed remote branch must contain the
exact current `master` commit. The sync commands verify this ancestry invariant
before reporting success.

`Full-2Way-Sync` keeps active work visible. It never stashes a dirty worktree:
incoming committed history is preflighted without changing files, then merged
only when it does not overlap the lane's uncommitted paths. An overlap leaves the
worktree untouched and names the paths. A dirty lane can take and push current
`master`, but its own commits are not published to `master` until its active
iteration is committed or finished.

`Sync-Across-MasterSbx` is the rare counterpart that also sends work the other
way: it merges each sandbox into `master` through the same `-Merge` gates, then
brings all sandboxes back up to the resulting `master`. Both commands default to
every registered sandbox and accept a sandbox number, slug, or short name to
narrow the merge to one lane. Because it publishes sandbox work, it refuses to
run while any targeted sandbox holds uncommitted work or unresolved conflicts,
prints the exact commits each sandbox would land, and then requires the phrase
`APPROVE_SANDBOX_TO_MASTER`. Use it only when those sandboxes are known to be
feature-clean; the routine refresh remains one-way.

If `Update-Sandbox` reports `SANDBOX_CONFLICT_PENDING`, resolve its marked files
in the sandbox worktree, then run `Resolve-SandboxConflicts` for that sandbox to
finish the merge and push its branch before retrying update or promotion.
If a retained safety stash restore conflicts, resolve the marked files first;
the same resolver preserves the applied local changes and clears only the stale
stash record before the next sync.

Discard a sandbox after verified promotion.
