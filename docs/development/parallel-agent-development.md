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
.\scripts\user\Sync-MeTo-Latest.cmd onlyfrommaster
```

From MasterAgent, it integrates committed local and remote worker heads into
`master`. From Agents 1-3, the no-argument command first integrates
every committed worker head through `master`, then merges that result into only
the launcher worktree. Pass `onlyfrommaster` from any lane to receive the latest
committed `master` without integrating sibling worktrees. The internal merge engine
starts its disposable integration checkout directly from fetched `origin/master`,
then updates local `master` only when MasterAgent is the launcher.

Non-launcher worktrees are never stashed, checked out, reset, or otherwise modified.
Target worktree changes are temporarily stashed and restored with their staged
state. Git `rerere` attempts a previously validated merge resolution. A new
semantic conflict does not prompt or block: the sync engine records the exact
paths, the resolution worktree, and a diff report under `logs/sync/`, preserves
the in-progress merge (and any safety stash), and stops with a
`SYNC_CONFLICT_PENDING` message rather than choosing blanket ours/theirs.

Finishing a pending merge needs no separate command or manual re-run. Every sync
launcher first reconciles the pending file with Git's unmerged indexes, so an
interrupted or previously unrecorded lane/stash conflict is recovered rather than
failing at the next stash attempt. Once the conflicted files are marker-free, the
next launcher run (or `resume-merge.ps1`) automatically finishes the merge or
stash restore, validates and publishes committed integration work, restores any
retained local edits, and propagates integrated `master` into every worktree.
Only a file that still carries conflict markers stops the run, because that is
the one case needing a real semantic decision. Sibling code always reaches a
worker through `master`; worker branches are not merged directly into one another.

Every conflict is shown in `zdiff3` style (the repository sets
`merge.conflictstyle=zdiff3`), so both sides and their common ancestor are visible
in the markers. That base context makes each resolution far less likely to drop a
side by accident.

Agent-written logs are kept out of contention structurally rather than merged. The
owner prompt log is partitioned per lane under
[`docs/reference/owner-inputs/prompts/`](../reference/owner-inputs/prompts/): each
lane tail-appends only to its own file, so two lanes can never touch the same file
and no merge is possible. The logs that must stay shared —
`docs/reference/history/requirements-log.txt` and `docs/ENGINEERING_LEARNINGS.md` —
use Git's union merge driver, and if a conflict still surfaces in a union-declared
file the sync scripts resolve it deterministically by keeping both sides. That
resolution never reaches the Copilot CLI, because concatenating two appends is not
a semantic decision and paying a model to re-derive it every run is waste.

A novel conflict is resolved automatically. When a launcher run stops on one, it
invokes the GitHub Copilot CLI to clear the markers and then retries the sync in
the same run, so no separate command is needed. The CLI only edits the conflicted
files and is denied `git push`, so the pre-publish validation gate still guards
every resolution, and a failure that is *not* a conflict (a failed validation
gate, for example) is re-raised untouched instead of being retried. Automatic
resolution requires `npm install -g @github/copilot` and a signed-in CLI; without
it the run reports the conflict and stops as before.

To opt out, pass `-NoAutoResolve` to the launcher or set
`TRIPPLANNER_NO_AUTO_RESOLVE=1`. You can then resolve the marked files by hand
(the next launcher run or `resume-merge.ps1` finishes them) or run
`scripts/user/Resolve-Conflicts.cmd`, which performs the same resolution on
demand; pass `-ResolveOnly` to inspect the edits before validating.

### Pre-publish validation gate

An integrated result is verified before it is published to `master`, so a
clean-but-broken merge cannot become the base everyone builds on. Dependencies are
reused from the primary worktree (frontend `node_modules` via a junction; the
primary `.venv` for Python) with `PYTHONPATH` pointed at the merged tree, so
nothing is reinstalled.

- **Frontend (`vitest`)** is a hard gate: any failure stops publication.
- **Python (`pytest`)** is a regression gate. It blocks only on failures that are
  new versus a self-updating baseline in `logs/sync/validation-baseline.json`, so
  pre-existing environmental or date-dependent failures never block a merge, while
  a genuinely new failure does.

When validation fails the integrated result is not pushed, `master` stays
unchanged, the merged worktree is preserved for inspection, and a report lands in
`logs/sync/validation-<stamp>.md`. Fix the merged tree (or the offending commit)
and re-run; a passing run publishes. A check whose toolchain is absent is skipped,
never failed. Set `TRIPPLANNER_SKIP_SYNC_VALIDATION=1` to bypass the gate for a run.

### Run logs and pending state

Every sync launcher writes a timestamped transcript to
`logs/sync/<component>-<yyyyMMdd-HHmmss>.log` and appends a one-line record to
`logs/sync/runs.log`, so a later session can reconstruct exactly what ran. The
outermost script owns the transcript; nested engines log into the same file. When
a conflict is pending, `logs/sync/pending-merge.json` holds the resumable entries
and `logs/sync/conflict-<kind>-<stamp>.md` holds the human-readable diff. The
`logs/` tree is git-ignored, so these never enter a commit. The heal step and
`resume-merge.ps1` clear each entry as it completes and report only files that
still hold conflict markers.
Independent dated additions to
`docs/reference/history/requirements-log.txt` use Git's union merge driver because that file is
append-only; both branches' entries are retained. The owner prompt log needs no
merge driver at all, because each lane owns a separate file under
`docs/reference/owner-inputs/prompts/`. Read the merged view with:

```powershell
.\scripts\user\Show-Prompts.cmd            # all lanes, newest first
.\scripts\user\Show-Prompts.cmd -Important # only prompts marked !
```

To intentionally synchronize every worktree from MasterAgent or Agents 1-3
launcher, run:

```powershell
.\scripts\user\Sync-AllTo-Latest.cmd
```

This first integrates committed heads through `master`, then updates MasterAgent,
Agents 1, 2, and 3 independently. Each lane's staged, unstaged, and untracked
files are preserved in an exact safety stash. Git `rerere` automatically applies
a previously recorded resolution. A novel local-edit conflict retains that
lane's stash, records a resumable entry under `logs/sync/`, lists its unresolved
paths, and allows the other lanes to continue; the command exits nonzero after
reporting every lane requiring attention. Resolve the listed files; the next
launcher run (or `scripts/dev/resume-merge.ps1`) finishes and propagates them
automatically. A novel conflict while
integrating committed heads must still be resolved before one authoritative
`master` can be distributed. The script never guesses with blanket ours/theirs
conflict resolution.

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
