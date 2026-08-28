# User Commands

This folder contains the regular owner-facing launchers. Their implementation
stays under `scripts/dev/` so everyday commands remain easy to find.
Windows launchers are grouped by purpose; matching macOS launchers use the same
subfolder and base name under `scripts/mac/user/`, with a `.command` extension.
Every launcher listed under `run/`, `sync/`, `google/`, and `azure/` accepts `help` or `?`
as its first argument and exits after printing usage. On macOS zsh, use `help`
or quote the wildcard as `'?'` so the shell passes it to the launcher.

| Command | Purpose |
| --- | --- |
| `run/Start-Dev-Spa.cmd` | Start the local app stack without synchronizing code first |
| `run/Run-Latest-Master.cmd` | Fast-forward primary `master` from `origin/master`, then start its local stack; optional dev SPA flags are forwarded |
| `google/Google-Places-Control.cmd disable prod` | Immediately disable paid Places in GCP without deploying; status, guarded enable, and profile apply are also supported |
| `google/Google-Maps-Control.cmd disable prod` | Disable Maps JavaScript, Routes, and Static Maps in GCP without deploying; status, guarded enable, and profile apply are also supported |
| `azure/Azure-Services-Control.cmd status` | Report all allowlisted Tripplanner Azure services; guarded disable stops hosted callers and blocks service access, while guarded enable restores them |
| `sync/Sync-Sbxs-FromMaster.cmd [sandbox]` | Fast-forward primary `master`, then update every registered sandbox or only the selected sandbox |
| `sync/Full-2Way-Sync.cmd [all\|sbx]` | Converge all local lanes and automatically replay recorded conflict resolutions without hiding active edits |
| `sync/Resolve-All-Recorded-Conflicts.cmd` | Scan all attached worktrees and finish pending merges covered by recorded resolutions; report new conflicts without aborting them |
| `sync/Sync-Across-MasterSbx.cmd [sandbox]` | Rare, gated cross-lane sync: merge every sandbox into `master`, or merge one selected sandbox, then refresh all sandboxes. Requires typing `APPROVE_SANDBOX_TO_MASTER` |
| `sandbox/Resolve-SandboxConflicts.cmd <sandbox>` | Finish a manually resolved sandbox merge and push its branch |
| `sandbox/Rename-Sandbox.cmd <sandbox> <new-name>` | Rename a sandbox, keeping its number and ports |
| `sandbox/Merge-Sandbox.cmd <sandbox>` | Merge the sandbox into `master` and resynchronize it, keeping the sandbox active |
| `Show-Prompts.cmd` | Read the master owner prompt log |

`Run-Latest-Master.cmd` is only for the primary `master` checkout. It fast-forwards
from `origin/master` and accepts every optional `dev-spa.ps1` parameter:

```cmd
run\Run-Latest-Master.cmd
run\Run-Latest-Master.cmd -Watch -NoLabs
```

For an isolated feature, use the sandbox launchers. On macOS, run the
corresponding primary launcher from the repository root:

```bash
./scripts/mac/user/run/Run-Latest-Master.command
./scripts/mac/user/run/Run-Latest-Master.command -Watch -NoLabs
./scripts/mac/user/sync/Sync-Sbxs-FromMaster.command 2
./scripts/mac/user/sync/Sync-Sbxs-FromMaster.command
```

A successful sync guarantees that every registered sandbox branch, both local
and pushed remote, contains the current `master` commit. A sandbox can be ahead
of `master` with its own feature commits; it must never be behind it.

Run `Resolve-All-Recorded-Conflicts.cmd` when several lanes are already stopped
in merge conflicts. It checks the primary checkout and every attached sandbox,
multiagent, and standalone-branch worktree, then finishes only merges Git
`rerere` already knows how to resolve. It does not fetch, start or abort merges,
or push branches. A local branch without an attached worktree cannot hold an
in-progress merge and therefore has nothing for this recovery command to scan.

When `Update-Sandbox` stops on a semantic merge conflict, resolve the marked
files in that sandbox, then run `scripts/win/user/sandbox/Resolve-SandboxConflicts.cmd <sandbox>`
on Windows or `scripts/mac/user/sandbox/Resolve-SandboxConflicts.command <sandbox>` on macOS.
