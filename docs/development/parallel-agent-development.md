# Optional parallel coding-agent development

The default workflow uses one VS Code window in the primary `tripplanner`
checkout and works directly on `master`. Use this parallel workflow only when
the owner explicitly requests concurrent assignments. In that mode, `worker-1`
is the development lane, the primary checkout is the review/integration lane,
and `worker-2` remains optional capacity.

## Persistent agent windows

The standard slots are:

| Role | Worktree | Branch | Workspace launcher |
|---|---|---|---|
| Agent 1 - Development | `C:\repos\tripplanner.worktrees\worker-1` | `agents/worker-1` | `tripplanner-worker-1.code-workspace` |
| Agent 3 - Review & Integration | `C:\repos\tripplanner` | `master` | `tripplanner-integration.code-workspace` |
| Agent 2 - Worker (optional) | `C:\repos\tripplanner.worktrees\worker-2` | `agents/worker-2` | `tripplanner-worker-2.code-workspace` |

The workspace launchers give each window a distinct title and color. Always
confirm the branch in the status bar before committing or merging.

When parallel mode is requested, double-click `Open-Tripplanner-Agents.cmd` from the
repository or the `Tripplanner Agent Windows` Desktop shortcut. The command
resolves the primary checkout through Git, verifies the default Agent 1 and
Agent 3 workspaces, and opens them in separate VS Code windows. VS Code restores
the last window position, editor groups and tabs, cursor/scroll state, undo
history, and terminal sessions for each workspace. The committed workspace
settings keep the primary sidebar on the left and the terminal panel on the
right. Machine-level `window.restoreWindows=all` and
`files.hotExit=onExitAndWindowClose` retain all windows and unsaved editor
buffers across a normal restart.

The launcher does not restart active dev servers or commands after a machine
reboot. Restored terminals retain their shell context, but restart the local
stack explicitly from its one designated worktree so multiple windows do not
compete for ports `5173` and `8000`.

The equivalent PowerShell command, including a validation-only mode, is:

```powershell
.\scripts\open-agent-windows.ps1
.\scripts\open-agent-windows.ps1 -WhatIf
.\scripts\open-agent-windows.ps1 -IncludeWorker2
```

Double-click `Open-Tripplanner-All-Agents.cmd` for the equivalent optional
three-window launch.

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

For the persistent Agent 1 lane, use either one-click entry point from the
primary integration checkout:

- VS Code: **Tasks: Run Task** → **Tripplanner: Merge Agent 1**
- File Explorer: double-click `scripts/dev/Merge-Agent1.cmd`

Both run `scripts/dev/merge-agent-1.ps1`, which refuses dirty or unexpected worktrees,
creates or reuses the Worker 1 pull request, merges it with a merge commit,
updates `master`, and keeps the persistent Worker 1 branch synchronized for
its next assignment. If the task stops on a conflict, return to the Worker 1
window, ask that agent to resolve and validate it, then run the task again.

In optional parallel mode, to merge Agent 1 and immediately restart the local application on the merged
code, use **Tasks: Run Task** → **Tripplanner: Run Latest Code** or double-click
`scripts/dev/Run-Latest-Code.cmd`. This is the regular local workflow even
when `master` has staged, unstaged, or untracked work: it temporarily stashes the
local state, runs the guarded merge against a clean checkout, restores the local
state with its staged status, and then starts `scripts/dev/dev-spa.ps1`. If restored
changes overlap the merged code, it stops with the stash retained for explicit
conflict resolution. The direct **Merge Agent 1** command remains clean-only.

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
