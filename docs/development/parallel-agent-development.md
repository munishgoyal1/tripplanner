# Sandbox development

Use the primary `tripplanner` checkout on `master` and a fresh, task-named sandbox for each isolated feature or UX Lab. A sandbox starts from `origin/master`, carries one coherent change, and returns only through its validated promotion flow.

Create a sandbox from the primary checkout:

```powershell
.\scripts\sandbox\New-Sandbox.cmd route-cache-fix "Route cache correction" -NoOpen
.\scripts\sandbox\Serve-Sandbox.cmd route-cache-fix
.\scripts\sandbox\Promote-Sandbox.cmd route-cache-fix
```

On macOS, use the matching `.command` launchers under `scripts/mac/sandbox/`. Each sandbox has an isolated worktree, branch, port slot, and local emulator database. `Update-Sandbox` merges current `origin/master` into an in-flight sandbox. Promotion is the only path from sandbox code into `master`.

The primary checkout owns the canonical local app stack. Before starting it, run `scripts/user/Run-Latest.cmd` on Windows or `scripts/mac/user/Run-Latest.command` on macOS. Sandboxes use their own ports and server-free validation by default.

If `Update-Sandbox` reports `SANDBOX_CONFLICT_PENDING`, resolve its marked files
in the sandbox worktree, then run `Resolve-SandboxConflicts` for that sandbox to
finish the merge and push its branch before retrying update or promotion.

Discard a sandbox after verified promotion.