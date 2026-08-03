# Optional parallel coding-agent development

The default workflow uses one VS Code window in the primary `tripplanner`
checkout and works directly on `master`. Use this parallel workflow only for
clear, sizeable, isolated features when the owner explicitly requests concurrent
assignments. In that mode, `worker-1`, `worker-2`, and `worker-3` are separate
development lanes and the primary checkout is the review/integration lane.

## Persistent agent windows

The standard slots are:

| Role | Worktree | Branch | Workspace launcher |
| --- | --- | --- | --- |
| Agent 1 - Iti-Map | `C:\repos\tripplanner.worktrees\worker-1` | `agents/worker-1` | `tripplanner-worker-1.code-workspace` |
| Agent 2 - Detail-Chat | `C:\repos\tripplanner.worktrees\worker-2` | `agents/worker-2` | `tripplanner-worker-2.code-workspace` |
| Agent 3 - Infra | `C:\repos\tripplanner.worktrees\worker-3` | `agents/worker-3` | `tripplanner-worker-3.code-workspace` |
| MasterAgent - Review & Integration | `C:\repos\tripplanner` | `master` | `tripplanner-integration.code-workspace` |

Agent 1 defaults to Itinerary, Map, and their shared focus/view-model contracts.
Agent 2 defaults to Details, Chat, and their assistant interaction contracts.
Agent 3 defaults to infrastructure, deployment, and operational tooling.
These are logical task-routing defaults, not hard code boundaries. MasterAgent
uses reserved integer `0`; workers use positive integer identities. Keep worker
branch names, worktree paths, and numeric script arguments stable. Assign
cross-area work explicitly and sequence overlapping edits when both domains
touch the same state or contract.

The workspace launchers give each window a distinct title and color. Always
confirm the branch in the status bar before committing or merging.

When parallel mode is requested, double-click `Open-Tripplanner-All-Agents.cmd`
from the repository. The command resolves the primary checkout through Git,
verifies all three worker workspaces plus the integration workspace, and opens them
in separate VS Code windows. VS Code restores
the last window position, editor groups and tabs, cursor/scroll state, undo
history, and terminal sessions for each workspace. The committed workspace
settings keep the primary sidebar on the left and the terminal panel on the
right. Machine-level `window.restoreWindows=all` and
`files.hotExit=onExitAndWindowClose` retain all windows and unsaved editor
buffers across a normal restart.

The launcher does not restart active dev servers or commands after a machine
reboot. MasterAgent owns the local stack from the primary worktree so multiple
windows do not compete for ports `5173` and `8000`. Workers 1, 2, and 3 must not
start, stop, or restart it unless the owner explicitly approves that action.

The equivalent PowerShell command, including a validation-only mode, is:

```powershell
.\scripts\open-agent-windows.ps1 -IncludeWorker2
.\scripts\open-agent-windows.ps1 -IncludeWorker2 -IncludeWorker3
.\scripts\open-agent-windows.ps1 -IncludeWorker2 -IncludeWorker3 -WhatIf
```

Create the worker slots once from the primary checkout:

```powershell
.\scripts\dev\agent-worktree.ps1 -Create worker-1 -NoOpen
.\scripts\dev\agent-worktree.ps1 -Create worker-2 -NoOpen
.\scripts\dev\agent-worktree.ps1 -Create worker-3 -NoOpen
code --new-window .\tripplanner-worker-1.code-workspace
code --new-window .\tripplanner-worker-2.code-workspace
code --new-window .\tripplanner-worker-3.code-workspace
```

Keep the worktree folders and their isolated dependencies between assignments.
After MasterAgent merges a worker PR, synchronize that worker before assigning new
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
.\scripts\dev\agent-worktree.ps1 -Create route-cache-fix
```

This creates:

- branch `agents/route-cache-fix` from the latest `origin/master`
- worktree `C:\repos\tripplanner.worktrees\route-cache-fix`
- a new VS Code window rooted at that worktree
- a local copy of the primary checkout's ignored `.env`, when present

Use a short task-oriented name. List or reopen agent worktrees with:

```powershell
.\scripts\dev\agent-worktree.ps1
.\scripts\dev\agent-worktree.ps1 -Open route-cache-fix
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

### Everyday synchronization

One location-aware launcher covers normal parallel work. Run the copy inside the
worktree that should receive all latest committed code; no lane number is needed.

```powershell
.\scripts\user\Sync-MeTo-Latest.cmd
.\scripts\user\Sync-MeTo-Latest.cmd onlymaster
```

From MasterAgent, it integrates committed local and remote worker heads into
`master`. From Agents 1-3, the no-argument command first integrates
every committed worker head through `master`, then merges that result into only
the launcher worktree. Pass `onlymaster` from any lane to receive the latest
committed `master` without integrating sibling worktrees. The internal merge engine
starts its disposable integration checkout directly from fetched `origin/master`,
then updates local `master` only when MasterAgent is the launcher.

Non-launcher worktrees are never stashed, checked out, reset, or otherwise modified.
Target worktree changes are temporarily stashed and restored with their staged
state. Git `rerere` attempts a previously validated merge resolution. A new
semantic conflict pauses, lists the exact paths and resolution worktree, and
waits for `RESOLVED` or `ABORT` rather than choosing blanket ours/theirs.
The internal merge engine uses its disposable integration worktree; the launcher
update engine keeps local changes in a safety stash until the merge finishes or
is aborted. Sibling code always reaches a worker through `master`; worker branches
are not merged directly into one another.
Independent dated additions to
`docs/reference/history/requirements-log.txt` use Git's union merge driver because that file is
append-only; both branches' entries are retained.

To intentionally synchronize every worktree from MasterAgent or Agents 1-3
launcher, run:

```powershell
.\scripts\user\Sync-AllTo-Latest.cmd
```

This first integrates committed heads through `master`, then updates MasterAgent,
Agents 1, 2, and 3 independently. Each lane's staged, unstaged, and untracked
files are preserved in an exact safety stash. Git `rerere` automatically applies
a previously recorded resolution. A novel local-edit conflict retains that
lane's stash, lists its unresolved paths, and allows the other lanes to continue;
the command exits nonzero after reporting every lane requiring attention. A novel
conflict while integrating committed heads must still be resolved before one
authoritative `master` can be distributed. The script never guesses with blanket
ours/theirs conflict resolution.

In parallel mode, to synchronize the launcher worktree and immediately restart
the local application on the merged code, use **Tasks: Run Task** →
**Tripplanner: Run Latest** or double-click
`scripts/user/Run-Latest.cmd`. It runs location-aware `Sync Latest`, preserves
and restores each affected worktree's local state, and then starts the existing
`scripts/dev/dev-spa.ps1`. If restored changes overlap synchronized code, it
stops with the stash retained for explicit conflict resolution.

All `dev-spa.ps1` flags remain optional and can be passed through `Run-Latest.cmd`.
Pass positional `all` (or named `-All`) to call the existing all-worktree sync
engine before starting the stack; with no sync selector, only the launcher
worktree is updated.

## Clean up merged work

After the PR is merged:

```powershell
.\scripts\dev\agent-worktree.ps1 -Remove route-cache-fix
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
