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
| `src/tripplanner/agents/trip_agent.py` | Phase-selected tool sets and the exhaustive read/trip-write/profile-write/external-write capability registry used by proposal-only mode |
| `src/tripplanner/chat_turn.py` | Transport-neutral replay/admission, cap and conversation-limit decisions, interrupted-turn persistence, final transcript persistence, passive learning, and completion telemetry shared by JSON and SSE chat |
| `src/tripplanner/api.py` | FastAPI routes, hosted identity boundary, JSON/SSE transport adaptation and stream events, `/providers/status` diagnostics, production SPA mount |
| `src/tripplanner/public_demo.py` | Validated bundled regional demo fallback, Cosmos active-manifest reads, ETags, and atomic monthly refresh |
| `src/tripplanner/chat_interactions.py` | Validated prefilled Assistant input requests |
| `src/tripplanner/planning_intelligence.py` | Pure trip-duration, personal day-capacity, and sparse-itinerary policy |
| `src/tripplanner/place_facts.py` | The only reading of cached place facts: weekday schedules, business status, place identity, and the unknown/false distinction the invariants depend on |
| `src/tripplanner/authorship.py` | Per-stop ownership: which stops the traveller chose and a rebalance may not move |
| `src/tripplanner/web/holidays.py` | Public-holiday calendar per country and year; an unreadable calendar stays unknown |
| `src/tripplanner/web/trip_verification.py` | The certificate: which checks ran, which failed, and which could not be evaluated |
| `src/tripplanner/web/trip_freshness.py` | Explicit itinerary place-fact recheck, stable before/after snapshots, and source-linked seasonal or renovation closure advisories |
| `src/tripplanner/tools/trip_rebalance.py` | Whole-trip arrangement search over legal slots, priced in minutes of regret |
| `src/tripplanner/tools/trip_history.py` | Active and saved-trip persistence facade, stable trip IDs, history numbering, listing, and deletion across local JSON and Cosmos |
| `src/tripplanner/trip_models.py` | Tolerant typed contracts for persisted trips, partial mutations, revisions, and mutation outcomes |
| `src/tripplanner/trip_repository.py` | Canonical versioned trip storage, conditional Cosmos retries, local per-trip locking, and active-pointer compatibility |
| `src/tripplanner/request_state.py` | Lazy request-scoped snapshots for active trips, preferences, and transcripts, with copy isolation and read-your-writes updates |
| `src/tripplanner/tools/itinerary_edit.py` | Pure itinerary placement, timing, rebalancing, leg settling, and repair helpers |
| `src/tripplanner/web/trip_repair.py` | Repair pass: clears the planner's own contradictions, reports the ones it may not touch |
| `src/tripplanner/platform_planning_insights.py` | Privacy boundary for versioned cross-user aggregate planning priors |
| `src/tripplanner/tools/trip_shape.py` | Read-only model tool exposing auditable trip-shape recommendations |
| `src/tripplanner/request_identity.py` | Signed web, native, and guest principal resolution |
| `src/tripplanner/request_limits.py` | Chat/replay rate limits, concurrency, and workspace exclusion |
| `src/tripplanner/conversation_limits.py` | Durable environment-wide daily, ISO-week, and lifetime admission ceilings for new-trip and existing-trip model conversations |
| `src/tripplanner/cli.py` | Local command-line experience |
| `src/tripplanner/config.py` | Pydantic environment settings |
| `src/tripplanner/caching.py` | Shared memory/Redis backend and environment-wide TTL policy for disposable runtime caches; stable and volatile regions have independent no-expiry overrides |
| `src/tripplanner/places_budget.py` | Default-deny paid-provider execution authorization for explicit user-interaction and corpus-generation scopes, plus shared Places text-search, review-details, and photo-media ceilings; parallel workers consume one thread-safe budget |
| `src/tripplanner/tools/google_places.py`, `place_hours.py`, `routing.py`; `src/tripplanner/web/itinerary_export.py` | Lowest shared paid-Google cache boundaries for successful Places queries/reviews, hours payloads, Routes responses, and Static Maps images; reads precede paid-budget consumption so direct and graph callers share results |
| `src/tripplanner/models.py` | Core trip and itinerary models |
| `src/tripplanner/json_store.py` | Atomic local JSON replacement and Windows-lock retry |
| `src/tripplanner/http_client.py` | Outbound HTTP runtime: pooled connections and TLS reuse, per-endpoint latency budget, circuit breaking, `outbound_call` telemetry, and a second default-deny check for known billable Google hosts. Every remote dependency goes through it |
| `src/tripplanner/circuit_breaker.py` | Pure per-endpoint breaker state machine (closed/open/half-open) |
| `src/tripplanner/concurrency.py` | Shared bounded fan-out for independent remote work; a failed branch degrades to `None` |
| `src/tripplanner/web/trip_view.py` | UI-independent trip view model and display semantics |
| `src/tripplanner/web/map_view.py` | Interactive-map view-model assembly from resolved pins |
| `src/tripplanner/web/day_journey.py` | Transfer-day journey model: path, terminals, inter-city edges, map framing |
| `src/tripplanner/web/chat_store.py` | Conversation and replay persistence |
| `src/tripplanner/web/trip_feedback.py` | Append-only trip feedback persistence and trip-scoped deletion |
| `src/tripplanner/web/travel_documents.py` | Traveller document field vault: allowlist, identity-number masking, and persistence. Never stores a file |
| `src/tripplanner/web/document_readiness.py` | Deterministic passport, visa, insurance, and permit checks against the active trip; silent unless the trip is known to cross a border |
| `src/tripplanner/web/place_country.py` | Resolves a free-text place to its country via Open-Meteo geocoding, cached per string |
| `src/tripplanner/web/document_extract.py` | Single-pass field extraction from a photo or pasted text; keeps nothing |
| `src/tripplanner/web/external_operations.py` | Idempotency ledger for outbound provider writes |
| `src/tripplanner/web/itinerary_email.py` | Itinerary email composition handoff, ACS/SMTP delivery, provider usage telemetry, mail-client fallback, and durable idempotency orchestration; `api.py` retains identity and HTTP adaptation |
| `src/tripplanner/persistence.py` | Local JSON persistence boundary |
| `src/tripplanner/storage_cosmos.py` | Cosmos implementation and conditional replacement |
| `src/tripplanner/secondary_cache.py`, `cache_merge.py` | Optional cache-only Cosmos client and shared timestamp-aware merge policy; fixed Places/global-tool partitions, fail-open reads, asynchronous tool writes, and ETag retries |
| `src/tripplanner/trip_events.py` | Durable trip event ownership |
| `src/tripplanner/about_me_store.py` | Preference profile persistence |
| `src/tripplanner/export.py` | Export composition |
| `src/tripplanner/observability.py` | Structured events and request diagnostics |
| `src/tripplanner/debug_store.py` | Internal implementation of the Trip Flight Recorder: automatic local-only history of real trip revisions for investigation and emulator restore; never active in hosted mode |
| `src/tripplanner/validation/` | Trip Quality Audit implementation: Trip Quality Corpus reader, deterministic and owner-rated gates, non-gating experiential scores, grouped findings, baseline, immutable `audit/reports/` history, comparable-run summaries (brief 004), and durable provenance aliases used by local inspection links |
| `src/tripplanner/validation/harness/`, `scripts/runtime_evidence_gate.py` | Correlated scenario execution and evidence capture; deterministic plan-eval namespace; unified measured usage, catalog-estimated cost, optional billing reconciliation, cache, amplification, performance, quality, model-round, throttle, retry-delay, and token reports. The hermetic comparison gate requires six representative scenarios, material round reduction, bounded p95 latency, no quality regression, and successful degradation before behavior-sensitive runtime policy changes. `tripplanner.evals` remains the compatibility API |
| `src/tripplanner/validation/market_catalog.py`, `india_heuristic_matrix.py`, `india_outbound_matrix.py` | Deterministic weighted India-domestic and India-outbound corpus scenarios; exact dedupe, destination-aware durations, audience priors, and evidence posture from `docs/research/india-*-2026-08.md` |
| `src/tripplanner/ops_metrics.py` | Content-free rolling request, model, chat-turn, timed-operation, product-funnel, engagement, and acquisition aggregates for the hidden owner dashboard |
| `src/tripplanner/provider_usage.py`, `usage_attribution.py`, `interaction_telemetry.py` | Content-free provider/model ledger and interaction timeline; one bounded hosted document per attributed interaction retains ordered allowlisted events, nested call detail, new-trip/update classification, and request, trip, audit, automation, and background attribution while measured calls/tokens stay distinct from versioned catalog cost estimates, cache savings, and unknown-price calls. Local development additionally writes one fail-open study artifact under `TRIPPLANNER_HOME/trip-telemetry/interactions/`; hosted environments never write it |
| `src/tripplanner/error_analysis.py` | Local and canary failure classification and reports |
| `src/tripplanner/critics.py` | Deterministic quality checks |
| `src/tripplanner/providers/` | Normalized travel provider clients, capability registry, TTL/fallback runtime, and non-secret readiness status |
| `src/tripplanner/tools/` | LangChain tools and stable agent/provider boundaries |
| `scripts/mac/` | macOS `.command` launchers mirroring Windows root, user, sandbox, canary, and production entry points |
| `scripts/dev/emergency-control.ps1` | Extensible cross-cloud emergency orchestration; status by default, explicit provider/environment scope, preflighted approvals, and delegation to allowlisted provider controls |
| `scripts/dev/apply-runtime-config.ps1` | Common owner-facing registry for read-only drift status and approved same-image runtime synchronization across canary and production |
| `infra/azure/set-google-runtime-access.ps1` | Guarded Google runtime synchronization for canary and production; coordinates profile desired state and GCP Service Usage with a verified same-image Container Apps revision, without an image build or Bicep deployment |
| `scripts/dev/multiagent_core.py` | Pure multiagent coordination logic: `owner:ready` eligibility, issue-body plus chronological-comment handoffs, comment-aware footprint collisions, attempt numbering, audit fingerprints, leases, and `/planner` audit links carrying immutable record IDs |
| `scripts/dev/multiagent.py` | Multiagent runtime: dedicated Coordinator publication, post-publish sandbox sync, full GitHub issue-thread intake, autopilot workers, remote-verified attempt SHAs, validated `origin/master` baselines, slots, supervision, batch integration, and audit proposals with representative trip/UX evidence plus opt-in exact-day screenshots on the `audit-evidence` branch |
| `scripts/dev/full-2way-sync.ps1` | Owner-invoked convergence across every local branch and attached worktree; preserves visible WIP, uses temporary worktrees for standalone branches, replays recorded conflict resolutions across every lane type, and retains `sbx` as the registered-sandbox-only scope |
| `scripts/prod-cache-sync.ps1`, `scripts/prod_cache_sync.py` | Owner-triggered, merge-only cache exchange between local `tripplanner-cache` and production; fixed shared/global partition allowlists, destination TTL policy, original evidence timestamps, fail-safe overlapping per-source watermarks, ETag writes, RU/byte/delta JSON reports, and an explicit production-write approval gate |
| `scripts/dev/resolve-all-recorded-conflicts.ps1` | Manual all-worktree recovery: finds pending merges in primary, sandbox, multiagent, and standalone-branch worktrees, delegates recorded `rerere` decisions to the canonical resolver, and aggregates genuinely new conflicts without starting, aborting, or publishing merges |
| `scripts/dev/build_corpus.py`, `scripts/dev/build-corpus.ps1` | Budgeted paid Trip Quality Corpus generation against the launcher checkout's running stack (primary `:8000`/`tripplanner-local`, or a registered sandbox's isolated API/database); the run cap combines measured model-ledger deltas with versioned catalog estimates for billable Google calls attributed to each unique turn, while preserving both components separately from authoritative provider billing; logical attempts use fresh corpus principals so failed chat/trip state cannot contaminate retries, one same-principal recovery turn repairs a completed empty draft, acceptance requires at least two stops per itinerary day, three consecutive completed barren turns stop with a failing exit, generation is serial unless `--workers` explicitly opts into concurrency, and every non-dry run commits and pushes its generated manifest, spend ledger, place cache, and trip files on the current branch; output reports accepted yield, richness, and the cost breakdown; `--country india` covers domestic destinations, while `--market india` alternates domestic and outbound Indian-traveler scenarios |

Tools use `@tool`. Keep provider HTTP details behind the existing client or tool
boundary. Checked-in `config/environments/local.env`, `canary.env`, and
`prod.env` own complete non-secret runtime profiles with matching key sets.
Ignored `.env`, `.env.canary`, and `.env.prod` files are secret overlays;
`.env.example` documents that secret-only surface. Local runtime loads its
profile plus `.env`; hosted deployment scripts load their profile plus matching
secret overlay and pass non-secrets as Container Apps environment variables
while secrets become secret references. `CACHE_TTL_SCALE` adjusts normal
runtime cache lifetimes, and the named search/fare TTL settings provide precise
overrides before that scale is applied. `CACHE_STABLE_FOREVER=1` bypasses both
for Places facts, reviews, routes, country resolution, visa data, and other
stable tool results. `CACHE_VOLATILE_FOREVER=1` independently does the same for
prices, availability, weather, events, web search, FX, and provider caches.
`CACHE_WARM_EVERYTHING=1` expands the Places warm manifest and durable payload
to all available fields, photo references, and signed photo URLs; it changes
surface only, so each entry still follows its stable or volatile TTL policy.
`SECONDARY_DURABLE_CACHE_ENABLED=1` adds a cache-only durable fallback after a
primary durable miss. Its endpoint, database, emulator guard, authentication,
and enablement are independent settings. Fresh shared Places and global tool
hits retain their evidence timestamps and are promoted into the primary cache;
provider results write through to both. Secondary failures open a short local
circuit and never fail an application request. The local profile enables the
emulator database `tripplanner-cache`; canary and production explicitly disable
the feature. User-scoped tool rows and all application data are structurally
excluded.
The production cache synchronizer moves that eligible surface only on owner
request. It merges `places_cache/_shared` and, when enabled by each destination,
`tool_cache/_global_`; user-scoped tool rows and application data never cross
this boundary. Places metadata, reviews, and photos resolve freshness
independently, while tool rows retain an explicit `cached_at`. Copying never
refreshes evidence timestamps or deletes a destination-only entry.
The first successful apply bootstraps from complete snapshots. Subsequent runs
query an overlap behind each source/container `_ts` watermark and point-read only
candidate IDs. The checkpoint is replaced atomically only after every planned
write verifies without an optimistic-concurrency conflict; any partial failure
retains the previous watermark so retrying can repeat work but cannot omit it.
Paid Google Places access requires
both `ENABLE_GOOGLE_PLACES=1` and `GOOGLE_PLACES_API_KEY`; a copied key alone
must never activate billable requests.
Paid base Maps, Google Routes fallback, and Static Maps export similarly require
`ENABLE_GOOGLE_MAPS=1` plus their existing browser or server key. The profile
flags are the sole desired state; `infra/gcp/set-google-places-access.ps1` and
`set-google-maps-access.ps1` synchronize project-level Service Usage and retain
deployment-free emergency off controls. For hosted application behavior,
`infra/azure/set-google-runtime-access.ps1` applies those same flags to canary or
production with a same-image Container Apps revision, verifies readiness and
latest-revision traffic, and never runs a full infrastructure deployment.
Every Azure OpenAI client construction requires `ENABLE_AZURE_OPENAI=1`; endpoint
and key presence alone never permits model spend. The default is fail-closed.
`infra/azure/set-azure-services-access.ps1` owns the profile desired state while
also blocking or restoring the selected OpenAI account's public network access.
Profile changes require a local restart or hosted deployment before application
processes observe them; cloud network enforcement is immediate.

Runtime cache policy is unified, but physical storage is intentionally tiered.
Provider, FX, route, country, and comparison regions use `caching.py`; read-only
tool results and structured Places facts retain specialized Cosmos/local durable
stores while honoring the same `Settings.cache_ttl()` policy. Corpus place facts
are validation evidence, not a runtime cache, and frontend memoization remains
browser-local. Do not describe those persistence and client-state boundaries as
one physical cache backend.

## Frontend Ownership

| Path | Owns |
| --- | --- |
| `frontend/src/publicEntry/Root.tsx`, `publicEntryState.ts` | The `/` public-entry route, `/planner` workspace route, legacy `/welcome` redirect, browser-history transitions, and page-independent account-controller mounting |
| `frontend/src/publicEntry/publicDemoRuns.json`, `demoRun.ts` | Ten self-contained regional public-demo artifacts, deterministic mapping, whole-artifact API replacement, and display-currency presentation |
| `frontend/src/App.tsx` | Web application composition; authoritative trip refresh, pane/resize state, and panel body ownership |
| `frontend/src/hooks/useWorkspaceTripMutations.ts` | Serialized new/reset/add/remove coordination, conflict retry, duplicate-removal suppression, stale identity/epoch rejection, and authoritative mutation response application |
| `frontend/src/components/ChatPanel.tsx` | Assistant transcript presentation, composer, trip-input UI, and transcript loading/cache coordination |
| `frontend/src/hooks/useChatStream.ts` | Assistant SSE lifecycle, progress timing, cancellation, retry state, trip-input requests, and workspace turn-status publication |
| `frontend/src/workspaceState.ts` | Canonical web trip revision, identity, and focus reducer |
| `frontend/src/components/CanvasPaneFrame.tsx`, `DetailsPaneShell.tsx`, `AssistantModalShell.tsx` | Render-only desktop pane frames and controls |
| `frontend/src/components/DesktopToolbar.tsx`, `MobileWorkspaceShell.tsx`, `AccessibleSheet.tsx` | Responsive workspace chrome plus reusable mobile dialog focus containment, Escape/backdrop dismissal, and focus restoration |
| `frontend/src/components/TripFeedbackControl.tsx` | Toolbar thumbs, optional rating/comment popover, and sent-count presentation |
| `frontend/src/lib/notices.ts` | Global notice channel: id-keyed upsert, tone priority, and success auto-expiry |
| `frontend/src/components/StatusBar.tsx` | Render-only toolbar and mobile presentation of the single active notice |
| `frontend/src/lib/displayPreferences.ts` | Display country, language, and currency storage; fixed standard option sets, legacy-value migration, locale derivation, and money/unit formatting |
| `frontend/src/components/AccountSettingsController.tsx`, `accountSettings.ts` | Page-independent account/settings ownership, auth and privacy actions, destination routing, and reusable open command |
| `frontend/src/components/AccountSettingsHub.tsx` | Account/settings render surface; delegates persisted destinations to existing auth, preferences, documents, analytics, and privacy boundaries |
| `frontend/src/components/TravelDocumentsVault.tsx` | Travel-document capture, review, reveal, and deletion. The trip surface only shows the gap badge |
| `frontend/src/components/SettingsModal.tsx` | Persisted Travel Profile editing and profile-summary conflict handling |
| `frontend/src/components/MapPanel.tsx` | Google Maps instance lifecycle, UI state, Places interaction, focus coordination, and compatibility re-exports |
| `frontend/src/components/map/` | Google Maps SDK loading, map icon generation, focus matching, day and dedicated-drive route derivation, Google-place candidate conversion, React-independent overlay synchronization, and viewport mutation |
| `frontend/src/components/ItineraryPanel.tsx`, `ItineraryStopRow.tsx` | Itinerary loading, mutation, day composition, and stop-row presentation ownership |
| `frontend/src/components/` | Production UI components and pane interactions |
| `frontend/src/components/map/placeIdentity.ts` | Conservative hotel identity shared by itinerary and map labels |
| `frontend/src/lib/itineraryFilters.ts` | Shared presentation-only classification and union filtering for Itinerary rows and Map geometry |
| `frontend/src/hooks/useWorkspaceFocus.ts` | Mutually exclusive place, identified drive/route, day-circuit, and all-days focus transitions and repeat-action tokens |
| `frontend/src/hooks/` | Web state synchronization and reusable client behavior |
| `frontend/src/lib/` | API client, mapping, formatting, and browser utilities |
| `frontend/src/ops/OpsDashboard.tsx` | Direct-only Business, API & Cost, and System Health views; one inclusive date filter governs API & Cost, which separates new-trip creation from existing-trip updates, exposes cumulative and average estimates, expands named trips and interactions into provider/operation components, and reports service totals, provider-versus-cache share, estimated cache savings, dataset hit rates, unknown-price coverage, and the unallocated shared-infrastructure boundary; server authorization remains authoritative |
| `frontend/src/types.ts` | Web-local types not owned by the shared client package |
| `frontend/e2e/` | Playwright end-to-end behavior |
| `frontend/labs/` | Isolated UX experiments only, never production runtime code |
| `mobile/app/` | Expo Router screens |
| `mobile/components/` | Native UI components |
| `mobile/providers/trip-provider.tsx` | Native trip context composition plus account and chat orchestration |
| `mobile/providers/use-saved-trip-lifecycle.ts` | Serialized saved-trip switch and new-trip lifecycle |
| `mobile/providers/use-trip-mutations.ts` | Serialized select, deselect, and booking mutations through authoritative refresh |
| `mobile/lib/` | Native platform helpers |
| `packages/tripplanner-client/` | Shared web/native request, response, event, identity, and SSE parsing contracts; platform adapters do not implement another event-stream parser |
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
- `/trip/workspace` returns Details, Map, and Itinerary projections built from one
  loaded plan snapshot. Focus-only navigation remains on `/trip/view` so it does
  not rebuild unrelated workspace projections.
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
The complete trip exists once at `trips/{trip_id}`. `users/active_trip` contains
only `{trip_id, revision}`; readers still accept legacy full active documents.
Every canonical mutation increments `revision`. Cosmos mutations replay semantic
callbacks after conditional-write conflicts, while stale detached saves fail as
HTTP `409 trip_conflict` instead of overwriting a newer trip. A request-scoped
snapshot reuses trip, preference, and transcript reads and is updated after writes.

Cosmos containers have explicit ownership:

| Container | Stores |
| --- | --- |
| `trips` | Persisted trip documents and revisions |
| `conversations` | Assistant conversation state |
| `events` | Durable trip events and delivery metadata |
| `trip_feedback` | Append-only trip feedback submissions; one document per submission |
| `about_me` | Preference profiles |
| `email_exports` | Idempotent export records |
| `guest_credentials` | Guest capability records |
| `public_demo_runs` | Immutable regional public-demo artifacts and the shared `_public` active manifest |
| `places_cache` | Google Places details, shared across users at partition `_shared` |
| `tool_cache` | Results of read-only tools, shared unless the tool is user-specific |
| `provider_usage` | Immutable content-free provider/model interaction batches, partitioned by environment with a 90-day TTL; nested call entries preserve provider, operation, model/SKU, tokens, estimated cost, cache hits/savings, and failures, while allowlisted ordered telemetry events preserve flow and reduce hosted writes to normally one per interaction |

Canary and production databases are isolated within the shared Cosmos account.
Local emulator data is also isolated and must never be reset automatically. Data
copy is not backup; use the guarded backup/recovery procedure for recoverability
evidence.

### Cached external data

Everything fetched from a provider lands in one of three places.

| Source | Store | Freshness | In the repository |
| --- | --- | --- | --- |
| Google Places | `places_cache` + in-process | Configured metadata/review/search/hour TTLs; photo URLs default to 50 min | Yes — `corpus/places.json` |
| Read-only tools (flights, weather, visa, events, search) | `tool_cache` + in-process LRU | per-entry `expires_at`, set per tool | No |
| FX rates | in-process only | 12 hours | No |

Only Places data is committed, because it is audit input rather than a
speed-up. Removing it silences eight rules — `I3`, `I4`, `I9`, `I11` and
`R1`–`R4` — and 605 of 1073 findings, and the audit then reports clean rather
than failing. Tool results are deliberately excluded: a frozen flight price or
weather window preserves something that is meaningless once stale, and no rule
reads them.

`storage_cosmos` gives the two cache containers a **30-day TTL**, the operational
`provider_usage` ledger a **90-day TTL**, and containers holding the user's own
data none. The TTL is a storage backstop, not
the freshness rule: Cosmos resets it on every write, so an entry still in use
never expires and only abandoned ones are reclaimed.

Two things follow that are easy to miss:

- **`corpus/places.json` is exempt from all of this.** It is in git, so it is
  kept indefinitely, including reviews. That is a deliberate choice made while
  the product is small, not an oversight.
- **The 30-day figure has not been checked against provider terms.** Google
  Maps Platform restricts how long Places content may be cached, and that limit,
  not our convenience, is the real ceiling. Revisit both points before the
  product carries real traffic.

#### The two durable copies

A lane's `places_cache` dies with its database, so places it paid Google for are
kept in two places outside it. The reviewable corpus is never read at request
time. The working central cache is the optional secondary durable lookup for
live local requests after a lane-cache miss.

| Copy | Where | Written by | Holds |
| --- | --- | --- | --- |
| Reviewable | `corpus/places.json`, in git | `corpus_cache.py --save`, and the sandbox discard | By default: grounded entries, reviews, and one photo reference, without signed URLs. With `CACHE_WARM_EVERYTHING=1`: every available entry and field, including all photo references and signed URLs |
| Working | `tripplanner-cache` on the emulator | Best-effort runtime read-through/write-through; `corpus_cache.py --sync` remains an explicit recovery/import utility | Shared Places and global tool-cache evidence, plus whatever no one has exported to git yet |

The split exists because the git file is 5 MB of tracked content and the sandbox
flows require a clean worktree — writing it on every stack start would leave the
primary checkout dirty. The emulator database can be written as often as we like.
`corpus_cache.py` with no arguments prints how many places the working copy holds
that the reviewable one does not, which is when `--save` is worth running.

## Tool and Provider Boundaries

| Area | Primary paths | Contract |
| --- | --- | --- |
| Destination discovery | `tools/destinations.py`, `tools/search.py` | Return grounded options with source context |
| Flights, hotels, activities, and tickets | Stable agent tools plus `providers/registry.py`, `providers/runtime.py`, and `providers/cache.py` | Prefer free/sandbox active providers, cache before fan-out, fall back in order, and label evidence/freshness accurately. A provider that returns nothing must fall through to the next source, never end the search |
| Item comparisons and overrides | `decisions/`, provider search tools, `web/trip_view.py`, and `frontend/src/components/DecisionPanel.tsx` | Persist candidates from the exact search response, rank with kind-specific deterministic rules, mutate through the active-trip owner, and keep opaque provider references out of display and share contracts |
| Currency normalization | `providers/fx.py` consumed by `decisions/rules.py` | Published ECB reference rates, cached; an unavailable rate drops the money term rather than comparing raw amounts across currencies |
| Trip cost evidence, recheck, and what-if | `decisions/trip_cost.py`, `decisions/price_recheck.py`, `decisions/budget_what_if.py`, provider registry, `web/budget.py`, and `web/trip_view.py` | Classify quote evidence; compare exact products only with known mandatory costs/FX; apply consented public benefit terms; explicitly verify stale exact flight offers or re-search exact-context stays; persist bounded observations without replacing selections |
| Advisory effort intelligence | `tools/trip_effort.py`, persisted weather, structured place/activity-provider evidence, and `web/trip_view.py` | Rank with physical, transit, logistical, circadian, and weather-exposure effort; emit at most grounded advisory notes and one pacing statement; never block or infer absent evidence |
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
| `docs/operations/gcp-billing-guardrails.md` | Reproducible Google Cloud budget, quota, and billing-shutoff setup |
| `docs/operations/azure-billing-guardrails.md` | Reproducible Azure budget and alert setup, including hard-cap limitations |
| `infra/billing-guardrails.json` | Owner-facing cloud service state, budgets, quotas, and account identifiers |
| `infra/{gcp,azure}/apply-billing-guardrails.ps1` | Idempotent cross-platform guardrail provisioning scripts |
| `infra/gcp/set-google-places-access.ps1` | Immediate no-deployment Places Service Usage control and central desired-state apply |
| `infra/azure/set-azure-services-access.ps1` | Reversible Azure usage and serving-only control for `local`, `canary`, `prod`, or all allowlisted Tripplanner resource groups; disable is immediate, enable is approval-gated, shared Cosmos changes only with a full `all`, and no resource or data is deleted |
| `scripts/dev/emergency-bringdown.ps1` | Reversible canary/production serving stop over the Azure control's serving-only mode; status by default, immediate down, approval-gated up, and no dependency or data changes |
| `infra/show-billing-status.ps1` | Read-only month-to-date spend report for both clouds |
| `infra/gcp/billing-shutoff/` | Cloud Function that detaches billing when the global GCP budget breaks |
| `docs/development/new-machine-setup.md` | Canonical one-click Windows/macOS environment recreation and manual sign-in steps |
| `docs/development/parallel-agent-development.md` | Sandbox lifecycle and promotion workflow |
| `infra/` | Azure IaC and approval-gated operational scripts |
| `scripts/README.md` | Developer workflow and utility script ownership |
| `scripts/win/user/` | Windows owner-facing run and prompt-log launchers |
| `scripts/win/user/sandbox/` | Windows owner-facing sandbox launchers (new, run, serve, stop, update, promote, discard, list) |
| `scripts/win/canary/` | Windows owner-facing launcher for the canary deployment |
| `scripts/win/prod/` | Windows owner-facing launchers for the approval-gated production deployment and rollback |
| `scripts/mac/` | macOS launcher equivalents with the same subfolder layout and base names |
| `scripts/dev/` | Local stack, feature sandbox, prompt-log, and UI snapshot engines |
| `scripts/` | Local setup, smoke, migration, and diagnostic helpers |
| `scripts/win/Setup-Tripplanner-Dev.cmd` | One-click full Windows developer environment setup |
| `scripts/mac/Setup-Tripplanner-Dev.command` | One-click full macOS developer environment setup |
| `tests/` | Python unit and integration tests |
| `docs/reference/` | Indexed owner inputs, decision history, and dated technical snapshots |

## Validation Commands

Run the narrowest command that exercises the changed ownership boundary.

```powershell
# Python fast tier (default development loop)
.venv\Scripts\python.exe -m pytest -q -m "not integration"

# Python integration tier
.venv\Scripts\python.exe -m pytest -q -m integration

# Python complete suite
.venv\Scripts\python.exe -m pytest -q

# Python lint
.venv\Scripts\python.exe -m ruff check src tests

# Frontend typecheck and unit tests
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit

# Frontend ownership-specific or complete tests
npm --prefix frontend run test:labs
npm --prefix frontend run test:inspector
npm --prefix frontend run test:all

# Frontend production build
npm --prefix frontend run build

# Shared client is source-only; validate it through its frontend/mobile consumers.
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
