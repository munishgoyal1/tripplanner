# Issue Workflow

GitHub issues are the shared task board for this repository. Chat sessions cannot
see each other, and repository memory is local to one machine and one lane. An
issue is the only place where the owner and several parallel agent sessions can
read and write the same record of one piece of work.

The repository is private, issues are enabled, and the default branch is `master`.

## What an issue is for

An issue holds one unit of work and its live state: what is wrong, who is on it,
what was found, what changed, and whether the owner has confirmed it. It is
deliberately short-lived. It is closed when the fix reaches `master`.

The issue body and its complete chronological comment thread form the handoff.
Owner comments are cumulative scope and context, like saved UX Lab handoff notes:
they may add a related observation, acceptance condition, or implementation
pointer after the issue was opened. A newer explicit owner statement supersedes
conflicting older text. Comments from other participants are supporting context,
not owner authorisation. Autonomous workers receive this whole thread and must
account for every owner ask in Triage before editing.

If an owner comment describes a genuinely separate outcome rather than a related
part of the same fix, or conflicts with existing scope in a way that cannot be
resolved from the thread, the worker blocks with the exact question. It does not
silently omit the comment or widen the issue by guessing.

Immediate work does not need that handoff record. A fix requested and completed in
the current chat stays in that chat, whether the lane is primary `master` or a
sandbox and regardless of size. Do not create an issue merely because the chat
found a bug or the fix became substantive; that discards useful conversational
context and creates queue work for something already being handled.

Create an issue only when one of these is true:

- the owner explicitly creates it or asks an agent to create it;
- the deterministic trip-audit producer files a finding;
- a specific audit run needs a durable scheduled work item; or
- the work cannot be handled now and is intentionally parked as backlog.

If an immediate fix reveals a distinct deferred follow-up, only the deferred
follow-up becomes an issue. The current fix remains chat-local.

An issue is not a place to keep truth. Durable knowledge keeps its existing owner:

| Kind of information | Where it belongs |
| --- | --- |
| Explicit, audited, scheduled, or intentionally deferred work and its progress | GitHub issue |
| Product intent, scope, and design taste | `docs/PRODUCT.md` |
| Current capability and status | `docs/REQUIREMENTS.md` |
| Ownership, architecture, contracts, commands | `docs/CODEMAP.md` |
| A durable lesson learned from a failure | `docs/ENGINEERING_LEARNINGS.md` |
| Deferred cross-cutting engineering work | `docs/eng-backlog/` |
| An idea not yet selected | `docs/roadmap/` |
| An approved milestone's bounded scope | `docs/feature-briefs/` |
| A visual decision between options | `docs/ux-experiments/` and a UX Lab |

When an issue produces a durable lesson, write the lesson in
`docs/ENGINEERING_LEARNINGS.md` and link it from the issue. The issue then closes
without becoming the record.

## Labels

State labels, applied by agents, one at a time:

| Label | Meaning |
| --- | --- |
| `agent:queued` | Logged and ready for an agent to pick up. Applied by the issue templates. |
| `agent:in-progress` | Claimed by exactly one lane, which is working it now. |
| `agent:blocked` | Waiting on an owner decision. The agent has asked in the issue and stopped. |
| `agent:needs-verify` | The fix is in `master`. The owner has not confirmed it yet. |

Lane labels, `lane:master` and `lane:sbx-<n>`, record which worktree owns the
issue. The number is the sandbox's permanent port slot, so it survives a rename.
There is only one GitHub account behind every agent, so the assignee cannot say
which session owns the work; the lane label is what makes that visible in a list.

Type labels reuse the GitHub defaults: `bug`, `enhancement`, `documentation`.

### Owner labels, and the multiagent queue

`owner:*` labels are additive facts, not states. `owner:proposed` records that
something entered as a candidate and is kept forever; `owner:ready` records that
you authorised implementation. Adding `owner:ready` never removes
`owner:proposed`.

`owner:ready` is what the autonomous coordinator selects on, so a manual lane
should leave it alone. `agent:queued` stays with the manual lanes described here,
and the coordinator ignores it. The full pipeline is in
[multiagent-coordination.md](multiagent-coordination.md).

## Lifecycle

```text
owner opens issue           -> agent:queued
agent claims it             -> agent:in-progress + lane:<lane>   (+ Triage comment)
agent needs a decision      -> agent:blocked                     (question in the issue)
agent lands the fix         -> agent:needs-verify                (+ Implementation comment)
                               issue closes when the commit reaches master
owner confirms              -> remove agent:needs-verify
```

## Claiming, and why it is not optional

Parallel lanes make double-work and merge collisions the default failure, not the
exception. Claiming is what prevents both.

The rules below apply only once work has an issue through the intake policy above.
They do not force any primary or sandbox chat to manufacture an issue for work it
is fixing immediately.

Before starting issue-backed work, look at what other lanes already own:

```bash
gh issue list --state open --label "agent:in-progress"
gh issue list --state open --label "agent:queued"
```

Then claim the existing issue, in one step, before editing:

```bash
gh issue edit <n> --add-label "agent:in-progress" --add-label "lane:sbx-3" \
  --remove-label "agent:queued" --add-assignee "@me"
```

Rules that keep parallel work honest:

- **One issue is worked in exactly one lane.** The lane is the one the chat
  session already owns; a sandbox session does not reach into `master` or another
  sandbox to fix its issue.
- **Never take an issue already labelled `agent:in-progress` by another lane.**
  If its claim comment is more than a day old with no newer comment, post a
  takeover comment naming your lane and the stale claim, then relabel.
- **Check for file collisions before claiming.** If another in-progress issue
  names the same files in its triage comment, say so in your issue and pick a
  different one, or agree an order in the issue rather than racing.
- **Release what you are not doing.** If a session ends without landing the fix,
  remove `agent:in-progress` and leave a comment saying where it stopped, so the
  next session does not have to guess whether it is abandoned.

Bugs default to the bugfix lane, new UX Labs to the Lab factory lane, and Lab
implementation to the implement-labs lane, matching the standing lane convention.

## The two comments

Post exactly two comments, with these headings so they stay greppable. Edit them
as things change rather than appending a running commentary; an issue read six
months later should be a record, not a transcript.

**Triage**, before editing any code:

```markdown
## Triage

**Lane:** sbx-3 (`sandbox/3-bugfixes`) · **Session:** <chat title>
**Reproduced:** yes | no | partly — how, and against which stack and data
**Root cause:** the actual mechanism, not the symptom
**Files:** the owning files this will touch
**Plan:** what will change, in one or two sentences
**Risk:** what else this could affect, and what stays untouched
**Open questions:** anything that would otherwise be a guess
```

If a question genuinely blocks the work, add `agent:blocked` and stop there. Do
not guess at scope, and do not silently widen it.

**Implementation**, after validation and before or with the merge:

```markdown
## Implementation

**Lane:** sbx-3 (`sandbox/3-bugfixes`) · **Commit:** abc1234
**Changed:** what actually changed, and why that was the fix
**Files:** the files touched
**Validation:** the commands run and their results
**Restart needed:** which stack, if any
**Follow-ups:** anything deliberately left, and where it is recorded
```

## Landing and closing

Reference the issue in the commit body so GitHub closes it when the fix reaches
the default branch:

```text
Fixes #42
```

A sandbox push does not close the issue; merging that sandbox into `master`
does. That is the intended meaning of closed: the fix is in `master`, not merely
in a lane. When work lands directly on `master`, the push closes it immediately.

Post the Implementation comment before the merge, so the record is complete at
the moment it closes, then add `agent:needs-verify`. The owner's confirmation
queue is:

```bash
gh issue list --state closed --label "agent:needs-verify"
```

Reopen rather than opening a duplicate when a fix turns out to be incomplete.

## Commands

```bash
# What is in flight across every session
gh issue list --state open --label "agent:in-progress"

# What this lane owns
gh issue list --state open --label "lane:sbx-3"

# Read one issue with its comments
gh issue view 42 --comments

# Log one quickly from the terminal
gh issue create --title "Return transfer dropped on day move" --label bug,agent:queued

# Comment from a file, so the template survives shell quoting
gh issue comment 42 --body-file triage.md

# Hand back an issue this session will not finish
gh issue edit 42 --remove-label "agent:in-progress"
gh issue comment 42 --body "Stopping here: root cause found, fix not started."
```

## Practices that keep this working

- **Read the body and every comment before you write.** List open issues when
  selecting or continuing issue-backed work, then read the complete thread; this
  is not an instruction to create an issue for immediate in-chat work.
- **Claim narrowly and land quickly.** A long-held claim blocks other lanes more
  than it helps; split a large issue rather than holding it for days.
- **One issue, one outcome.** A bug that turns out to be three bugs becomes three
  issues, linked, not one issue with three fixes and an unclear closing state.
- **Say what you did not do.** Deliberate non-scope in the Implementation comment
  is what stops the next session from assuming it was already handled.
- **Keep the status line and the issue consistent.** The reply's lane and commit
  must match what the Implementation comment says.
- **Do not paste secrets.** Trip, user, and chat ids are fine in a private
  repository; keys, tokens, and `.env` contents never are.
- **Do not let issues replace the docs.** If it will still be true next month, it
  belongs in the canonical document that owns it.
