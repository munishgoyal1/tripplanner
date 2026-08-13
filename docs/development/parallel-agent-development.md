# Sandbox development

Use the primary `tripplanner` checkout on `master` and a fresh, task-named sandbox for each isolated feature or UX Lab. A sandbox starts from `origin/master`, carries one coherent change, and returns only through its validated promotion flow.

Create a sandbox from the primary checkout:

```powershell
.\scripts\user\sandbox\New-Sandbox.cmd route-cache-fix "Route cache correction" -NoOpen
.\scripts\user\sandbox\Serve-Sandbox.cmd route-cache-fix
.\scripts\user\sandbox\Promote-Sandbox.cmd route-cache-fix
```

On macOS, use the matching `.command` launchers under `scripts/mac/user/sandbox/`. Each sandbox has an isolated worktree, branch, port slot, and local emulator database. `Update-Sandbox` merges current `origin/master` into an in-flight sandbox. Promotion is the only path from sandbox code into `master`.

The primary checkout owns the canonical local app stack. Before starting it, run `scripts/user/Run-Latest-Master.cmd` on Windows or `scripts/mac/user/Run-Latest-Master.command` on macOS. Sandboxes use their own ports and server-free validation by default.

Promotion requires the primary `master` checkout to be clean and exactly equal
to `origin/master` before the pull request is merged. After GitHub merges the
pull request, promotion fast-forwards the primary checkout before recording
completion or discarding the sandbox. A stale or locally-ahead primary checkout
stops the promotion instead of creating a divergent history.

After a successful `Sync-Latest-FromRemoteMaster`, each registered sandbox may be ahead of
`master`, but both its local branch and its pushed remote branch must contain the
exact current `master` commit. The sync commands verify this ancestry invariant
before reporting success.

If `Update-Sandbox` reports `SANDBOX_CONFLICT_PENDING`, resolve its marked files
in the sandbox worktree, then run `Resolve-SandboxConflicts` for that sandbox to
finish the merge and push its branch before retrying update or promotion.
If a retained safety stash restore conflicts, resolve the marked files first;
the same resolver preserves the applied local changes and clears only the stale
stash record before the next sync.

Discard a sandbox after verified promotion.
