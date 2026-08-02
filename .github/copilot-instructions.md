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
  Reconsider it after every prompt in every primary and worker VS Code window.
- Read 50-200 line chunks and batch independent reads. Start from the owning file,
  nearby test, or documented contract instead of mapping the whole repository.
- Before every new code change, require a clean worktree, fetch `origin`, and
  synchronize the active branch with latest `origin/master`. Resolve conflicts
  and re-read affected files before editing.
- The primary `master` workspace is the default development lane. Use persistent
  Agent 1 - Iti-Map and Agent 2 - Detail-Chat worktrees only for owner-requested,
  sizeable, isolated parallel assignments. These names are logical default
  ownership areas; agent numbers, branches, worktree paths, and script arguments
  remain unchanged. Each worker owns one PR-sized change at a time.
- Run `scripts/user/Sync-MeTo-Latest.cmd` from the worktree to update. Agent 3 always
  integrates all committed worker heads. A worker receives only `master` by
  default; pass `all` to include committed sibling worktree changes through
  `master`. The launcher is the only worktree updated.
- Use `scripts/user/All-SyncTo-Latest.cmd` only when every worktree should be
  updated. It may run from any lane, preserves each lane's local edits, reuses
  recorded `rerere` resolutions, and reports novel conflicts without guessing.
- Agent 3 in the primary workspace owns local stack startup, stop, restart,
  stale-port cleanup, and health checks for the owner's manual testing. Workers 1
  and 2 must obtain explicit approval before changing the stack lifecycle and use
  server-free validation by default.
- Validate once per coherent milestone unless a focused mid-edit check is needed.
  Always commit and push completed changes; do not leave unpushed milestones.
- Never revert unrelated owner or agent work. Work with relevant concurrent edits
  and ignore unrelated ones.
- Do not add docstrings, type hints, or comments to code you did not otherwise touch.

See [parallel-agent-development.md](../docs/development/parallel-agent-development.md)
for worktree synchronization and cleanup.

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
- For selected UX Labs, implement only the declared option scope plus saved owner
  modifications. Preserve the Lab page and complete its lifecycle record.
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
