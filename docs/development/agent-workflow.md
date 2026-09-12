# Agent Workflow

The cross-agent process contract. Every coding agent working in this repository
follows it, whichever tool it runs under: Claude Code, Codex/GPT, Copilot.

It exists because these rules used to live in four places at once — `AGENTS.md`,
`.github/copilot-instructions.md`, `.codex/instructions.md`, and nothing at all
for Claude Code — so a rule added to one drifted out of the others. This document
owns them now; those files point here.

Tool-specific settings stay with their tool. The documentation ownership table
stays in [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).

## 1. Branch and worktree

**Start every non-trivial change in a new worktree.** The primary checkout at
`C:\Users\munis\repos\tripplanner` is the owner's own testing tree and stays on
`master`. An agent that edits it directly takes the owner's stack out from under
them mid-session.

**Name the branch `<agent>/<task-slug>`:**

| Agent | Prefix | Example |
| --- | --- | --- |
| Claude | `claude/` | `claude/suite-suspension` |
| Codex / GPT | `gpt/` | `gpt/rail-ticket-pricing` |

The prefix makes ownership visible at a glance when several agents run at once,
which is the normal state of this repository. Branch from current
`origin/master`, not from local `master`, which may be mid-merge.

Two mechanical notes:

- Git refs are directories, so once `claude/anything` exists a branch named
  exactly `claude` becomes impossible. Never use a bare agent name as a branch.
- `full-2way-sync.ps1` sanitises `/` to `-` when it derives a temporary worktree
  path. `claude/foo` becoming `claude-foo` on disk is expected.

Shared bugfix lanes follow the same shape: `gpt/bugfixes`, not `gpt-bugfixes`.
Follow-ups to unfinished work stay on their existing branch.

## 2. Every feature or enhancement starts from a brief

Before writing code for a new capability or a material change to one, there must
be a brief in [`../feature-briefs-backlog/`](../feature-briefs-backlog/) — either
a new one from
[`FEATURE_BRIEF_TEMPLATE.md`](../feature-briefs-backlog/FEATURE_BRIEF_TEMPLATE.md)
or an existing one this work advances.
[`006-verified-itinerary.md`](../feature-briefs-backlog/006-verified-itinerary.md)
is a realistic worked example; real briefs are 150–450 lines, not the full
template skeleton.

Bug fixes, refactors with no behaviour change, and doc-only changes do not need
one.

The brief's **acceptance criteria** and **validation matrix** carry more weight
than they used to. With the complete suites suspended from the lane gates
(section 4), the brief is the written record of what "done" meant — and it is
what a later session reads when a test fails months from now and nobody
remembers what the test was protecting.

## 3. Definition of done

A change is not finished until all of these are true:

1. **Code works**, validated at the level section 4 describes.
2. **The canonical owner doc is updated** — not a new summary document. Which
   file owns which kind of change is the ownership table in
   `.github/copilot-instructions.md`. The short version:
   - observable behaviour changed → `docs/EXPECTED_BEHAVIORS.md`
   - a capability shipped or its status changed → `docs/REQUIREMENTS.md`
   - file layout, ownership, or a technical contract changed → `docs/CODEMAP.md`
   - product intent or taste changed → `docs/PRODUCT.md`
   - a reusable lesson was proven by a failure → append to
     `docs/ENGINEERING_LEARNINGS.md`
3. **A fully shipped brief is archived** to [`../implemented/`](../implemented/)
   in the same commit. If only part of a brief shipped, split it and archive the
   shipped part rather than moving the whole file.
4. **Committed and pushed**, with the lane, commit, and publication status
   reported.

Write docs densely enough that the next agent can reconstruct the feature without
re-reading the code. That is the deal that makes section 4 safe: validation got
cheaper, so context has to get better.

## 4. Validation

Which gates run locally is decided in one place:
[`scripts/dev/validation-policy.json`](../../scripts/dev/validation-policy.json).

The complete pytest and vitest suites are **suspended** from the lane gates. They
are not gone — they run periodically on master via `suite-health.ps1`, measured
against a checked-in known-failure baseline. Full detail, including how to turn
them back on, is in [`testing.md`](testing.md).

While editing, use the selector rather than a whole suite:

```powershell
python scripts/dev/test_selection.py --base origin/master
```

Run the narrowest command that proves the changed behaviour. Do not re-run
passing full suites.

## 5. Reporting

Close substantive work with the structure `AGENTS.md` defines, in that order:
**Original prompt** (verbatim, or labelled a summary) → **Root cause (RCA)** →
**Summary** → **Next actions** → **Learning note**.

Pair technical detail with a short plain-language summary. State what you did not
do, and why, explicitly — a partial result reported honestly is worth more than a
complete-sounding one that is not.
