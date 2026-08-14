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
| `src/tripplanner/graph.py` | Agent/tool loop, model invocation and telemetry, and model-facing tool-result budget |
| `src/tripplanner/graph_policy.py` | Pure forced-tool and completion-requirement precedence, including the semantic tool-phase budget |
| `src/tripplanner/state.py` | Shared graph state and merge behavior |
| `src/tripplanner/prompts.py` | Agent instructions and prompt assembly |
| `src/tripplanner/workflow.py` | Trip-planning workflow helpers |
| `src/tripplanner/api.py` | FastAPI routes, hosted identity boundary, SSE transport, `/providers/status` diagnostics, production SPA mount |
| `src/tripplanner/public_demo.py` | Validated bundled regional demo fallback, Cosmos active-manifest reads, ETags, and atomic monthly refresh |
| `src/tripplanner/chat_interactions.py` | Validated prefilled Assistant input requests |
| `src/tripplanner/planning_intelligence.py` | Pure trip-duration, personal day-capacity, and sparse-itinerary policy |
| `src/tripplanner/place_facts.py` | The only reading of cached place facts: weekday schedules, business status, and the unknown/false distinction the invariants depend on |
| `src/tripplanner/platform_planning_insights.py` | Privacy boundary for versioned cross-user aggregate planning priors |
| `src/tripplanner/tools/trip_shape.py` | Read-only model tool exposing auditable trip-shape recommendations |
| `src/tripplanner/request_identity.py` | Signed web, native, and guest principal resolution |
| `src/tripplanner/request_limits.py` | Chat/replay rate limits, concurrency, and workspace exclusion |
| `src/tripplanner/cli.py` | Local command-line experience |
| `src/tripplanner/config.py` | Pydantic environment settings |
| `src/tripplanner/models.py` | Core trip and itinerary models |
| `src/tripplanner/json_store.py` | Atomic local JSON replacement and Windows-lock retry |
| `src/tripplanner/http_client.py` | Outbound HTTP runtime: pooled connections and TLS reuse, per-endpoint latency budget, circuit breaking, and `outbound_call` telemetry. Every remote dependency goes through it |
| `src/tripplanner/circuit_breaker.py` | Pure per-endpoint breaker state machine (closed/open/half-open) |
| `src/tripplanner/concurrency.py` | Shared bounded fan-out for independent remote work; a failed branch degrades to `None` |
| `src/tripplanner/web/trip_view.py` | UI-independent trip view model and display semantics |
| `src/tripplanner/web/map_view.py` | Interactive-map view-model assembly from resolved pins |
| `src/tripplanner/web/day_journey.py` | Transfer-day journey model: path, terminals, inter-city edges, map framing |
| `src/tripplanner/web/chat_store.py` | Conversation and replay persistence |
| `src/tripplanner/web/travel_documents.py` | Traveller document field vault: allowlist, identity-number masking, and persistence. Never stores a file |
| `src/tripplanner/web/document_readiness.py` | Deterministic passport, visa, insurance, and permit checks against the active trip; silent unless the trip is known to cross a border |
| `src/tripplanner/web/place_country.py` | Resolves a free-text place to its country via Open-Meteo geocoding, cached per string |
| `src/tripplanner/web/document_extract.py` | Single-pass field extraction from a photo or pasted text; keeps nothing |
| `src/tripplanner/web/external_operations.py` | Idempotency ledger for outbound provider writes |
| `src/tripplanner/persistence.py` | Local JSON persistence boundary |
| `src/tripplanner/storage_cosmos.py` | Cosmos implementation and conditional replacement |
| `src/tripplanner/trip_events.py` | Durable trip event ownership |
| `src/tripplanner/about_me_store.py` | Preference profile persistence |
| `src/tripplanner/export.py` | Export composition |
| `src/tripplanner/observability.py` | Structured events and request diagnostics |
| `src/tripplanner/debug_store.py` | Local-only archive of real trips for debugging and emulator restore; never active in hosted mode |
| `src/tripplanner/ops_metrics.py` | Content-free rolling request, model, chat-turn, product-funnel, engagement, and acquisition aggregates for the hidden owner dashboard |
| `src/tripplanner/error_analysis.py` | Local and canary failure classification and reports |
| `src/tripplanner/critics.py` | Deterministic quality checks |
| `src/tripplanner/providers/` | Normalized travel provider clients, capability registry, TTL/fallback runtime, and non-secret readiness status |
| `src/tripplanner/tools/` | LangChain tools and stable agent/provider boundaries |
| `scripts/mac/` | macOS `.command` launchers mirroring Windows root, user, sandbox, canary, and production entry points |

Tools use `@tool`. Keep provider HTTP details behind the existing client or tool
boundary. Configuration comes from `Settings`, not scattered environment reads.

## Frontend Ownership

| Path | Owns |
| --- | --- |
| `frontend/src/publicEntry/Root.tsx`, `publicEntryState.ts` | Public-entry gating, the permanent `/welcome` route back to the landing experience, and page-independent account-controller mounting |
| `frontend/src/publicEntry/publicDemoRuns.json`, `demoRun.ts` | Ten self-contained regional public-demo artifacts, deterministic mapping, whole-artifact API replacement, and display-currency presentation |
| `frontend/src/App.tsx` | Web application composition; trip state, refresh, mutations, pane/resize state, and panel body ownership |
| `frontend/src/components/ChatPanel.tsx` | Assistant transcript presentation, composer, trip-input UI, and transcript loading/cache coordination |
| `frontend/src/hooks/useChatStream.ts` | Assistant SSE lifecycle, progress timing, cancellation, retry state, trip-input requests, and workspace turn-status publication |
| `frontend/src/workspaceState.ts` | Canonical web trip revision, identity, and focus reducer |
| `frontend/src/components/CanvasPaneFrame.tsx`, `DetailsPaneShell.tsx`, `AssistantModalShell.tsx` | Render-only desktop pane frames and controls |
| `frontend/src/components/DesktopToolbar.tsx`, `MobileWorkspaceShell.tsx` | Render-only responsive workspace chrome |
| `frontend/src/lib/notices.ts` | Global notice channel: id-keyed upsert, tone priority, and success auto-expiry |
| `frontend/src/components/StatusBar.tsx` | Render-only toolbar and mobile presentation of the single active notice |
| `frontend/src/lib/displayPreferences.ts` | Display country, language, and currency storage; fixed standard option sets, legacy-value migration, locale derivation, and money/unit formatting |
| `frontend/src/components/AccountSettingsController.tsx`, `accountSettings.ts` | Page-independent account/settings ownership, auth and privacy actions, destination routing, and reusable open command |
| `frontend/src/components/AccountSettingsHub.tsx` | Account/settings render surface; delegates persisted destinations to existing auth, preferences, documents, analytics, and privacy boundaries |
| `frontend/src/components/TravelDocumentsVault.tsx` | Travel-document capture, review, reveal, and deletion. The trip surface only shows the gap badge |
| `frontend/src/components/SettingsModal.tsx` | Persisted Travel Profile editing and profile-summary conflict handling |
| `frontend/src/components/MapPanel.tsx` | Google Maps instance lifecycle, UI state, Places interaction, focus coordination, and compatibility re-exports |
| `frontend/src/components/map/` | Map icon generation, focus matching, day and dedicated-drive route derivation, Google-place candidate conversion, React-independent overlay synchronization, and viewport mutation |
| `frontend/src/components/ItineraryPanel.tsx`, `ItineraryStopRow.tsx` | Itinerary loading, mutation, day composition, and stop-row presentation ownership |
| `frontend/src/components/` | Production UI components and pane interactions |
| `frontend/src/components/map/placeIdentity.ts` | Conservative hotel identity shared by itinerary and map labels |
| `frontend/src/lib/itineraryFilters.ts` | Shared presentation-only classification and union filtering for Itinerary rows and Map geometry |
| `frontend/src/hooks/useWorkspaceFocus.ts` | Mutually exclusive place, identified drive/route, day-circuit, and all-days focus transitions and repeat-action tokens |
| `frontend/src/hooks/` | Web state synchronization and reusable client behavior |
| `frontend/src/lib/` | API client, mapping, formatting, and browser utilities |
| `frontend/src/ops/OpsDashboard.tsx` | Direct-only Business and System Health views; server authorization remains authoritative |
| `frontend/src/types.ts` | Web-local types not owned by the shared client package |
| `frontend/e2e/` | Playwright end-to-end behavior |
| `frontend/labs/` | Isolated UX experiments only, never production runtime code |
| `mobile/app/` | Expo Router screens |
| `mobile/components/` | Native UI components |
| `mobile/providers/trip-provider.tsx` | Native trip context composition plus account and chat orchestration |
| `mobile/providers/use-saved-trip-lifecycle.ts` | Serialized saved-trip switch and new-trip lifecycle |
| `mobile/providers/use-trip-mutations.ts` | Serialized select, deselect, and booking mutations through authoritative refresh |
| `mobile/lib/` | Native platform helpers |
| `packages/tripplanner-client/` | Shared web/native request, response, event, and identity contracts |
| `packages/tripplanner-client/src/serialized-mutation.ts` | Shared FIFO client mutation serialization and failure recovery |

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
- Native builds require an explicit `EXPO_PUBLIC_API_BASE_URL`; an unconfigured
  development build must never fall through to production.

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
| `public_demo_runs` | Immutable regional public-demo artifacts and the shared `_public` active manifest |

Canary and production databases are isolated within the shared Cosmos account.
Local emulator data is also isolated and must never be reset automatically. Data
copy is not backup; use the guarded backup/recovery procedure for recoverability
evidence.

## Tool and Provider Boundaries

| Area | Primary paths | Contract |
| --- | --- | --- |
| Destination discovery | `tools/destinations.py`, `tools/search.py` | Return grounded options with source context |
| Flights, hotels, activities, and tickets | Stable agent tools plus `providers/registry.py`, `providers/runtime.py`, and `providers/cache.py` | Prefer free/sandbox active providers, cache before fan-out, fall back in order, and label evidence/freshness accurately. A provider that returns nothing must fall through to the next source, never end the search |
| Item comparisons and overrides | `decisions/`, provider search tools, `web/trip_view.py`, and `frontend/src/components/DecisionPanel.tsx` | Persist candidates from the exact search response, rank with kind-specific deterministic rules, mutate through the active-trip owner, and keep opaque provider references out of display and share contracts |
| Currency normalization | `providers/fx.py` consumed by `decisions/rules.py` | Published ECB reference rates, cached; an unavailable rate drops the money term rather than comparing raw amounts across currencies |
| Trip cost evidence and what-if | `decisions/trip_cost.py`, `decisions/budget_what_if.py`, `providers/fx.py`, and `web/budget.py` | Classify selected items as live, stale, unverified or unpriced; retain published timestamped FX provenance; label incomplete headroom as estimated; generate cheaper exact-alternative proposals only on explicit request |
| Gated provider candidates | `providers/registry.py` catalog plus disabled experimental adapters | Do not auto-enable without current approved API access and acceptable terms |
| Maps and geocoding | `tools/routing.py`, optional `providers/openrouteservice.py`, and frontend map utilities | Google Routes is primary; OpenRouteService is a coordinate-only free-tier fallback; keep coordinates and selected itinerary synchronized |
| Preferences | About Me extractor, apply logic, and store | Merge additively unless the owner explicitly removes data |
| Email/export | Export tool and external operation ledger | Retried requests must not duplicate delivery records |

Booking means grounded selection and verified handoff material. The application
does not purchase, pay, cancel, or manage provider orders.

### Outbound call rules

Every remote dependency is called through `http_client`. Never use `httpx.get`,
`httpx.post`, or a per-call `httpx.Client`: that rebuilds the TLS context per
call and opts out of the shared budget, breaker, and telemetry.

- The endpoint identity is the URL host, so a new provider is pooled, budgeted,
  breakered, and measured with no registration step.
- A latency budget belongs to the endpoint (`_ENDPOINT_POLICIES`), not to the
  call site. Pass an explicit `timeout` only for a call that is genuinely slower
  than its endpoint's normal work, and say why.
- `CircuitOpenError` subclasses `httpx.HTTPError`, so an open circuit degrades
  through the same path as an unreachable provider.
- Independent remote work is composed with `concurrency.run_parallel`, not run
  in sequence. Sequential fallback within one capability stays sequential.

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
| `devconfigs/` | Portable, secret-free developer settings, apply logic, and configuration history |
| `docs/README.md` | Documentation index and ownership |
| `docs/PRODUCT.md` | Product intent and interaction rules |
| `docs/REQUIREMENTS.md` | Current capabilities, gaps, and roadmap |
| `docs/ENGINEERING_LEARNINGS.md` | Durable lessons from observed failures |
| `docs/feature-briefs/` | Owner-approved active milestone scope |
| `docs/roadmap/` | Candidate and deferred ideas |
| `docs/ux-experiments/` | UX Lab decisions and lifecycle records; `LAB_SELECTIONS.json` is the tracked canonical handoff and implementation history |
| `docs/operations/deployment-flow.md` | Canonical canary, production, monitoring, and rollback runbook |
| `docs/operations/backup-recovery.md` | Guarded backup and restore drill |
| `docs/development/new-machine-setup.md` | Canonical one-click Windows/macOS environment recreation and manual sign-in steps |
| `docs/development/parallel-agent-development.md` | Sandbox lifecycle and promotion workflow |
| `infra/` | Azure IaC and approval-gated operational scripts |
| `scripts/README.md` | Developer workflow and utility script ownership |
| `scripts/user/` | Owner-facing run and prompt-log launchers |
| `scripts/user/sandbox/` | Owner-facing sandbox launchers (new, run, serve, stop, update, promote, discard, list) |
| `scripts/canary/` | Owner-facing launcher for the canary deployment |
| `scripts/prod/` | Owner-facing launchers for the approval-gated production deployment and rollback |
| `scripts/dev/` | Local stack, feature sandbox, prompt-log, and UI snapshot engines |
| `scripts/` | Local setup, smoke, migration, and diagnostic helpers |
| `Setup-Tripplanner-Dev.cmd` | One-click full Windows developer environment setup |
| `Setup-Tripplanner-Dev.command` | One-click full macOS developer environment setup |
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
