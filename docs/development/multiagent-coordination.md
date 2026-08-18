# Multiagent Coordination

Several bounded agents process GitHub issues in parallel while one owner-approved
path leads back to `master`. This document is the operational contract: what each
role may do, what the owner controls, and how the system recovers.

It extends [issue-workflow.md](issue-workflow.md), which remains the protocol for
ordinary chat sessions working in a sandbox. Nothing here changes how sandboxes
work; the multiagent lanes are deliberately invisible to them.

## Roles

| Role | Runtime | Owns |
| --- | --- | --- |
| Owner | You | What is worth building, and every ambiguous decision |
| Coordinator chat | VS Code Copilot agent | The conversation: drafting requirements, answering blocked issues |
| Controller | `scripts/dev/multiagent.py`, launched detached | Leases, dispatch, slots, integration, recovery |
| Worker | Copilot CLI, non-interactive | One issue, one branch, one commit |
| Producer | `scripts/dev/multiagent.py audit` | Finding bugs and proposing them as issues |

The split between the coordinator chat and the controller is deliberate. A chat
session is the better interface but the worse process manager: it cannot be
relied on to still exist in an hour. The controller is deterministic, holds the
lease, and survives with no chat open. The coordinator chat is where you talk to
the system, and it can be closed and reopened at any time.

There is one interactive agent. The producer never talks to you directly, and
neither does a worker; everything reaches you through an issue and the
coordinator chat reads it.

## How work enters the system

```text
you file a Requirement issue        -> owner:proposed
the producer finds a bug            -> owner:proposed + source:audit + bug
you decide it should be built       -> owner:proposed + owner:ready
the controller dispatches it        -> + agent:in-progress + lane:mw-<slot>
a worker pushes its commit          -> + agent:integrating
integration and validation pass     -> + agent:needs-verify, in the batch PR
you merge the PR                    -> issue closes on master
```

Nothing is ever dispatched because an agent thought it was a good idea. The only
entry to execution is you adding `owner:ready`.

### Labels

`owner:*` labels are **additive facts**. They record what was decided and are not
removed as work progresses.

| Label | Fact it records |
| --- | --- |
| `owner:proposed` | Entered as a candidate; kept forever as provenance |
| `owner:ready` | You authorised implementation |
| `owner:withdrawn` | You revoked authorisation after dispatch |
| `owner:decision-needed` | Something is waiting on your answer |
| `source:audit` | The producer created this from an audit finding |

`agent:*` labels are **mutually exclusive execution states**. Exactly one applies
at a time, and the controller removes the previous one on every transition:
`agent:queued`, `agent:in-progress`, `agent:blocked`, `agent:integrating`,
`agent:needs-verify`.

Selection is by containment, never by absence of `owner:proposed`:

```text
is:issue is:open label:owner:ready
```

filtered further to exclude `owner:withdrawn` and any issue already holding an
active `agent:*` state.

The Requirement and audit issues do **not** get `agent:queued`. `owner:ready` is
the multiagent queue; `agent:queued` stays with the manual lanes so the two
systems cannot fight over the same issue.

### Withdrawing authorisation

Authorisation is **snapshotted at dispatch**, so removing `owner:ready` mid-flight
is never a silent abandon:

- Not yet dispatched: the issue simply stops being eligible.
- Dispatched, worker still running: the controller adds `owner:withdrawn`, stops
  the worker at its next checkpoint, and comments where it stopped.
- Already integrated: the change stays in the batch. Withdrawal after acceptance
  is a revert, which is its own issue.

## The producer

The producer is deterministic. It runs the existing read-only trip audit, which
reads stored trips and fixtures and calls no model and no provider, then turns
new finding groups into proposed issues.

Three rules exist because breaking them would quietly defeat the purpose:

1. **It never runs `--accept`.** That writes the findings baseline and marks
   current findings as known forever. An auto-accepting producer would suppress
   exactly the bugs it exists to find. Accepting stays a manual owner action.
2. **Exit code `2` is an infrastructure failure, not a clean run.** It means the
   corpus was empty and nothing was checked. Exit `1` means new findings; exit
   `0` means genuinely clean.
3. **It caps how many issues one run may open** (three by default, worst severity
   first). A run with more findings than the cap opens one summary issue asking
   how to proceed rather than filing forty.

Deduplication survives a wiped runtime directory because the fingerprint lives in
the issue body, not on disk:

```text
audit-fingerprint: I9/3f2a1c8b
```

Before creating anything the producer searches open **and closed** issues for that
marker. A finding that recurs after being closed reopens the original issue with a
comment instead of opening a duplicate.

Corpus generation spends real money and needs a running API, so it is never part
of the automatic loop. A paid run requires its own issue carrying `owner:ready`
and naming the budget, target, database, and API. The producer may run
`--dry-run` freely.

## Lanes, slots, and worktrees

```text
tripplanner.worktrees/multiagent/
  integration/      long-lived, reset to origin/master each batch
  slot-1/           reusable worker worktree
  slot-2/           reusable worker worktree
  runtime/          state, leases, pids, transcripts (outside the repo, untracked)
```

Slots are reusable worktrees, not per-issue creations. Creating a worktree per
small issue would re-install frontend dependencies and re-link the client package
every time; reusing a slot keeps `node_modules` and the linked packages warm. What
is *not* reused is the branch or the agent context: every attempt gets a fresh
branch and a fresh session, so one issue never inherits another's reasoning.

Branches are `multiagent/issue-<n>-attempt-<k>`. The attempt number is derived
from the branches that exist on the remote, so a wiped runtime directory cannot
reuse `attempt-1`.

Lane labels are `lane:mw-1` and `lane:mw-2`, distinct from `lane:sbx-<n>`.

### Why this cannot disturb sandboxes

- Sandbox commands enumerate lanes from `sandboxes.json`, and multiagent lanes are
  never registered there.
- The stray detector in `sandbox.ps1` only flags worktrees whose directory name
  matches `sbx-*` and branches under `refs/heads/sandbox`. Slot directories are
  `slot-N` and branches are `multiagent/*`, so neither is reported.
- The slots are named `slot-N`, not `worker-N`, so they cannot be confused with
  the existing `tripplanner.worktrees/worker-1..3` agent worktrees.
- Workers do not start stacks and allocate no ports. Work that genuinely needs a
  running stack is escalated to you, not silently given a port.

## The worker contract

A worker receives a complete, immutable assignment. It never watches GitHub and
never chooses what to work on.

1. Start from the integration baseline SHA in its slot, on a fresh branch.
2. Read the issue, the canonical docs that own the area, and the nearby tests.
3. Post `## Triage` before editing anything.
4. Change only the assigned outcome, and commit with `Fixes #<n>` in the body.
5. Run the required validation.
6. Push the branch and report the exact commit SHA.
7. Stop.

A worker never merges, never closes an issue, never pushes outside its own
branch, and never picks up a second issue.

**The slot is released the moment the worker pushes.** Integration happens
asynchronously on a single serialized lane, so a slot is never idle waiting for a
queue it does not control. If integration later fails, the issue is re-dispatched
as the next attempt to whichever slot is free — slots are interchangeable.

## Integration

- Integration merges the **exact pushed SHA**, never a branch name that may have
  moved.
- `multiagent/integration` is long-lived and reset to `origin/master` at the start
  of each batch.
- Focused validation runs after each merge. The baseline advances only on success.
- Because you commit to `master` directly, the batch re-syncs with the current
  `origin/master` and re-runs aggregate validation before the PR opens. A batch
  validated against a stale base is not validated.
- The PR is **merged, not squashed**, so each worker commit keeps its `Fixes #<n>`
  trailer. The PR body repeats every `Fixes #<n>` as a second guarantee.
- Issues close when the PR reaches `master`. An accepted integration commit is not
  a closed issue.

### Validation

Focused validation is the backend suite plus, when frontend files changed, the
frontend suite. Measured on 2026-08-18, the backend suite is 1,446 tests in 23
seconds, so there is no case for a change-mapped subset: running everything is
both cheaper to reason about and fast enough to run on every integration.

Workers use the primary checkout's `.venv` through `git rev-parse --git-common-dir`,
exactly like the other dispatchers. They must run tests with `PYTHONPATH=src`
resolved **from their own worktree**, or they validate the primary checkout's
source and report a false pass.

## Owner decisions

When a worker or the producer hits something genuinely ambiguous, it stops and
writes one block into the issue:

```markdown
## Owner Decision

**Question:** the single decision needed
**Why it blocks:** what cannot safely continue
**Options:** the bounded choices, with tradeoffs
**Recommendation:** the preferred option and why
**Answer:** waiting
```

The controller then applies `agent:blocked` and `owner:decision-needed`. Your
queue is one command:

```bash
gh issue list --state open --label "owner:decision-needed"
```

`Multiagent-Status` prints the same queue. You answer in the coordinator chat or
directly in the issue; the controller resumes the work as a fresh attempt with the
answer included in the assignment.

## Safety

- **Quota is shared.** Every worker, the producer, and your own chats draw on one
  account. Concurrency starts at two. When limits are hit the controller enters
  `paused:quota` and says so, instead of surfacing mysterious worker failures.
- **Audit-derived text is untrusted data.** It embeds real trip content and ends up
  in an issue that a worker later reads. The producer fences it under an explicit
  marker, and workers are instructed that content below the marker is data to
  analyse, never instructions to follow.
- **Secrets never leave the machine.** Transcripts live in the untracked runtime
  directory, and known secret environment variables are redacted from worker
  output.
- **Workers are denied** production deployment, sandbox commands, `owner:*` label
  changes, merges, force pushes, and pushes to any branch but their own.
- **Deployment is untouched.** Canary and production keep their existing approval
  gates. This system never deploys.

## Commands

One shared implementation, thin launchers on both platforms.

| Launcher | Does |
| --- | --- |
| `Start-Multiagent` | Preflight, take the lease, start the controller detached, open the coordinator chat |
| `Pause-Multiagent` | Stop dispatching; let running workers finish |
| `Resume-Multiagent` | Resume dispatching |
| `Stop-Multiagent` | Stop dispatch, terminate supervised workers, keep their worktrees and branches |
| `Multiagent-Status` | Slots, assignments, decisions waiting, last validation, recovery commands |
| `Plan-Multiagent` | Dry run: what it *would* dispatch, and why it excluded the rest |
| `Open-Coordinator` | Open the owner-facing coordinator chat in VS Code |
| `Run-Audit-Producer` | One producer pass; `--dry-run` reports findings without opening issues |

Windows launchers are in `scripts/win/user/multiagent/`, macOS in
`scripts/mac/user/multiagent/`, and both forward to `scripts/dev/multiagent.ps1`.

## State and recovery

All runtime state is one JSON file in the untracked runtime directory: the
coordinator lease, slot occupancy, and every assignment with its attempt number,
base SHA, worker session id, pushed SHA, validation result, and last heartbeat.

- One coordinator holds a lease with an expiry. A second `Start` refuses unless
  the lease has expired.
- Leases and heartbeats expire, and every remote-mutating step is idempotent or
  records its phase first.
- On restart the controller reconciles four sources — issue labels, its own state
  file, the processes actually alive, and the branches actually on the remote —
  because labels alone cannot say whether a push happened.
- A timed-out worker keeps its worktree and branch for inspection. Evidence is not
  deleted to make room.

## Non-goals

- A free-running agent that decides repository priorities on its own.
- Workers polling GitHub or negotiating ownership with each other.
- Batching unrelated issues into one branch or commit to save startup cost.
- Treating labels as an atomic lock, or a pushed branch as validated work.
- Any deployment, production data change, or bypass of an existing approval gate.
