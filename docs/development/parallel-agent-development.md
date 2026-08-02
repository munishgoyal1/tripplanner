# Optional parallel coding-agent development

The default workflow uses one VS Code window in the primary `tripplanner`
checkout and works directly on `master`. Use this parallel workflow only for
clear, sizeable, isolated features when the owner explicitly requests concurrent
assignments. In that mode, `worker-1` and `worker-2` are separate development
lanes and the primary checkout is the review/integration lane.

## Persistent agent windows

The standard slots are:

| Role | Worktree | Branch | Workspace launcher |
|---|---|---|---|
| Agent 1 - Development | `C:\repos\tripplanner.worktrees\worker-1` | `agents/worker-1` | `tripplanner-worker-1.code-workspace` |
| Agent 2 - Development | `C:\repos\tripplanner.worktrees\worker-2` | `agents/worker-2` | `tripplanner-worker-2.code-workspace` |
| Agent 3 - Review & Integration | `C:\repos\tripplanner` | `master` | `tripplanner-integration.code-workspace` |

The workspace launchers give each window a distinct title and color. Always
confirm the branch in the status bar before committing or merging.

When parallel mode is requested, double-click `Open-Tripplanner-All-Agents.cmd`
from the repository. The command resolves the primary checkout through Git,
verifies both worker workspaces plus the integration workspace, and opens them
in separate VS Code windows. VS Code restores
the last window position, editor groups and tabs, cursor/scroll state, undo
history, and terminal sessions for each workspace. The committed workspace
settings keep the primary sidebar on the left and the terminal panel on the
right. Machine-level `window.restoreWindows=all` and
`files.hotExit=onExitAndWindowClose` retain all windows and unsaved editor
buffers across a normal restart.

The launcher does not restart active dev servers or commands after a machine
reboot. Agent 3 owns the local stack from the primary worktree so multiple
windows do not compete for ports `5173` and `8000`. Workers 1 and 2 must not
start, stop, or restart it unless the owner explicitly approves that action.

The equivalent PowerShell command, including a validation-only mode, is:

```powershell
.\scripts\open-agent-windows.ps1 -IncludeWorker2
.\scripts\open-agent-windows.ps1 -IncludeWorker2 -WhatIf
```

Create the worker slots once from the primary checkout:

```powershell
.\scripts\agent-worktree.ps1 -Create worker-1 -NoOpen
.\scripts\agent-worktree.ps1 -Create worker-2 -NoOpen
code --new-window .\tripplanner-worker-1.code-workspace
code --new-window .\tripplanner-worker-2.code-workspace
```

Keep the worktree folders and their isolated dependencies between assignments.
After Agent 3 merges a worker PR, synchronize that worker before assigning new
work:

```powershell
git fetch origin
git merge origin/master
git push
```

If GitHub deleted the remote worker branch after merge, use
`git push -u origin HEAD` instead. Each new assignment still gets its own PR;
the persistent branch name identifies the worker slot, not the feature.

## Additional temporary agent window

From any tripplanner checkout:

```powershell
.\scripts\agent-worktree.ps1 -Create route-cache-fix
```

This creates:

- branch `agents/route-cache-fix` from the latest `origin/master`
- worktree `C:\repos\tripplanner.worktrees\route-cache-fix`
- a new VS Code window rooted at that worktree
- a local copy of the primary checkout's ignored `.env`, when present

Use a short task-oriented name. List or reopen agent worktrees with:

```powershell
.\scripts\agent-worktree.ps1
.\scripts\agent-worktree.ps1 -Open route-cache-fix
```

Each worktree has isolated ignored files and dependencies. Do not share
`.venv` across worktrees because its editable install can resolve code from the
wrong checkout. Do not share `node_modules` when an agent might change package
locks. Before that worktree needs to validate code, initialize it with:

```powershell
.\scripts\setup-dev-machine.ps1 -SkipToolInstall
```

Do not run the normal dev stack in multiple worktrees simultaneously: the
default frontend, backend, and local Cosmos ports are shared. Agents can edit
and run targeted tests independently; use one designated window for interactive
app testing.

## Give each agent a narrow assignment

In each new window, start a separate coding-agent session and state:

1. the exact feature or fix and acceptance criteria
2. the files or subsystem it owns
3. nearby work owned by other agents that it must not edit
4. the smallest required validation
5. that it must commit and push `agents/<name>` when complete

Prefer independent file ownership. If two tasks must substantially edit the same
module or contract, sequence them instead of running them in parallel.

## Merge checkpoints

The agent finishes its branch with a coherent commit and push. From that
worktree:

```powershell
git push -u origin HEAD
gh pr create --base master --head agents/route-cache-fix --fill
```

To synchronize both persistent agent lanes, use either one-click entry point from
the primary integration checkout:

- VS Code: **Tasks: Run Task** → **Tripplanner: Sync All Worktrees**
- File Explorer: double-click `scripts/dev/Sync-All-Worktrees.cmd`

Both use the shared guarded integration engine. The sync command refuses dirty or
unexpected worktrees, preflights both
before either merge, and enables Git `rerere` so a previously validated conflict
resolution is reused automatically. For a new semantic conflict, it pauses in the
named worker worktree, reports the exact paths, and waits for `RESOLVED` after the
owner or worker reconciles and validates both changes. It rejects remaining conflict
markers, records the resolution for future reuse, commits it on the worker branch,
and resumes integration. `ABORT` restores the worker to its clean pre-merge state.
It never applies blanket ours/theirs conflict choices. The engine then creates or
reuses each worker's pull request, merges Worker 1 with a merge commit, updates
`master`, brings Worker 2 onto that new baseline, and merges Worker 2 separately.
Finally, it fast-forwards both persistent workers to the resulting `master`, so
all three worktrees finish synchronized for their next assignments.
Independent dated additions to
`PRD/REQUIREMENTS Auto Log.txt` use Git's union merge driver because that file is
append-only; both branches' entries are retained.

To synchronize only one lane, double-click `scripts/dev/Sync-Worker-1.cmd` or
`scripts/dev/Sync-Worker-2.cmd`. For validation-only preflights, run
`sync-worker.ps1 -WorkerNumber 1 -ValidateOnly` (or worker 2), or run
`.\scripts\dev\sync-all-worktrees.ps1 -ValidateOnly` for both. The `.cmd`
worker launchers call the generic `sync-worker.ps1` engine with the corresponding
worker number. `Sync-All-Worktrees.cmd -ValidateOnly` forwards the validation flag
to its shared engine.

In parallel mode, to synchronize all worktrees and immediately restart the local
application on the merged code, use **Tasks: Run Task** → **Tripplanner: Run Latest Code** or double-click
`scripts/dev/Run-Latest-Code.cmd`. This is the regular local workflow even
when `master` has staged, unstaged, or untracked work: it temporarily stashes the
local state, runs both guarded merges against a clean checkout, restores the local
state with its staged status, and then starts `scripts/dev/dev-spa.ps1`. If restored
changes overlap the merged code, it stops with the stash retained for explicit
conflict resolution. The direct **Sync All Worktrees** command remains clean-only.

Use a pull request for each optional worker branch. It provides one diff and
check surface, keeps `master` stable, and makes parallel integration order
explicit. Review and merge one ready branch at a time from the primary checkout.
Pass the PR number explicitly so GitHub CLI does not try to switch the feature
worktree to `master`:

```powershell
Set-Location C:\repos\tripplanner
gh pr merge 123 --merge --delete-branch
```

Use merge commits rather than squash merges so the cleanup helper can prove that
the local branch is contained in `origin/master`. After each checkpoint, every
still-active agent should incorporate the new integration baseline from its own
worktree:

```powershell
git fetch origin
git merge origin/master
git push
```

Resolve conflicts in the feature worktree, rerun the affected validation, and
push the resolution. Never resolve a feature conflict by making speculative
edits directly on `master`.

## Clean up merged work

After the PR is merged:

```powershell
.\scripts\agent-worktree.ps1 -Remove route-cache-fix
```

The helper refuses cleanup when the worktree is dirty or its branch is not an
ancestor of `origin/master`. Add `-DeleteRemoteBranch` only when GitHub did not
already delete the remote branch.

## Voice instructions in VS Code

Voice is only an input method for the VS Code coding-agent chat; it is not a
tripplanner application feature.

Install the official Microsoft extension once:

```powershell
code --install-extension ms-vscode.vscode-speech
```

On Windows:

- `Ctrl+I`: start voice chat from anywhere in VS Code
- hold `Ctrl+I`, speak, then release: submit in walkie-talkie mode
- `Ctrl+Alt+V`: dictate into the focused editor or rich text field
- `Escape`: stop dictation or speech playback

VS Code Speech performs recognition locally and does not send recordings to an
online speech service. `accessibility.voice.speechTimeout` controls the pause
before a chat prompt is automatically submitted; set it to `0` to disable
automatic submission.
