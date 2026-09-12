# CLAUDE.md — Tripplanner

Claude Code does not read `AGENTS.md` by convention, so this file exists to point
at the rules that govern every agent in this repository. They are not restated
here; a second copy would drift from the first.

## Read these

1. **[`docs/development/agent-workflow.md`](docs/development/agent-workflow.md)**
   — the cross-agent process contract: branch and worktree convention, the
   feature-brief requirement, the definition of done, and how validation works
   now that the complete suites are suspended from the lane gates. Read it before
   starting work.
2. **[`AGENTS.md`](AGENTS.md)** — the required response structure and the
   architecture invariants (one LangGraph trip agent; `graph.py` owns the
   agent/tool loop; `api.py` owns FastAPI/SSE/SPA mount; `web/trip_view.py` is
   the UI-independent view-model boundary; booking is a grounded handoff, never
   a purchase).
3. **[`.github/copilot-instructions.md`](.github/copilot-instructions.md)** — the
   documentation ownership table and the append-only-log discipline.

Before changing code, read the canonical docs rather than reconstructing intent
from repository-wide scans: `docs/README.md`, `docs/CODEMAP.md`,
`docs/PRODUCT.md`, `docs/EXPECTED_BEHAVIORS.md`, `docs/REQUIREMENTS.md`,
`docs/ENGINEERING_LEARNINGS.md`.

## The three things most easily got wrong

- **Work in a new worktree on a `claude/<slug>` branch.** The primary checkout is
  the owner's testing tree and stays on `master`.
- **The complete test suites do not run in the lane gates.** A green merge does
  not mean the suites pass. See
  [`docs/development/testing.md`](docs/development/testing.md); use
  `/fix-suite-health` to work the known-failure backlog.
- **Update the canonical owner document, never add a parallel summary.**
