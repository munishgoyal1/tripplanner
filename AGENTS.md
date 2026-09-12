# AGENTS.md — Tripplanner

This repository follows the same engineering and reporting rules as the Copilot workspace instructions. Codex must comply with these rules on every task unless the user explicitly overrides them.

## Required operating rules

- Read the canonical docs before changing code:
  - docs/README.md
  - docs/CODEMAP.md
  - docs/PRODUCT.md
  - docs/EXPECTED_BEHAVIORS.md
  - docs/REQUIREMENTS.md
  - docs/ENGINEERING_LEARNINGS.md
- Use the canonical docs instead of reconstructing intent from broad repository scans.
- Keep work scoped to the active lane and avoid wandering into unrelated worktrees unless the user explicitly says to do so.
- Work in small read batches (50-200 lines where practical) and start from the owning file, nearby test, or documented contract.
- Before code changes, require a clean worktree and sync with the active branch's upstream before editing.
- Never revert unrelated owner or agent work. Work with relevant concurrent edits and ignore unrelated ones.
- Preserve Windows and macOS support for core dev workflows; do not claim parity without verification.
- Do not add docstrings, type hints, or comments to code that you did not otherwise touch.
- Protect production safety: do not deploy to production without explicit owner approval.

## Required response structure for substantive tasks

Every substantive task must end with a concise structured summary that includes the following headings, using the repo's established pattern:

- Original prompt
- Root cause (RCA)
- Summary
- Next actions
- Learning note

Use these exact labels, in this order, when applicable.

### Original prompt
Quote the latest active user request verbatim or as closely as possible.

### Root cause (RCA)
- For bugs or failures: include the supported direct cause, evidence, contributing factors, why the fix works, and remaining risk.
- For non-failure work: say "RCA is not applicable" and explain the decision rationale instead of inventing a cause.

### Summary
Provide a brief, concrete statement of what was done, what changed, and what was validated.

### Next actions
Use a numbered list with owner and validation notes. If there are no follow-up actions, write "None".

### Learning note
Name 1-3 reusable agentic-engineering practices demonstrated by the work and why they mattered. End the section with:

Keywords: <3-6 terms>

Examples: engineeering review, refactor planning, deterministic guardrails, tool-use policy, human-in-the-loop, verification-first.

## Required workflow expectations

- Start each feature or enhancement on a fresh, task-named agent branch such as
  `gpt-telemetry-footprint`. Bug fixes may reuse `gpt-bugfixes` only when it is
  clean and not owned by another active session. Never use generic Coordinator
  branches for owner-requested work. Keep the agent identity visible in branch
  names, use isolated worktrees for concurrent agents, and publish through a PR.

- Keep the current task title concrete and task-specific.
- If a task is a bug fix or feature change, keep the work narrow and scoped to a single coherent milestone.
- Validate with the smallest proving command that checks the changed behavior.
- Prefer tests and evidence over assumptions.
- If scope is genuinely ambiguous, stop and ask the user instead of guessing.

## Issue handling and backlog handling

- Do not create issues casually. Only create or work an issue when the repo's documented durable intake paths apply.
- A fix requested and completed in-chat does not need a separate issue if it stays local to the current lane.
- Use the repository's backlog docs and tech-debt proposals as the authoritative source for deferred work.

## Product and architecture boundaries

- Preserve the single trip-planning agent and the existing phase-based tool flow.
- Keep Itinerary, Map, Details, and Assistant synchronized.
- Treat booking as grounded selection and handoff material, not provider-side purchase or payment.
- Keep code simple and consistent with the ownership model in docs/CODEMAP.md.
- Do not reintroduce removed router or personal-assistant agents.
- Keep `src/tripplanner/graph.py` as the authority for the agent/tool loop and completion gates.
- Keep `src/tripplanner/api.py` as the authority for FastAPI, SSE, and the SPA mount.
- Keep `src/tripplanner/web/trip_view.py` as the UI-independent trip view-model boundary.

## Documentation ownership

- Update the existing canonical owner rather than creating a duplicate summary.
- Shared append-only logs are intentionally append-only; do not rewrite them.
- For durable engineering lessons, update docs/ENGINEERING_LEARNINGS.md instead of inventing a separate one-off note.

## Final rule

When Codex is acting in this workspace, it must follow the repository's Copilot rules and the reporting format above in every substantive task.

## Completion and validation

- Read `.github/copilot-instructions.md` for shared lane and publication rules.
- Commit and push completed changes; report the lane, commit, publication status,
  affected stack, and whether the primary or sandbox stack needs a restart.
- Run focused checks once per milestone. Broaden only when changes or unresolved
  failures justify it; do not repeatedly run passing full suites.
- Original prompt must be verbatim when quoted; otherwise label it a summary.
- Prompt logging remains paused; response summaries do not authorize log writes.
