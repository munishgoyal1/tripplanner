# Code Map

This document answers four questions: where behavior is owned, which contracts
must remain stable, how data flows, and which commands validate a change. Product
intent belongs in [PRODUCT.md](PRODUCT.md); capability status belongs in
[REQUIREMENTS.md](REQUIREMENTS.md); observable interaction contracts belong in
[EXPECTED_BEHAVIORS.md](EXPECTED_BEHAVIORS.md); durable failure lessons belong in
[ENGINEERING_LEARNINGS.md](ENGINEERING_LEARNINGS.md).

## System Shape

```text
React web / Expo mobile / CLI
             |
        FastAPI + SSE
             |
   one LangGraph trip agent
             |
 phase-selected tools and provider clients
             |
 local JSON or Azure Cosmos DB persistence
```

The project has one trip agent. Do not add router or personal-assistant agents.
The Assistant builds the itinerary; Details and Map mutate the same persisted
trip through shared API contracts.

## Runtime Ownership

| Path | Owns |
| --- | --- |
| `src/tripplanner/graph.py` | Agent/tool loop, completion gates, and model-facing tool-result budget |
| `src/tripplanner/state.py` | Shared graph state and merge behavior |
| `src/tripplanner/prompts.py` | Agent instructions and prompt assembly |
| `src/tripplanner/workflow.py` | Trip-planning workflow helpers |
| `src/tripplanner/api.py` | FastAPI routes, hosted identity boundary, SSE transport, production SPA mount |
| `src/tripplanner/chat_interactions.py` | Validated prefilled Assistant input requests |
| `src/tripplanner/request_identity.py` | Signed web, native, and guest principal resolution |
| `src/tripplanner/request_limits.py` | Chat/replay rate limits, concurrency, and workspace exclusion |
| `src/tripplanner/cli.py` | Local command-line experience |
| `src/tripplanner/config.py` | Pydantic environment settings |
| `src/tripplanner/models.py` | Core trip and itinerary models |
| `src/tripplanner/json_store.py` | Atomic local JSON replacement and Windows-lock retry |
| `src/tripplanner/web/trip_view.py` | UI-independent trip view model and display semantics |
| `src/tripplanner/web/chat_store.py` | Conversation and replay persistence |
| `src/tripplanner/web/external_operations.py` | Idempotency ledger for outbound provider writes |
| `src/tripplanner/persistence.py` | Local JSON persistence boundary |
| `src/tripplanner/storage_cosmos.py` | Cosmos implementation and conditional replacement |
| `src/tripplanner/trip_events.py` | Durable trip event ownership |
| `src/tripplanner/about_me_store.py` | Preference profile persistence |
| `src/tripplanner/export.py` | Export composition |
| `src/tripplanner/observability.py` | Structured events and request diagnostics |
| `src/tripplanner/error_analysis.py` | Local and canary failure classification and reports |
| `src/tripplanner/critics.py` | Deterministic quality checks |
| `src/tripplanner/providers/` | Normalized travel provider clients and capability registry |
| `src/tripplanner/tools/` | LangChain tools and stable agent/provider boundaries |

Tools use `@tool`. Keep provider HTTP details behind the existing client or tool
boundary. Configuration comes from `Settings`, not scattered environment reads.

## Frontend Ownership

| Path | Owns |
| --- | --- |
| `frontend/src/App.tsx` | Web application composition; trip state, focus, refresh, mutations, pane/resize state, and panel body ownership |
| `frontend/src/workspaceState.ts` | Canonical web trip revision, identity, and focus reducer |
| `frontend/src/components/CanvasPaneFrame.tsx`, `DetailsPaneShell.tsx`, `AssistantModalShell.tsx` | Render-only desktop pane frames and controls |
| `frontend/src/components/DesktopToolbar.tsx`, `MobileWorkspaceShell.tsx` | Render-only responsive workspace chrome |
| `frontend/src/components/ErrorBanner.tsx` | Render-only workspace error alert |
| `frontend/src/components/AccountSettingsHub.tsx` | Web account/settings section ownership; delegates persisted destinations to existing auth, preferences, analytics, and privacy boundaries |
| `frontend/src/components/SettingsModal.tsx` | Persisted Travel Profile editing and profile-summary conflict handling |
| `frontend/src/components/MapPanel.tsx` | Google Maps lifecycle, refs, drawing, viewport mutation, focus coordination, and compatibility re-exports |
| `frontend/src/components/map/` | Pure map icon generation, focus matching, route/day derivation, and Google-place candidate conversion |
| `frontend/src/components/` | Production UI components and pane interactions |
| `frontend/src/hooks/` | Web state synchronization and reusable client behavior |
| `frontend/src/lib/` | API client, mapping, formatting, and browser utilities |
| `frontend/src/types.ts` | Web-local types not owned by the shared client package |
| `frontend/e2e/` | Playwright end-to-end behavior |
| `frontend/labs/` | Isolated UX experiments only, never production runtime code |
| `mobile/app/` | Expo Router screens |
| `mobile/components/` | Native UI components |
| `mobile/providers/` | Native identity and application providers |
| `mobile/lib/` | Native platform helpers |
| `packages/tripplanner-client/` | Shared web/native request, response, event, and identity contracts |

The React workspace has one owner for current trip revision, identity, selection,
and focus. Async reads must be aborted, revision-guarded, or identity-guarded so
stale responses cannot overwrite newer state. Web and native should share
contracts, not component implementations.

## API and Identity Contracts

- Hosted identity is derived from signed Google credentials, native bearer tokens,
  or guest capability credentials. Never trust a caller-supplied account ID.
- Guest trip access is capability-scoped. Account ownership and guest capability
  must not be conflated.
- Mutations use the persisted trip revision as an optimistic concurrency boundary.
  A stale write must fail rather than overwrite newer work.
- SSE event names and payloads are client contracts. Change producers, shared
  types, and consumers together.
- `/healthz` is the liveness/readiness surface used by deployment smoke.
- The production SPA is mounted by FastAPI; Vite is development-only.
- CORS allowlists and hosted redirect behavior come from environment-specific
  configuration.

## Persistence Contracts

Local JSON and Cosmos implementations remain selectable through configuration.
Hosted environments use Cosmos; direct local CLI use may retain JSON fallback.

Cosmos containers have explicit ownership:

| Container | Stores |
| --- | --- |
| `trips` | Persisted trip documents and revisions |
| `conversations` | Assistant conversation state |
| `events` | Durable trip events and delivery metadata |
| `about_me` | Preference profiles |
| `email_exports` | Idempotent export records |
| `guest_credentials` | Guest capability records |

Canary and production databases are isolated within the shared Cosmos account.
Local emulator data is also isolated and must never be reset automatically. Data
copy is not backup; use the guarded backup/recovery procedure for recoverability
evidence.

## Tool and Provider Boundaries

| Area | Primary paths | Contract |
| --- | --- | --- |
| Destination discovery | `tools/destinations.py`, `tools/search.py` | Return grounded options with source context |
| Flights and hotels | Stable agent tools plus `providers/registry.py` | Prefer live availability; label fallback data accurately |
| Activities | Existing Viator/Amadeus provider boundaries | Preserve provenance and handoff material |
| Maps and geocoding | Map/location tools plus frontend map utilities | Keep coordinates and selected itinerary synchronized |
| Preferences | About Me extractor, apply logic, and store | Merge additively unless the owner explicitly removes data |
| Email/export | Export tool and external operation ledger | Retried requests must not duplicate delivery records |

Booking means grounded selection and verified handoff material. The application
does not purchase, pay, cancel, or manage provider orders.

## Key Data Flows

### Assistant turn

```text
POST /api/.../messages
  -> authenticate account or guest capability
  -> apply admission and workspace limits
  -> load trip and conversation
  -> stream graph events over SSE
  -> execute phase-eligible tools
  -> persist trip/conversation changes
  -> emit revision-aware client events
```

### Detail or map edit

```text
user action
  -> shared client request with expected revision
  -> API authorization and validation
  -> persisted mutation
  -> revised trip view
  -> one workspace state update
```

### Preference update

```text
conversation or explicit edit
  -> extract structured preference
  -> additive merge
  -> persist About Me profile
  -> apply only at relevant planning boundaries
```

## Repository Map

| Path | Purpose |
| --- | --- |
| `.github/copilot-instructions.md` | Durable coding-agent rules and canonical pointers |
| `docs/README.md` | Documentation index and ownership |
| `docs/PRODUCT.md` | Product intent and interaction rules |
| `docs/REQUIREMENTS.md` | Current capabilities, gaps, and roadmap |
| `docs/ENGINEERING_LEARNINGS.md` | Durable lessons from observed failures |
| `docs/feature-briefs/` | Owner-approved active milestone scope |
| `docs/roadmap/` | Candidate and deferred ideas |
| `docs/ux-experiments/` | UX Lab decisions and lifecycle records |
| `docs/operations/deployment-flow.md` | Canonical canary, production, monitoring, and rollback runbook |
| `docs/operations/backup-recovery.md` | Guarded backup and restore drill |
| `docs/development/parallel-agent-development.md` | Primary/worker synchronization and integration workflow |
| `infra/` | Azure IaC and approval-gated operational scripts |
| `scripts/README.md` | Developer workflow and utility script ownership |
| `scripts/user/` | Owner-facing sync and run launchers |
| `scripts/dev/` | Local stack, worktree synchronization, and UI snapshot engines |
| `scripts/` | Local setup, smoke, migration, and diagnostic helpers |
| `tests/` | Python unit and integration tests |
| `docs/reference/` | Indexed owner inputs, decision history, and dated technical snapshots |

## Validation Commands

Run the narrowest command that exercises the changed ownership boundary.

```powershell
# Python tests
.venv\Scripts\python.exe -m pytest -q

# Python lint
.venv\Scripts\python.exe -m ruff check src tests

# Frontend typecheck and unit tests
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run

# Frontend production build
npm --prefix frontend run build

# Shared client
npm --prefix packages/tripplanner-client test

# Mobile typecheck and lint
npm --prefix mobile run typecheck
npm --prefix mobile run lint

# Documentation/patch hygiene
git diff --check
```

Use focused pytest targets or frontend tests during iteration. Workers use
server-free validation unless the owner explicitly authorizes stack changes.
MasterAgent in the primary workspace owns local stack lifecycle and manual-test health.

## Deployment and Operations

The release procedure is [operations/deployment-flow.md](operations/deployment-flow.md).
Infrastructure topology and script ownership are in [infra/README.md](../infra/README.md).
The non-negotiable gates are:

- Image publication is manual.
- Canary builds and tests an immutable Git-SHA image.
- Production promotes the exact canary-tested image without rebuilding.
- Production requires the exact `APPROVE_PROD_DEPLOYMENT` phrase and owner approval.
- Rollback activates a prior revision and does not undo data writes.
- Azure OpenAI data-plane API version is `2024-10-21`; `2024-11-20` is a model
  snapshot, not a valid API version.

## Change Routing

| Change | Start here | Also verify |
| --- | --- | --- |
| Agent/tool behavior | `graph.py`, owning tool, nearby tests | Prompt and SSE effects |
| API or identity | `api.py`, shared client contract | Web/native consumers and authorization tests |
| Trip display semantics | `web/trip_view.py` | Web/native rendering and persisted revision |
| Web interaction | Owning component/hook | `App.tsx` state ownership and e2e behavior |
| Native interaction | Owning screen/provider | Shared client compatibility |
| Persistence | Persistence interface and selected implementation | Both local and Cosmos behavior |
| Azure resources | Owning Bicep/script | Dry run, canary flow, environment isolation |
| Product scope | `PRODUCT.md` or owner-edited feature brief | Requirements baseline after implementation |
| Capability status | `REQUIREMENTS.md` | Append dated decision when relevant |

Update this map only when ownership, contracts, repository structure, or canonical
commands change. Do not turn it into a release diary or duplicate feature status.
