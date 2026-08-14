# Copilot Instructions — tripplanner

Read these canonical sources before changing code:

- [docs/README.md](../docs/README.md): documentation ownership and navigation.
- [docs/CODEMAP.md](../docs/CODEMAP.md): architecture, code ownership, contracts, and commands.
- [docs/PRODUCT.md](../docs/PRODUCT.md): product intent, interaction rules, and design taste.
- [docs/EXPECTED_BEHAVIORS.md](../docs/EXPECTED_BEHAVIORS.md): authoritative user actions, outcomes, and regression IDs.
- [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md): current capability baseline, gaps, and roadmap.
- [docs/ENGINEERING_LEARNINGS.md](../docs/ENGINEERING_LEARNINGS.md): durable lessons from observed failures.

Use the canonical docs instead of reconstructing intent from broad repository
searches. The chronological decision history remains in
[docs/reference/history/requirements-log.txt](../docs/reference/history/requirements-log.txt).
Owner-authored source notes in `docs/reference/owner-inputs/` provide original
intent, while other dated context lives under `docs/reference/history/`. They do
not override the canonical documents above, which govern current behavior.

## Agent workflow

- Keep the current chat title to a concrete 4-5 word summary of the latest task.
  Reconsider it after every prompt in the primary or sandbox VS Code window.
- A chat session titled or opened for a specific sandbox (`sbx-N` / `sandbox/N-*`)
  stays scoped to that sandbox's worktree for the rest of the session: keep
  reading, editing, testing, and committing there instead of wandering into
  `master` or another sandbox unless the owner explicitly redirects it. This
  keeps parallel sessions mapped 1:1 to a lane so which session owns which
  track stays obvious without switching windows to check.
- End every substantive reply with a one-line status: what was fixed/changed,
  which part of the stack (frontend/backend/both/docs/scripts), and whether a
  dev-stack restart is needed to pick it up (and which stack: primary or the
  sandbox in scope). Skip this line only for pure question-answering turns
  that changed nothing.
- After each owner prompt, append it verbatim to the **bottom** of
  [master.txt](../docs/reference/owner-inputs/prompts/master.txt). Entry header:
  `[YYYY-MM-DD HH:MM] [master] <short title>`, with ` !` after the lane for feature
  work, bug fixes, critical owner direction, or reusable workflows. Do not read the
  file first and do not number entries.
  `prompts_executed.txt` and `prompts_executed_imp.txt` are frozen archives.
  Read the log back with `pwsh -File scripts/dev/show-prompts.ps1`.
- Read 50-200 line chunks and batch independent reads. Start from the owning file,
  nearby test, or documented contract instead of mapping the whole repository.
- Before every new code change, require a clean worktree, fetch `origin`, and
  synchronize the active branch with latest `origin/master`. Resolve conflicts
  and re-read affected files before editing.
- The primary `master` workspace is the default development lane. Use a fresh,
  task-named sandbox only for an isolated feature or UX Lab. A sandbox returns to
  `master` only through its validated promotion flow.
- Run `scripts/user/Run-Latest-Master.cmd` only from primary `master` to fast-forward it
  from `origin/master` before starting the local stack.
- The primary workspace owns the canonical local stack. Sandboxes use their own
  port slots and server-free validation by default.
- Validate once per coherent milestone unless a focused mid-edit check is needed.
  Always commit and push completed changes; do not leave unpushed milestones.
- Preserve Windows and macOS support for core development: setup, dependency
  restore, VS Code/Copilot configuration, build, test, lint, and persistent
  worktrees. Prefer shared PowerShell 7, Python, Node.js, and Docker engines with
  thin platform-specific launchers. Do not duplicate every convenience wrapper
  or claim platform parity without a host-level check; document unverified or
  intentionally platform-specific operational workflows explicitly.
- Never revert unrelated owner or agent work. Work with relevant concurrent edits
  and ignore unrelated ones.
- Do not add docstrings, type hints, or comments to code you did not otherwise touch.

See [parallel-agent-development.md](../docs/development/parallel-agent-development.md)
for sandbox lifecycle and promotion.

## Product and engineering boundaries

- This is a one-person, preference-aware trip planner. Optimize for the owner's
  actual workflow, not generic SaaS behavior.
- Keep one LangGraph trip agent with phase-selected tools. Do not reintroduce the
  removed router or personal-assistant agents.
- The Assistant builds the itinerary; Details and Map refine the persisted plan.
  Preserve synchronization among Itinerary, Map, Details, and Assistant.
- Booking means grounded choices and verified handoff material, not provider-side
  purchase, payment, cancellation, or order management.
- Keep changes simple, modular, and consistent with existing ownership. Major
  functional changes require explicit owner consent.
- Treat [FUTURE_FEATURES.md](../docs/roadmap/FUTURE_FEATURES.md) as candidates,
  not approval. Use an owner-edited feature brief for coherent new capabilities.
- For selected UX Labs, link the implementation sandbox with `-LabId` and read the
  latest saved handoff before editing. Implement only the declared option scope
  plus saved owner modifications, and preserve the Lab page. If the handoff or
  implementation scope is ambiguous, ask the owner in the current sandbox worker
  chat and wait for that answer instead of guessing. `-Promote` records the promoted
  commit as an implemented-review iteration by itself, after starting the stack and
  confirming the endpoints answer, so an iteration loop ends at promotion with no
  separate step. Pass `-IterationSummary` to `-Serve` or `-Promote` only to choose
  that wording, or to record an intermediate iteration you want in the Lab history.
  Do not record a startup with no Lab changes as an
  iteration. Successful verified promotion appends Completed before cleanup.
- Never deploy production without explicit owner approval.

## Code conventions

- Python 3.11+, `from __future__ import annotations`, 100-character Ruff line limit.
- Tools use LangChain `@tool`; API clients and search tools live under
  `src/tripplanner/tools/` or the existing provider boundary.
- Configuration uses Pydantic `Settings` from environment files.
- Pure logic tests use pytest without mocks where practical.
- Production web code lives under `frontend/src/`; isolated experiments live under
  `frontend/labs/`; shared web/native contracts live in `packages/tripplanner-client/`.
- Use succinct comments only for non-obvious choices.

## Architecture invariants

- `src/tripplanner/graph.py` owns the agent/tool loop and deterministic completion gates.
- `src/tripplanner/api.py` owns FastAPI, SSE, and the production SPA mount.
- `src/tripplanner/web/trip_view.py` is the UI-independent trip view-model boundary.
- `src/tripplanner/storage_cosmos.py` and local JSON persistence remain selectable
  through configuration; hosted canary and production databases stay isolated.
- Hosted identity comes from signed Google, native bearer, or guest capability
  credentials, never caller-claimed account IDs.
- The React workspace has one state owner for trip revision and focus. Stale reads
  must not overwrite newer trip, identity, or mutation state.
- Azure OpenAI data-plane API version is `2024-10-21`; `2024-11-20` is a model
  snapshot and causes a 404 when used as the API version.

## Deployment gates

- Image publication is manual only. Commits do not automatically build or push.
- `infra/deploy-canary.ps1` builds and pushes the current immutable Git SHA by
  default, deploys canary, and runs read-only smoke. Use canary for testing.
- `infra/deploy-prod.ps1` promotes the immutable image already deployed to canary.
  Normal promotion must not rebuild. The script requires the exact phrase
  `APPROVE_PROD_DEPLOYMENT` and logs the result.
- `infra/rollback-prod.ps1` activates the prior production revision; it does not
  undo data writes.
- The canonical release procedure is
  [docs/operations/deployment-flow.md](../docs/operations/deployment-flow.md).

## Documentation ownership

Update the existing owner rather than creating another summary:

| Change | Update |
| --- | --- |
| Cross-project preference | `/memories/preferences.md` |
| Repository-specific fact or landmine | `/memories/repo/tripplanner.md` |
| Product intent, scope, or design taste | `docs/PRODUCT.md` |
| Current capability or status | `docs/REQUIREMENTS.md` |
| File ownership, architecture, or command | `docs/CODEMAP.md` |
| Durable engineering lesson | `docs/ENGINEERING_LEARNINGS.md` |
| New dated requirement or decision | `docs/reference/history/requirements-log.txt` |
| Active milestone scope | `docs/feature-briefs/` |
| Candidate or deferred idea | `docs/roadmap/` |
| Current in-flight session state only | `/memories/session/` |

Keep the latest rule only. Stale memory or duplicated documentation is worse
than a concise pointer to the canonical owner.

### Append-only logs

Prefer **partitioning over merging**: if only one lane ever writes a file, no merge
is possible. The owner prompt log is split per lane under
`docs/reference/owner-inputs/prompts/` for exactly this reason. Use the same pattern
for any new agent-written log.

For the logs that must stay shared — `docs/ENGINEERING_LEARNINGS.md` and
`docs/reference/history/requirements-log.txt` — `merge=union` in `.gitattributes` is
the safety net, and the sync scripts resolve any residual conflict in a
union-declared file by keeping both sides without calling the Copilot resolver.
That guarantee depends on how you write them:

- **Append at the tail.** Adding at the top makes two lanes edit the same region,
  which forces a read of the file, produces colliding entry numbers, and eats the
  blank line between entries even when union succeeds.
- **Do not number entries.** Use a timestamp; a global counter cannot be allocated
  without reading the shared file and still collides across lanes.
- Only ever add a new dated entry. Never edit, reorder, reflow, or delete an
  existing one; union merge would silently keep both versions of a rewritten line.
- Keep each entry a self-contained block separated by a blank line, so
  concatenating two lanes' entries always yields a valid document.
- Before adding a file to the union list, confirm it is genuinely append-only.
  Structured documents such as `docs/REQUIREMENTS.md` must stay conflict-visible.
  A file left off the list is the usual cause of a surprise conflict.
