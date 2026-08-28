# Sandbox development

Use the primary `tripplanner` checkout on `master` and a fresh, task-named sandbox for each isolated feature or UX Lab. A sandbox starts from `origin/master`, carries one coherent change, and returns only through its validated promotion flow.

An in-chat sandbox fix stays in that sandbox and does not need a GitHub issue.
Issue creation is reserved for work the owner explicitly puts on the issue board,
deterministic trip-audit findings, specific tracked audit runs, and known work
intentionally parked for later. If an issue already exists, claim and update it;
do not manufacture one for work the current sandbox chat is already completing.

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

The primary checkout owns the canonical local app stack. Before starting it, run `scripts/win/user/run/Run-Latest-Master.cmd` on Windows or `scripts/mac/user/run/Run-Latest-Master.command` on macOS. Sandboxes use their own ports and server-free validation by default.

Promotion requires the primary `master` checkout to be clean and exactly equal
to `origin/master` before the pull request is merged. After GitHub merges the
pull request, promotion fast-forwards the primary checkout before recording
completion or discarding the sandbox. A stale or locally-ahead primary checkout
stops the promotion instead of creating a divergent history.

After a successful `Sync-Sbxs-FromMaster`, each registered sandbox may be ahead of
`master`, but both its local branch and its pushed remote branch must contain the
exact current `master` commit. The sync commands verify this ancestry invariant
before reporting success.

`Publish-Coordinator` runs that synchronization automatically after Coordinator
work merges to `master`. The trigger is publication rather than a timer, so active
sandboxes learn about every Coordinator landing without periodic background
mutations. A lane that cannot merge cleanly is reported and left for explicit
resolution; its uncommitted files are never stashed or rewritten.

`Full-2Way-Sync` keeps active work visible and defaults to every local branch,
including registered sandboxes, multiagent worktrees, and standalone branches
without an attached worktree. Pass `sbx` to retain the registered-sandbox-only
scope. It never stashes a dirty worktree: incoming committed history is
preflighted without changing files, then merged only when it does not overlap the
lane's uncommitted paths. An overlap leaves the worktree untouched and names the
paths. A dirty lane can take and push current `master`, but its own commits are
not published to `master` until its active iteration is committed or finished.
When committed histories conflict, the full sync invokes the shared conflict
resolver for registered sandboxes, multiagent worktrees, and temporary
standalone-branch worktrees. It replays only resolutions already recorded by
Git `rerere`; genuinely new conflicts remain visible in attached worktrees, or
are aborted in temporary worktrees and reported for manual resolution.

`Resolve-All-Recorded-Conflicts` is the manual recovery command when several
attached lanes are already stopped in pending merges. It scans the primary,
sandbox, multiagent, and standalone-branch worktrees, finishes every merge
covered by a recorded `rerere` resolution, continues past genuinely new
conflicts, and summarizes what still needs a person. It does not fetch, initiate
or abort merges, or push branches. An unattached branch cannot retain an
in-progress merge; check it out into a worktree before using this command.

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

Discard a sandbox after verified promotion. Before dropping its emulator database,
discard saves the lane's trips and newly warmed places into the global corpus and
publishes a scoped corpus commit on `master`; successful discard must not leave
those retained files as unexplained local changes.
