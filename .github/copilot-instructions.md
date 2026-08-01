# Copilot Instructions — tripplanner

> **Read [docs/README.md](../docs/README.md) (documentation guide),
> [docs/CODEMAP.md](../docs/CODEMAP.md) (where),
> [docs/PRODUCT.md](../docs/PRODUCT.md) (what/why + taste), and
> [docs/REQUIREMENTS_V2.md](../docs/REQUIREMENTS_V2.md) (current capability
> baseline + roadmap) FIRST. Consult
> [docs/ENGINEERING_LEARNINGS.md](../docs/ENGINEERING_LEARNINGS.md) for durable
> cross-feature lessons before changing interaction behavior.
> They are the canonical, committed sources of truth and are kept up to date
> with the code. Use them instead of grepping the repo to "rediscover"
> structure or owner intent on every task.

## Agent efficiency rules (avoid wasting the user's time)
- Before substantive work, and after every user prompt, ensure the current agent
  chat has a concrete 4-5 word title summarizing the latest prompt or active task
  (for example, `Debug Azure Model Rate Limits`). Use `/rename <title>` when
  supported. Keep the title only while it still accurately summarizes the latest
  prompt. This applies to existing and new chats in the primary and every
  tripplanner worker VS Code instance.
- Read big chunks (50–200 lines) and read multiple files in parallel.
  Do NOT dribble 5-line reads.
- Batch independent tool calls into ONE turn. Only chain when an output is
  needed for the next input.
- Trust this file + `docs/CODEMAP.md` + `docs/PRODUCT.md` +
  `docs/REQUIREMENTS_V2.md` +
  `/memories/repo/tripplanner.md`. Skip re-exploration on every task.
- Treat `docs/roadmap/FUTURE_FEATURES.md` as the consolidated candidate backlog;
  an entry there is not approval to implement it.
- For a coherent new feature, prefer an owner-edited brief under
  `docs/feature-briefs/`. Treat roadmap entries as candidates, not approval.
- Run validation (tsc, pytest, build) ONCE at the end of a milestone, not
  after every micro-edit (exception: when a mid-edit failure is suspected).
- One milestone = one commit + push. Per owner rule, never leave unpushed work.
- The coding agent owns the local server lifecycle: start, stop, restart, clear
  stale ports, and health-check the canonical stack without handing operations
  back to the owner. After a push, restart affected services when runtime code
  changed. Skip unnecessary restarts for runtime-neutral changes, but ensure the
  stack is running whenever the owner needs to test.
- Do not add docstrings/type-hints/comments to code you didn't touch.

## Development workspace

- The owner's default is this single primary `tripplanner` VS Code workspace,
  working directly on `master` for features, fixes, review, and integration.
- Use persistent `worker-1` / `worker-2` worktrees only when the owner explicitly
  requests parallel development for clear, sizeable, isolated features. They are
  optional capacity, not the normal path; when active, both are independent lanes.
- Each worker owns one narrow PR-sized assignment at a time. Avoid parallel
  assignments that substantially edit the same files or contracts.
- Merge completed branches one at a time through reviewed pull requests using
  merge commits. Active branches then merge `origin/master`, validate affected
  behavior, and push.
- When parallel mode is explicitly active, `scripts/dev/run-latest-code.ps1`:
  it temporarily stashes staged, unstaged, and untracked master work, performs the
  clean guarded Worker 1 then Worker 2 PR merges, restores the local state, and
  only then starts the app. Both workers preflight before either merge. Worker 2
  incorporates Worker 1's new master first. Worker synchronization conflicts abort
  and restore that worker automatically; overlapping restored master changes stop
  for explicit conflict resolution.
- Use `scripts/agent-worktree.ps1` and
  `docs/development/parallel-agent-development.md` for slot creation, synchronization,
  temporary worktrees, and safe cleanup. Do not share `.venv` or mutable
  `node_modules` across worktrees.

## Deployment & Production Gates

**CRITICAL: Never deploy to production without explicit user approval.**

**Image build/push is MANUAL ONLY** — commits do NOT build or push an image
(the GitHub Actions workflow is `workflow_dispatch`-only) so the local loop
stays fast. Build & push only when explicitly asked.

- **Build & push image**: `./infra/push-image.ps1` — builds the Docker image and
  pushes to GHCR tagged with the git short SHA + `latest`. Needs a `docker login
  ghcr.io` session (or set `GHCR_TOKEN`/`CR_PAT` with `write:packages`).
- **Canary (Testing)**: Deploy via `./infra/deploy-canary.ps1` — no approval gate,
  use for all testing. **Builds & pushes the image from current code first by
  default**, then deploys its immutable Git SHA (one-click full deploy). Pass
  `-NoBuild -ImageTag <sha>` to redeploy an existing immutable image.
- **Production (Live)**: Deploy via `./infra/deploy-prod.ps1` — requires manual approval via interactive prompt
  - Resolves and promotes the immutable image currently deployed to canary
  - Script displays readiness checklist
  - Requires you to type `APPROVE_PROD_DEPLOYMENT` (exact, case-sensitive)
  - All prod deployments logged to `logs/deployments-prod.log` with timestamp and approver
  - Pass `-Build` to build+push before the approval gate's deploy step
- **Rollback (Emergencies)**: `./infra/rollback-prod.ps1` — reverts to previous revision without data loss

Canary builds new code by default. Production resolves the exact immutable SHA
currently deployed to canary; do not rebuild normal promotions.
See `docs/operations/deployment-flow.md` for the canonical release runbook.

Resource naming:
- Canary RG: `rg-tripplanner-canary` (app: `canary-app-*`)
- Prod RG: `rg-tripplanner-prod` (app: `prod-app-*`)
- Standardized naming roadmap: See `infra/DEPLOYMENT_PROCESS.md`

## Memory maintenance (KEEP CONTEXT FRESH — do this every session)
Whenever the owner teaches a new preference, taste, or requirement, update
the right place IN THE SAME TURN so future sessions don't relearn it:

| What changed                                | Update                                |
|---------------------------------------------|---------------------------------------|
| Cross-project habit (terse, no servers, …)  | `/memories/preferences.md`            |
| Repo-only gotcha / landmine                 | `/memories/repo/tripplanner.md`        |
| Vision / scope / taste / design language    | `docs/PRODUCT.md` (commit)            |
| Current capability / roadmap status         | `docs/REQUIREMENTS_V2.md` (commit)    |
| Next coherent feature scope                 | `docs/feature-briefs/*.md` (commit)   |
| File layout / commands / contracts          | `docs/CODEMAP.md` (commit)            |
| New requirement / decision (with date)      | `PRD/REQUIREMENTS Auto Log.txt` (commit) |
| Architecture / config shift                 | `README.md` + this file (commit)      |
| Current in-flight TODOs only                | `/memories/session/<topic>.md`        |

The latest instruction always wins — delete stale entries, don't pile up.
Stale memory is worse than no memory.

## What is this project?
An AI-powered trip planner for Munish Goyal (munishgoyal1).
It uses LangGraph with a single Trip Agent + 18 tools to create complete,
bookable travel plans. Searches real flights/hotels/activities (Amadeus),
real ratings & reviews (Google Places), and fresh travel content (Tavily).
Learns from user preferences and past trips.

## Owner & Accounts
- GitHub: munishgoyal1 — repo is private
- Azure: munishgoyal1@gmail.com (personal subscription, gpt-4.1 primary; gpt-4o + gpt-5 also deployed)
- Amadeus: Self-Service API (test environment, 2000 calls/month free)
- Google Places: free $200/month credit (Places API New)
- Google Cloud: separate `aitripplanner-local`, `aitripplanner-canary`, and
  `aitripplanner-prod` projects with environment-owned OAuth clients and
  browser/server Maps keys; one billing account is shared.
- Tavily: free 1000 searches/month

## Codebase Conventions
- Python 3.11+, typed with `from __future__ import annotations`
- Single agent in `src/tripplanner/agents/trip_agent.py`
- Tools as `@tool`-decorated functions (langchain_core.tools)
- Agent exports: `build_trip_system_prompt()` factory (injects today's date) and `TRIP_TOOLS` (list). `TRIP_SYSTEM_PROMPT` snapshot kept for back-compat.
- API clients and search tools go in `src/tripplanner/tools/`
- Config via Pydantic `Settings` from `.env` (see `config.py`)
- Graph in `graph.py` — single-agent tool-calling loop
- Tests in `tests/` — use pytest, no mocks for pure logic tests
- Line length: 100 (ruff)
- No unnecessary comments — only non-obvious choices

## Key Architecture
- `graph.py`: LangGraph StateGraph with agent → tools → agent loop → END
- No router — single trip agent handles everything
- Agent: system prompt + phase-selected tools, bound via `bind_tools()`
- Two entrypoints: CLI (`cli.py`) and FastAPI (`api.py`)

## Working Preferences (from user)
- Always commit AND push after every change
- Keep it simple, modular — no over-engineering
- No major functional changes without user consent
- Update `PRD/REQUIREMENTS Auto Log.txt` when new requirements come in
- Update README.md when architecture changes
- This file must always reflect current state

## Current State (last updated 2026-08-01)
- **Refined Map command hierarchy**: the accepted Map commands direction now uses
  the pane title row for All days/day scope, keeps Add stop directly visible below,
  and compresses schedule span plus route-only evidence into one labeled line.
  Focus semantics, placement, pins, routes, mutations, and cross-pane synchronization
  are unchanged. Pane-local Hide/Maximize styling remains unchanged while a separate
  enhancements and polishing Lab evaluates presentation alternatives.
- **Decision-brief trip snapshot**: implemented Trip Snapshot Lab Option B only
  in the authoritative whole-trip band. Traveler context and an authored or factual
  trip-level narrative stay with identity, booking readiness is explicit, and
  Days/Stay/Places/Flights share one compact facts row. Persisted weather renders
  day evidence; older trips retain a truthful unavailable state. Family/constraint
  evidence remains visible without repeating a vague Trip fit block below Budget;
  day briefs and agenda rows are unchanged.
- **Direct semantic desktop command bar**: implemented Option A from both command
  bar Labs changes only the top row. New trip is a labeled primary command;
  Itinerary, Map, Details, and Assistant remain direct meaning-first controls
  with short wide-desktop labels and compact icon fallbacks. Pane-local Hide and
  Maximize behavior and all workspace UI below the command bar are unchanged.
- **Non-interfering UX Lab change markers**: every individual Lab can outline its
  exact varied preview regions through shared Lab-only annotations. A scope-panel
  toggle hides the portal-rendered, pointer-transparent overlays for a clean view;
  markers add no wrappers, dimensions, or production component styling.
- **Concrete-hotel placeholder synchronization**: selecting one unambiguous real
  hotel replaces stale `Hotel (TBD)` itinerary anchors even when placeholder
  filtering left the prior `selected_hotels` list empty. Existing stop timing is
  retained; the local Mauritius plan was repaired to Preskil Island Resort.
- **Restorable stable UI history**: owner-accepted interface milestones are
  preserved as immutable, remotely pushed `ui-stable/*` tags, with the latest
  three documented under UX experiments. A guarded helper lists, creates, or opens
  snapshots in detached sibling worktrees; restoration remains a new validated
  commit and never resets master or deploys automatically.
- **Explicit UX Lab decision boundaries**: every individual Lab names the exact
  elements varied by its options and separately lists surrounding preview UI that
  is fixed context. Option selection and implementation handoff are limited to
  that declared scope unless owner notes explicitly add another change.
- **Navigable Lab lifecycle handoffs**: catalog filters live only on All Labs,
  In progress, and Completed indexes; each individual experiment has one clear
  return to All Labs. Active handoffs bind the selected option to owner-authored
  modifications and implementation inputs, and can be marked ready, parked with
  that handoff preserved, completed with the decision and notes retained, or
  discarded with option, notes, and browser draft deleted. Parked Labs leave In
  progress and remain grouped on All Labs; completed Labs move to both Completed
  views without implying that production implementation is approved or shipped.
- **Worktree-safe Lab decisions**: all primary and worker Labs servers use one
  machine-level `%LOCALAPPDATA%/Tripplanner/ux-labs/selections.json` authority
  with atomic writes and one previous snapshot. Catalog load failure is explicit
  and never reclassifies missing decisions as active; server state overrides stale
  browser drafts.
- **Shared local diagnostics + model throttle evidence**: every canonical local
  stack writes rotating PII-safe JSON under the primary Git checkout, so primary
  and worker VS Code windows analyze the same log. Final Azure OpenAI rate-limit
  failures retain only safe deployment/status/retry/remaining-quota metadata and
  identify token versus request pressure without logging prompts or response bodies.
- **Destination-safe new-trip persistence**: an explicit whole-trip request for a
  destination different from the active trip now forces `create_trip_plan` before
  itinerary completion or enrichment gates. SSE prose fallback persistence is
  limited to turns that actually created a trip, preventing a missing create call
  from overwriting an unrelated active saved trip.
- **Deterministic mid-chat new trips**: explicit new/separate/another/different
  trip intent preempts completion gates for the currently active trip, runs the
  normal preference kickoff, and then forces `create_trip_plan`. The prior trip
  and its transcript remain separate; the existing carryover path seeds only
  portable context into the new trip chat.
- **Modern web Assistant controls**: the Option B conversation sheet can abort its active SSE
  response through the shared transport, preserves and marks useful partial text,
  and restores the composer without failure/retry state. Completed messages expose
  Copy, and prior user instructions can be revised in the composer and sent as new
  corrective operations so durable itinerary side effects and replay IDs remain honest.
- **Weather-aware itinerary summaries**: Open-Meteo needs no API key and now
  persists normalized trip weather. Live forecast failure falls back to the
  same-season archive; total provider failure permits only an explicitly labeled
  monthly-climate estimate. Trip snapshot and day headers show condition icons,
  temperature/rain context, and deterministic clothing/umbrella guidance.
- **Production customer-flow analytics (Session 86)**: consent-gated GA4 is
  runtime-enabled only in production and uses a small content-free event
  vocabulary for visit-to-planning-to-trip-to-handoff funnels. Query strings,
  trip/chat content, account identity, and other customer data are excluded;
  Account can reopen analytics preferences. Azure Log Analytics remains the
  operational reliability source. Production is configured for GA4 Web stream
  `G-VNTSQG9SWZ`; production release `10963d5` activated consent-gated collection.
- **Production failure alerting + non-production analysis**: the existing PII-safe
  Container Apps Log Analytics stream remains the single hosted telemetry path.
  Production release `10963d5` deployed a stateful five-minute application/chat/
  tool failure rule and owner email Action Group behind the approval gate.
  Local development retains bounded redacted JSON, and one read-only command
  produces grouped local or canary Markdown diagnostics without non-production email.
- **Provider-neutral live travel foundation**: the stable hotel and preferred
  flight tools now select capability-specific providers through a minimal
  registry. LiteAPI supplies normalized read-only hotel rates, flight search,
  and selected-flight verification with provider references, quote timestamps,
  expiry, totals, and explicit evidence status. Legacy Duffel/Amadeus/Google
  fallbacks remain; Google hotel results are labeled metadata-only rather than
  live availability. Explicit refresh bypasses the 60-second inventory cache.
  No prebook, booking, payment, order, or cancellation endpoint exists.
- **Option B Assistant conversation sheet**: the main web app opens Assistant in a
  compact lower-right sheet over the still-usable itinerary/map workspace.
  It closes explicitly or with Escape, reopens from the command bar, and remains
  mounted while hidden so conversation state survives.
  Validated `input_request` events render as compact prefilled controls for all
  supported field kinds and submit through normal chat. New trips deterministically
  load preferences and force this one-step review before plan creation, enumerating
  relevant saved and past-trip context; direct mode proceeds without more questions
  after submit or skip. No Azure deployment is implied.
- **Execution-ready Trip Book Lab**: one realistic London family-trip fixture
  compares a compact operations binder, recommended layered Trip Book, and
  visual journey book across contents, trip brief, executable day, document
  readiness, and evidence-labeled personal context. Production export remains
  unchanged; secure document ingestion and merged-PDF behavior require a later
  owner-approved contract.
- **Assistant-led itinerary foundation**: the selected Option B sheet preserves
  the Lab's preference-aware kickoff, not only its footprint. FastAPI streams the
  validated payload as an additive `input_request` event, and shared web/native
  transport retains it. Hosted deployment remains pending.
- **Truthful itinerary timing + density lab (Session 87)**: Itinerary and Map
  consume one backend-owned day schedule that separates endpoint-to-endpoint E2E
  time from route-only Travel and marks inferred hotel departure/return times as
  estimates. Hotel anchors no longer show generic stay duration, redundant In
  trip state, or invalid exact-delete controls; backend mutation also rejects
  single-anchor removal. The itinerary pane can expand to 55% while retaining a
  usable map. A separate 320 px density lab compares ledger, circuit-header, and
  progressive-focus refinements without rewriting the selected Compact Agenda.
- **Repository ownership cleanup**: UX Lab HTML, source, feedback middleware,
  and build configuration now live under `frontend/labs/`; production
  `frontend/src/` excludes experiments. The canonical local SPA startup also
  serves the isolated Labs catalog on port 5175. Platform-neutral occurrence and latest-
  request helpers live in `packages/tripplanner-client` instead of `mobile/`.
  Generated test-home state, orphaned root npm metadata, dead Chainlit-era
  scripts, and the obsolete top-level architecture folder are removed.
- **Categorized documentation**: canonical product and engineering truth remains
  prominent at `docs/`, while supporting material is grouped under
  `development/`, `operations/`, `mobile/`, `roadmap/`, `feature-briefs/`,
  `ux-experiments/`, and `archive/`. `docs/README.md` is the navigation owner.
- **Compact itinerary brief + agenda (Session 86)**: the owner-selected Compact
  Brief C and Compact Agenda B now drive production itinerary days. Day briefs
  exclude hotel anchors from planned-stop counts, label the end-to-end timed span
  as the schedule, show confirmed and remaining booking readiness, and label
  guidance Travel rhythm. Dense left-anchored rows expose Depart/Return or
  Arrive/Stay semantics, travel legs, and explicit Confirmed/Needs booking
  actions while preserving exact occurrence behavior.
- **Complete-by-default new trips (Session 85)**: after the immediate first cut,
  new-trip research must be persisted in a second enriched full-plan update with
  the strongest concrete hotel and sensible daily defaults. One bounded
  correction handles remaining hotel, meal, or empty-day gaps; the opening chat
  asks only for origin, destination, and rough timing.
- **Enforced first itinerary persistence (Session 84)**: production telemetry
  exposed a planning turn that created and researched London but skipped
  `update_trip_plan`. The graph now forces the initial structured itinerary
  after same-turn creation, and SSE tool timing no longer overwrites request
  timing before terminal telemetry and the pane-refresh `done` event.
- **Google environment isolation (Session 83)**: local, canary, and production
  now use separate Google Cloud projects, OAuth Web clients, and restricted
  browser/server Maps keys. Hosted deployments require ignored `.env.canary`
  or `.env.prod` files and cannot fall back to local `.env`; the projects share
  only the billing account.
- **Documentation navigation + future backlog**: `docs/README.md` classifies
  canonical product truth, planning inputs, runbooks, and historical owner
  artifacts without destabilizing established paths. The consolidated candidate
  backlog lives in `docs/roadmap/FUTURE_FEATURES.md`; Live Trip Mode is the lead
  product increment, and every candidate still requires owner selection plus a
  focused feature brief.
- **Performance and cost baseline (engineering improvement 6)**: a hermetic
  runner exercises real FastAPI routing, identity, worker-thread delegation,
  and workspace admission for three trip reads plus one mutation. It reports
  p50/p95/error evidence, rejects scenario p95 above a conservative 750 ms,
  and proves zero LLM calls/cost while stubbing only storage/view computation.
  `docs/operations/performance-cost.md` separates this regression tripwire from production
  chat/tool telemetry, Cosmos RU/throttling analysis, and Azure/provider billing.
- **Backup and recovery drill (engineering improvement 5)**: the Cosmos data
  utility can export all six application containers into a credential-free
  checksummed artifact, validate it offline, and restore it exactly into an
  empty isolated recovery database. Drill mode rejects canary/production,
  same-coordinate, nonempty, missing-container, and partial-scope targets;
  `docs/operations/backup-recovery.md` defines evidence, initial RPO/RTO objectives, and
  the explicit approval boundary for any real production recovery.
- **External side-effect idempotency (engineering improvement 4)**: trip email
  export now carries a stable client request ID through a bounded principal
  operation ledger. ACS receives a deterministic provider `operation_id`,
  completed retries replay without sending, and key reuse with changed content
  is rejected. Ambiguous ACS delivery never falls through to SMTP; SMTP claims
  are at-most-once and uncertain outcomes are surfaced rather than duplicated.
- **Live concurrency integration coverage (engineering improvement 3)**:
  authenticated overlapping FastAPI requests now verify the production
  admission singleton end to end. A blocked model turn rejects a second chat
  with 429 and a workspace mutation with 409; after the first response releases
  its permit, both paths recover. Existing lower-level tests continue to cover
  local mutation serialization and Cosmos semantic conflict replay.
- **Production observability + measurable chat SLOs (engineering improvement 2)**:
  every JSON and SSE chat attempt emits one PII-safe terminal `chat_operation`
  event with outcome, transport, and end-to-end duration, including admission,
  replay, cap, model, and persistence paths. `docs/operations/operations-slos.md` defines
  the initial accepted-chat success and p95 latency objectives, honest
  low-volume interpretation, release checks, tool diagnostics, and copy-paste
  Log Analytics queries. Existing Container Apps stdout routing remains the
  single telemetry path; no duplicate Application Insights stack was added.
- **Production custom domain (Session 82)**: `aitripplanner.co` and
  `www.aitripplanner.co` serve the production Container App through Azure-managed
  TLS. Namecheap owns authoritative DNS; Bicep owns the existing managed
  certificates and hostname bindings, and production OAuth callbacks use
  `https://aitripplanner.co/api`. The generated Azure hostname remains available
  for rollback access.
- **V2 baseline + feature-intake workflow (Session 81)**: current capabilities,
  truthful booking boundaries, explicit gaps, proposed public-MVP roadmap, and
  the shared quality bar now live in `docs/REQUIREMENTS_V2.md`. New coherent
  outcomes should start from `docs/feature-briefs/FEATURE_BRIEF_TEMPLATE.md`;
  the owner edits `NEXT_INCREMENT.md`, and the agent normalizes it into
  acceptance criteria before implementation. Roadmap entries are not automatic
  approval.
- **Conflict-safe preferences + chat persistence (Session 80, milestone D)**:
  Cosmos conditional create/replace/delete now backs replayable semantic
  preference mutations and exact-turn chat appends. Sparse web/native writes and
  explicit-field ownership preserve unrelated or intentionally default settings;
  guest adoption fills missing fields and unions additive lists. Chat request IDs
  survive retries and first-trip migration, completed results replay before usage
  admission through a bounded principal operation index, interrupted rows are
  replaced on retry, and retained general chat is reconciled with version-aware
  source cleanup. Guest adoption merges all transcript/replay metadata. Replay,
  model turns, direct active-trip writes, lifecycle changes, and privacy deletion
  share a retryable workspace exclusion. Local writes retain same-process
  serialization plus atomic file replacement.
- **Native occurrence + refresh correctness (Session 80, milestone C)**: Plan
  converts rendered stop indexes to the backend's one-based occurrence contract,
  so repeated-place actions reach the exact row. Native refreshes share one
  abortable generation across Trip, Itinerary, Map, saved trips, and chat;
  superseded results cannot overwrite newer state, while every successful chat
  or mutation still refreshes all dependent surfaces.
- **Single guarded deployment path (Session 80, milestone B)**: the manual
  GitHub Actions workflow only builds and pushes SHA/`latest` images. It has no
  Azure login or deployment authority; canary and production releases remain
  exclusively owned by the guarded PowerShell scripts.
- **Hosted identity + chat abuse boundary (Session 80, milestone A)**: every
  user-data API derives its principal from a signed Google cookie, native bearer,
  or server-signed UUID guest capability in hosted environments; raw account ids
  are not authoritative. Guest migration proves both the account and source
  guest sessions. Chat input, per-user/IP request rate, and per-user/global
  concurrency are bounded before model execution, and usage caps follow the
  resolved principal.
- **Reproducible setup + immutable release flow (Session 79)**: one Windows
  setup command installs/verifies required tooling, restores locked Python/web
  dependencies, and preserves secrets. Canary's one-click deployment now uses
  the Git SHA it builds. The release runbook documents artifact ownership,
  staged production approval, infrastructure ownership, smoke, bake, monitoring,
  and rollback. Read-only hosted smoke additionally validates SPA assets,
  critical OpenAPI routes, and major workspace read contracts.
- **Hosted post-deployment smoke gates (Session 78)**: canary and production
  deploys now run a retry-tolerant read-only public-HTTP suite covering the SPA,
  health, environment-owned Google OAuth, Maps, anonymous auth, and isolated
  Cosmos reads. Canary adds an explicit deep Azure OpenAI check before promotion;
  deep production smoke requires separate write acknowledgement. Promotion uses
  the exact canary-tested image, manual critical-flow validation, risk-based bake,
  explicit owner approval, production smoke, monitoring, and rollback evidence.
- **Android behavioral parity repair (Session 77)**: native booking controls
  are independent from stop navigation, booking and place mutations refresh
  every dependent trip surface, streamed Assistant drafts have stable ownership,
  and Details can move an exact occurrence to another authoritative day.
- **Immediate new-trip pane population (Session 76)**: completed planning turns
  now advance the shared trip revision while refreshing Details, so Itinerary
  and Map fetch the newly persisted plan concurrently instead of waiting for a
  later action. The Pune/Khandala case exposed the missed invalidation.
- **Itinerary day-summary focus parity (Session 75)**: itinerary day-summary
  clicks and Map day chips now use one App-owned aggregate handler that clears
  exact focus, fits the full day circuit, and aligns the summary at the top of
  the Itinerary pane.
- **All-days map summary navigation (Session 74)**: Map All days clears exact
  place and single-day circuit focus, displays every circuit, and scrolls the
  Itinerary pane to its trip-level summary on desktop and responsive layouts.
- **Android account/data parity (Session 73)**: the Expo app now uses native
  browser Google OAuth to adopt the same `google-<sub>` identity as web, exposes
  Account sign-in/out, refresh, preferences, and API diagnostics, tolerates
  partial refresh failures and CRLF/buffered SSE, and shows retryable Assistant
  errors. Production still needs an explicitly approved deployment before its
  native OAuth endpoints can be exercised against existing production data.
- **Map day-to-summary navigation (Session 72)**: selecting a Map day keeps
  aggregate circuit focus and scrolls Itinerary to the start of that day's
  title, metrics, and summary instead of centering the full stop list.
- **Reliable persisted Cosmos restart (Session 71)**: local startup detects the
  vNext emulator's stale PostgreSQL PID/Unix-socket locks after abrupt Docker
  stops, removes them only when no server process exists, and restarts once.
  The named data volume is never reset; abrupt-stop recovery retains trip data.
- **Chronological itinerary circuits (Session 70)**: model-authored duplicate or
  backwards visit times are rejected before persistence. Attraction reflow now
  places fully timed meals/visits chronologically and retimes collisions while
  preserving geographic order for mixed untimed data. Map routes sort by
  authoritative occurrence stop when provider-expanded names do not directly
  match itinerary text. The active/saved Goa plan was repaired across all days.
- **Cross-surface selection consistency (Session 69)**: exact-place selection
  clears stale jump highlights, concern text no longer tints whole stop cards,
  and Map day chips use the same aggregate circuit action as itinerary day
  headers on desktop and mobile. Reusable lessons now live in the separate
  `docs/ENGINEERING_LEARNINGS.md`; the owner's `learning.txt` is untouched.
- **Clean local SPA restart (Session 68)**: `scripts/dev/dev-spa.ps1` force-clears
  stale process trees from enabled API, SPA, and Labs ports before startup and
  verifies each port is released. Backend-only runs leave frontend ports untouched.
- **Immediate mutually exclusive map focus (Session 67)**: exact-stop clicks
  clear stale aggregate circuit state, while day-header clicks clear exact
  focus. MapPanel also cancels queued circuit work before pin focus. Loaded
  Details items reorder immediately instead of waiting for Places enrichment;
  marker numbering follows authoritative itinerary occurrences rather than
  route pin order, and provider-expanded place names still match. Live rapid-
  click checks switch map number/day/Details within one paint.
- **Aggregate circuit focus + complete days (Session 66)**: itinerary day-header
  clicks clear stale exact-stop focus before fitting the full map circuit.
  `update_trip_plan` now flags ordinary hotel-only days while exempting genuine
  flight/transport travel days. The local five-day Goa trip was restored from
  its persisted transcript with populated, closed hotel circuits on every day.
- **Automatic local Docker startup (Session 65)**: the default local
  `scripts/dev/dev-spa.ps1` path launches an installed Docker Desktop when its daemon
  is stopped, waits up to two minutes, then starts the Cosmos Emulator. Azure,
  canary-data, and frontend-only runs do not launch Docker; unhealthy persisted
  emulator data is reported but never reset automatically.
- **Map placement + circuit-level focus (Session 64)**: temporary Google map
  place tiles expose Best day / exact-day selection beside Add to trip. Clicking
  an itinerary day header now fits the complete day circuit instead of routing
  through one representative place; desktop and mobile share a repeatable
  circuit-focus token. Exact-place clicks intentionally retain zoom 15 for now,
  with the usage decision recorded in `docs/roadmap/DEFERRED_DECISIONS.md`.
- **Exact map focus regression repair (Session 63)**: changing itinerary
  selection updates existing same-day marker icons immediately, restores the
  previous marker, and leaves exactly one current map number. Circuit/hotel
  markers remain 34x44 with their normal day color and white border; focus only
  inverts the center/label and raises stacking. Focus-driven redraws are one-shot,
  so callback rerenders and manual day filtering cannot undo or hijack zoom 15.
- **Mutation impact review + stronger focus (Session 62)**: direct add/move/
  remove/stay responses report the final authoritative day after reflow. A fast
  deterministic impact gate stays quiet for routine edits and offers Review
  with planner / Keep as is for crowded, travel-heavy, empty, or meal-incomplete
  days. Review opens a transcript-safe proposal-only Assistant turn that cannot
  mutate before explicit approval: graph binding/execution is read-only and API
  fallback persistence/learning is disabled. Focused map markers use elevated
  stacking and inverted number contrast.
- **Aggregate day focus + responsive chat (Session 61)**: the whole itinerary
  day header focuses its first non-stay mapped place across itinerary, Map, and
  Details. Global mutation status lives only in the command bar. Chat emits and
  renders thinking/tool/review/save phases with elapsed time, anti-buffered SSE,
  and animation-frame token paints. The measured model decision remains GPT-4.1.
- **Exact stop-to-circuit focus (Session 60)**: clicking a mapped itinerary
  place fills only that exact day/stop `H` or number, highlights the matching
  fixed-size map number, and reapplies the day filter on repeated clicks. Repeated
  hotel scrolling uses occurrence identity instead of the first name match.
- **Occurrence-safe map inspection (Session 59)**: itinerary-to-map focus keeps
  the exact day for repeated places, Google-canonical punctuation still resolves
  named itinerary pins such as Britto's, and native/autocomplete Google POIs
  become temporary real-coordinate map tiles plus contextual Details before any
  explicit Add stop mutation.
- **Itinerary-owned snapshot + contextual Details (Session 58)**: one shared
  `TripSnapshot` at the top of web itinerary owns dates, travelers, lifecycle,
  authoritative counts, booking progress, cost/budget, fit, and constraints on
  desktop and mobile. The top bar is command/status only. Whole-trip Details is
  a white destination guide plus dense place rows; focused Details retains the
  rich place inspector. Duplicate attraction and embedded-map surfaces are gone.
- **Centralized trip actions + authoritative counts (Session 57)**: Export,
  Share, and Add to calendar live in one compact common-bar menu instead of the
  Details hero. Workspace and Details place counts include unique structured
  attractions and named meals/restaurants while excluding repeats, hotels,
  flights, and transport.
- **Per-leg route context (Session 56)**: the map view exposes estimated
  `legs[]` for each consecutive pin pair, and itinerary stops expose the same
  estimate as `travel_from_previous`. Itinerary rows show quiet distance/time
  connectors; selected-day map circuits show compact midpoint labels, while
  all-days mode remains uncluttered.
- **Matching itinerary/map sequence (Session 55)**: itinerary place rows show
  restrained day-colored markers matching the map circuit: `H` for hotel
  endpoints and `1, 2, 3...` for attractions and named restaurants. Transport
  and flight rows remain unnumbered.
- **Recoverable itinerary map pins (Session 54)**: successful Places metadata
  retains its one-week cache, while transient empty lookup results expire after
  one minute instead of hiding authoritative itinerary stops for a week. The
  local Goa Day 2 circuit now includes Fort Aguada and Britto's between its
  hotel endpoints.
- **Concrete default hotels (Session 53)**: placeholder accommodation labels
  such as `Hotel (TBD)` are filtered out of `selected_hotels` and reported as
  incomplete planning. Unless the user asks to compare first, the agent must
  search, review-verify, and persist its strongest preference-matched real
  hotel in the same turn, replacing placeholder itinerary stops.
- **Hotel-anchored daily itineraries (Session 52)**: every ordinary itinerary
  day renders and is prompted as a circuit from the applicable hotel back to
  that hotel. Explicit old-stay/new-stay transfer days retain distinct
  endpoints, and overnight flight/train/bus days are not forced back to a
  hotel. Existing structured plans are repaired at view time; synthesized and
  future agent-generated plans follow the same rule.
- **Native Android app (Session 51)**: the Expo/React Native mobile shell now
  explicitly supports Android with package `com.munishgoyal1.tripplanner`,
  Material icon mappings, Google Maps via `react-native-maps`, secure identity,
  LAN Expo Go testing on port 8082, and a maintained `docs/mobile/android-testing.md`
  runbook. Android reuses all shared client/state/backend behavior. Standalone
  EAS maps need a restricted Android Maps key before preview/Play testing.
- **Repeatable iPhone testing (Session 50)**: `docs/mobile/ios-testing.md` is the
  maintained Expo Go, EAS preview, and TestFlight runbook. Physical-device
  testing defaults to LAN port 8082 because Docker can occupy 8081; ngrok is an
  optional fallback and may be blocked by the current network. Mobile checks
  remain TypeScript, Expo lint, and Expo Doctor. Production submission still
  requires explicit owner approval.
- **Native iPhone app (Session 49)**: Expo SDK 54/React Native app under
  `mobile/` provides Trips, Plan, Apple Maps, Assistant, and occurrence-aware
  Details. `packages/tripplanner-client/` is the shared, dependency-free source
  of JSON contracts, trip/map/itinerary transport, SSE parsing, mutations, and
  workspace state for both web and native. Mobile identity is Keychain-backed;
  EAS profiles cover device, preview, and App Store builds. Submission remains
  an explicit owner approval gate.
- **Consistent place actions + Change day (Session 48)**: Details and Map use
  one shared selected-place control. Normal non-hotel places show their current
  day and can move to an authoritative itinerary day using exact source
  occurrence identity; removal remains direct. Rare repeated visits are managed
  individually or everywhere and cannot collide on one day. Hotels retain
  stay-range semantics. Validation: 518 backend tests, 39 frontend tests, and
  production build pass.
- **iOS-first mobile goal (Session 47)**: mobile is now an explicit product POC,
  beginning with an iPhone-testable React Native/Expo app and Android next. The
  mobile clients reuse the authoritative FastAPI/LangGraph backend, persistence,
  API/view contracts, and mutation semantics; native adapters own phone layout,
  navigation, maps, secure auth storage, deep links, sharing, and lifecycle.
- **Reliable switches + Details actions (Session 46)**: saved-trip switching
  aborts and invalidates older Details reads before applying the new view, so
  old places cannot return. Every visible In trip pill is actionable: direct
  removal for one occurrence, contextual choices for repeated places.
- **Occurrence-aware place mutations (Session 45)**: add/remove applies the
  authoritative focused server view across Details, Itinerary, and Map.
  Repeated places carry day/stop/time identity; row removal targets one exact
  occurrence, while Details and Map offer contextual occurrence choices plus
  Remove everywhere without relying on Assistant visibility. Validation: 515
  backend tests, 36 frontend tests, TypeScript check, and production build pass.
- **Emulator-first local persistence (Session 44)**: local SPA development now
  defaults to the Docker Cosmos Emulator. Azure `tripplanner-local` requires
  explicit `COSMOS_DEV_BACKEND=azure` or `-CosmosBackend azure`. Cosmos shared
  database throughput cannot be 200 RU/s; 400 RU/s is the minimum. The Azure
  local database remains prepared in IaC but undeployed.
- **Map-rich consistent exports (Session 43)**: preview, print, direct PDF, and
  email share the photo/map options. Enabled exports embed Google static day
  maps and include hotel, attraction, and restaurant photos plus address,
  rating, notes, time, and booking status. Direct PDF no longer drops the media
  toggles; route diagrams remain the fallback when Static Maps is unavailable.
- **Configurable local Cosmos backend, prepared only (Session 42)**:
  `COSMOS_DEV_BACKEND=azure|emulator` supports Azure `tripplanner-local` and
  the emulator while canary remains a separate override. Bicep adds
  the undeployed 400-RU/s local database, taking planned shared throughput to
  1,200 RU/s (200 above free tier). Deployment requires separate approval.
- **Authoritative Map day placement (Session 41)**: explicit Map additions move
  existing unbooked occurrences to the chosen day and bypass automatic reflow.
  Missing days and booked conflicts reject unchanged with actionable choices;
  Map retains place/day inputs for retry. Validation: 510 backend tests, 31
  frontend tests, and production build pass.
- **Reversible place changes + visible status (Session 40)**: add/remove keeps
  the changed place focused in Details and removal immediately exposes the Add
  reversal while refreshing that same focus. The top update moved left into a
  flexible two-line region with compact routine messages. Validation: 30
  frontend tests, TypeScript check, and production build pass.
- **Robust place removal (Session 39)**: successful removal responses invalidate
  older in-flight trip reads, and duplicate same-place removals coalesce.
  Details, Map, and Itinerary share the guarded mutation path and expose a
  disabled pending state; Details cards use stable place keys. Validation: 29
  frontend tests, TypeScript check, and production build pass.
- **Cold trip-pane performance (Session 38)**: simultaneous cache misses for the
  same place/top-places query are coalesced. Itinerary and map warm metadata in
  parallel without review requests, and complete structured itineraries no
  longer expand the map with unrelated destination suggestions. Sparse views
  and the trip-details gallery retain destination suggestions. Validation: 48
  focused Places/view-model tests and all 506 backend tests pass.
- **Map place discovery and exact-day additions (Session 37)**: the map loads
  the Google Places library for viewport-biased autocomplete and captures
  labeled native POI clicks as stop candidates. The stop picker targets Best day
  or an explicit itinerary day; explicit placement bypasses automatic cross-day
  reflow. Google lodging POIs become hotels, restaurant POIs become meal stops,
  and manual text entry remains available when Places suggestions are absent.
- **Persistence and async reliability (Session 36)**: local active-trip,
  history, chat, and Places-cache writes use atomic temporary-file replacement
  with bounded Windows lock retry. Same-process trip mutations serialize per
  user. Cosmos exposes opt-in versioned reads and conditional replacements while
  existing mutations retain their public shapes. Places cache state/load/write
  ordering is synchronized without locking Google HTTP. Blocking trip API work
  runs as complete worker-thread operations through `web/trip_operations.py`.
- **Cross-flow reliability cleanup (Session 35)**: automatic itinerary fallback
  invokes the LangChain tool through `.invoke`, chat-created trip switches clear
  stale place/day focus before refreshing, and failed New trip requests preserve
  the current transcript. The filename-only attachment affordance is removed
  until actual upload/content extraction exists. Canonical docs avoid volatile
  tool/test counts and align booking terminology with verified handoffs.
- **Concrete restaurant itinerary stops (Session 34)**: restaurant search is a
  completion gate, not optional enrichment. Substantial days must persist named,
  preference-matched restaurants instead of `TBD` meals. `update_trip_plan`
  reports placeholders or meal-free multi-activity days so the agent can call
  `nearby_restaurants` and resubmit; `restaurant` kinds normalize to `meal`.
- **Popover, pane maximize, and complete map circuits (Session 33)**: the account
  popover toggles from the profile control and dismisses on outside click/Escape.
  Details and Assistant now maximize/restore like Itinerary and Map while all
  panes stay mounted. Map day chips still focus the first non-hotel place. Day
  routes use every structured occurrence (including places repeated across
  days) and close each circuit from/to the selected hotel; active-day filtering
  follows route membership so referenced pins do not disappear.
  Map focus tolerates Google-canonicalized restaurant/place names, so itinerary
  restaurant clicks still open the matching map tile.
- **Portable low-cost Cosmos architecture (Session 32, repository implementation)**:
  local SPA development uses the official Dockerized Cosmos DB Emulator with
  loopback-only TLS relaxation. Hosted IaC now separates a shared lifetime
  free-tier data account (`rg-tripplanner-data`) from app environments, with
  isolated `tripplanner-canary` and `tripplanner-prod` databases at 400 RU/s
  each. Migration performs exact six-container verification; throughput and
  cleanup scripts are guarded. Live canary/prod data migration and cutover are
  complete. All three legacy accounts are deleted. Direct Azure inventory on
  2026-07-26 verified only the shared free-tier account, both 400-RU/s
  databases, and healthy canary/prod apps. Both obsolete Basic ACRs and the
  unreferenced zero-deployment Foundry account/project are also deleted; apps
  continue to use GHCR. See `.azure/deployment-plan.md`.
- **Independent right dock + common export (Session 31)**: Details and Assistant
  are mounted sibling sections with matching hide controls; hiding either leaves
  the other visible and lets it fill the dock. Map day chips now focus a primary
  day place in Details as well as scrolling the itinerary. The desktop command
  bar exposes photo/PDF/email export and shows green signed-in or gray guest
  account status. Removing the active place clears stale focus. The malformed
  route-circuit branch in `web/itinerary_export.py` is repaired and covered.
  Validation: 22 frontend tests, production build, and all 477 backend tests pass.
- **Cross-pane focus + recoverable workspace (Session 30)**: Map day chips now
  scroll the itinerary to the matching day; adding a place from Details focuses
  its updated itinerary row and map pin using the mutation response (no redundant
  TripView rebuild). Structured restaurants/meals remain map pins inside ordered
  day circuits and focus like other places. Desktop New trip, account, and
  preferences launch from the common top row; duplicate chat-header controls are
  mobile-only. Itinerary, Map, Details, and Assistant have explicit show/hide
  recovery controls while stateful panes remain mounted. Stale map/itinerary
  requests abort during rapid updates. Validation: 20 frontend tests, production
  build, and 161 focused backend tests pass; full backend baseline is 469 passing
  with the same 7 unrelated share/export failures.
- **Workspace controls + coherent itinerary mutations (Session 29)**: the
  desktop top row is now a compact command/status bar with saved-trip selection,
  New trip, Details/Assistant visibility, lifecycle, trip completeness, cost,
  loading state, and latest mutation outcome. Its dropdown has an explicit
  workspace-level stacking contract and browser regression. Hotel/place add or
  remove actions now reflow all unbooked attractions around current hotel
  anchors by proximity and balanced load; booked attractions, hotels, and
  non-place stops remain fixed. Duplicate itinerary hotels are refreshed in
  place rather than inserted again. Validation: 126 focused trip tests, 17
  frontend tests, production build, and desktop/mobile Playwright pass.
- **No-scroll spatial workspace, Layout D (Session 27)**: desktop is now a
  fixed `100dvh` planner with itinerary left, a persistent dominant map center,
  and a contextual details inspector right. Chat is a collapsible dock inside
  the inspector; map, inspector, and chat remain mounted through collapse and
  maximize transitions so map/chat state survives. Session 28 restored focused
  mouse/keyboard separators for itinerary/map, map/inspector, and details/chat;
  sizes persist locally and the inspector defaults wider at 31%. At 768-1199px
  the inspector overlays the canvas instead of squeezing it; mobile keeps chat
  plus the on-demand trip-details sheet. Only panes scroll, and itinerary place
  clicks focus both the map and contextual Details. Frontend validation: 16
  Vitest/RTL tests, production build, and Playwright desktop/mobile projects pass.
- **Frontend reliability foundation (Session 25)**: desktop and mobile trees
  are conditionally mounted so duplicate API/chat/map effects cannot run. Trip
  view requests cancel stale predecessors, map/itinerary keep prior content
  during refresh with retry states, map-local selection/day state reconciles to
  fresh data, removing a focused stop clears Details, and chat always exits busy
  state after HTTP/SSE interruption. `dev-spa.ps1` rejects occupied frontend
  ports instead of silently moving Vite to another port.
- **Frontend completion pass (Session 26)**: `workspaceState.ts` now owns trip
  identity/revision, chat revision, active place, and itinerary jump state;
  focus-only detail requests no longer reload map/itinerary/saved trips and
  reducer/App regressions lock that boundary. `TripSwitcher.tsx` and
  `ExportModal.tsx` were extracted from the oversized `TripPanel.tsx`; Lucide
  icons now cover familiar actions. Itinerary day headers show stops, planned
  duration, route metrics, and Maps handoff; booking controls have stop-specific
  accessible names. User-facing API calls reject non-2xx responses and saved
  trips expose recovery states. Frontend validation: 14 Vitest/RTL tests,
  production build, and both Playwright desktop/mobile projects pass using the
  installed stable Chrome channel.
- **Intelligent v1 itinerary + map zoom fix (Session 24)**: two canary bugs
  closed. (1) The itinerary panel no longer shows a flat "Your picks so far"
  dump when the agent forgets to persist `day_wise_itinerary` — 
  `trip_view._itinerary_from_selections` now SYNTHESIZES an intelligent
  multi-day v1: selected attractions are proximity-ordered (nearest-neighbor
  from the hotel via cached `places_cache` coords, `_haversine_km`) then split
  into contiguous, day-sized clusters across `_trip_day_count` days (never more
  days than attractions, so no empty days), hotel anchors Day 1, each day titled
  `Day N · <primary place>`. Degrades to selection order when Places isn't
  configured. New helpers `_place_coords`, `_nearest_neighbor_order`,
  `_split_contiguous`. (2) Clicking an itinerary stop now actually zooms the
  map: `MapPanel.tsx` stashes the target in `pendingFocusRef` and applies the
  `panTo`+`setZoom(15)`+`openInfo` INSIDE `draw()` (instead of `fitBounds`), so
  a lazy map mount or follow-up redraw can't undo the zoom; the focus effect is
  no longer gated on `mapRef.current` being ready. +1 test
  (`test_itinerary_synthesizes_multiple_days`) → 463 passing; tsc clean.

- **Requirements alignment + map route metrics (Session 23)**: reviewed the
  updated `docs/Requirements.docx` and closed a concrete UX/functional gap:
  day-wise circuits now surface travel distance/time/mode. `trip_view.build_map_view`
  adds `days[].route = {distance_km,duration_min,mode,distance_display,duration_display}`
  computed from ordered day pins using straight-line haversine totals plus
  conservative local-transfer heuristics (walk/local transit/car transfer) to
  avoid billed Directions API calls. `frontend/src/components/MapPanel.tsx`
  now shows an active-day summary line: `Day N route: X km · Y min · mode`
  (estimated). `frontend/src/types.ts` adds `MapDay.route`; tests updated in
  `tests/test_trip_view.py`. 408 tests passing; tsc clean.
- **Rail rework + fresh-trip fixes + 1-week cache (Session 22)**: owner disliked
  the Session-21 tabs, so `RightRail.tsx` was REWRITTEN with NO tabs — a
  persistent header (saved-trips `TripSwitcher` left + Map toggle right) over a
  stacked body: Itinerary (top, `basis-2/5`) and Photos (bottom, `flex-1`) are
  ALWAYS visible, Map is an opt-in lazy section (still bills per load).
  `TripSwitcher` is now exported from `TripPanel.tsx`; `TripPanel` gained a
  `hideSwitcher` prop to avoid duplication. `App.tsx` dropped
  `RailTab`/`activeTab`/`autoTabbed`, added `mapOpen` state, and reduced chat
  default width ~30% (`chatPct` 52→36). Bug fixes shipped alongside: (1) fresh
  chat loss — `/chat/stream`'s error path now saves the partial transcript so a
  tool side-effect can't orphan the chat, plus `POST /trip/new` →
  `trip_planner.start_new_trip()` (clears active pointer; saved trips untouched)
  and a ChatPanel "New trip" button (`api.startNewTrip`). (5) empty itinerary —
  `trip_view._itinerary_from_selections` synthesizes a "Your picks so far" day
  from selections when `day_wise_itinerary` is empty; STEP 4 prompt now insists
  the agent persist the structured itinerary via `update_trip_plan`. (4) 1-week
  persisted places cache — see `web/places_cache.py` below. +8 cache tests →
  407 passing; tsc clean.
- **Split-TTL persisted places cache (Session 22)**: `web/places_cache.py` is a
  two-layer cache (in-process dict hot L1 + durable L2). Place details, reviews,
  and `top_places` use `_META_TTL_S = 7 days`; signed photo URLs use
  `_PHOTO_TTL_S = 50 min` (Google expires them ~1h) and are re-resolved on
  demand from the long-lived `photo_refs` (URLs are NEVER persisted). Durable
  store: Cosmos `places_cache` container (partition `_shared`, one doc id
  `cache` holding all entries) when enabled, else local
  `~/.tripplanner/places_cache/cache.json`; loaded once per process, 1-week-stale
  entries dropped on load. `prefetch` batches writes (`_batched_persist`). All
  public fns take `refresh=True` to force a re-fetch + re-cache. Soft cap
  `_MAX_ENTRIES=800`. No Redis — reuses the existing Cosmos/local dual-store
  pattern (no infra to provision on a scale-to-zero free-credit deployment).
- **Structured itinerary + tabbed right rail (Session 21)**: the itinerary is
  now data, not just prose. `web/trip_view.build_itinerary(trip)` returns
  day-by-day `days[{day,date,title,summary,color,stops[...]}]` + `stats`, where
  each stop has `name/kind/time/duration_min/note/booked/selected/color`
  (`_normalize_stop`/`_infer_stop_kind` accept string OR dict stops).
  `trip_planner.set_stop_booked(day,name,booked)` persists a per-stop booked
  flag (normalizes string stops to dicts so it sticks). Endpoints:
  `GET /trip/itinerary`, `POST /trip/stop/booked` (`StopBookedRequest`). Agent
  prompt STEP 4 now asks for structured `stops` (prose still works) and to set
  `"booked": true` after `execute_bookings`. Frontend: new `ItineraryPanel.tsx`
  (clickable day timeline with a booked checkbox — optimistic toggle) and
  `RightRail.tsx` (segmented **Itinerary · Map · Photos** tabs) REPLACE the old
  standalone "Show map" 3rd column. Map mounts lazily inside the rail (Google
  Maps bills per load); itinerary + photos stay mounted. Clicking a place stop
  focuses the Photos tab; the 📍 button jumps to the Map tab (`MapPanel` got a
  `focusName` prop that reveals the pin's day + opens its info window).
  Incremental saves confirmed already working (per-turn `_save_chat` +
  `update_trip_plan→_save_active_trip` mirror under `trip_id`).
  Types: `Itinerary`/`ItineraryDay`/`ItineraryStop`; api: `fetchItinerary`,
  `setStopBooked`. +7 backend tests → 398 passing; tsc clean.
- **Persistent chat + day-clustered map (Session 20)**: the conversation +
  itinerary summary now survive a browser refresh AND follow saved-trip
  switches. Pure-Python `web/chat_store.py` persists the clean Human/AI text
  turns keyed by the active `trip_id` (Cosmos `users`/`chat_<trip_id>` or local
  `chats/<trip_id>.json`); a pre-trip conversation lives in a `_general` bucket
  and migrates into the trip's bucket on create. `trip_planner.active_trip_id()`
  exposes the active id; `api.py` replaced in-memory `_HISTORY` with
  `_load_chat()`/`_save_chat()` in `/chat` + `/chat/stream`, plus a new
  `GET /chat/history`. Frontend `fetchChatHistory()` + `ChatPanel` restore the
  transcript on mount and when a saved trip is switched (new `chatReloadToken`
  bumped only on switch so routine refreshes don't wipe the chat). Map fixes:
  selected attractions the itinerary text didn't place get a fallback day so
  they show bold numbered day-colored pins + per-day route lines; distinct
  marker styles (slate "H" hotel pins always shown, numbered day teardrops,
  quiet suggestion dots); fixed the map going blank on trip reload (container
  stays mounted, stale map ref reset on unmount).
- **Remembered saved trips (Session 19)**: trips persist across logins and are
  never lost. Every `trip_planner._save_active_trip` mirrors the plan into the
  `trips` collection keyed by a stable `trip_id = slug(destination)_<dep>_<ret>`.
  Same destination + same dates → same id → `create_trip_plan` RESUMES (keeps
  selections); different dates/duration → different id → kept as a separate,
  date-tagged trip. Non-tool helpers `list_saved_trips()` /
  `switch_active_trip(id)` / `delete_saved_trip(id)` back a self-contained
  "My trips" `TripSwitcher` dropdown in `TripPanel.tsx` (status badges, active
  highlight, per-trip delete ×; shown even on the empty canvas). Endpoints:
  `GET /trips`, `POST /trips/switch`, `POST /trips/delete` (`TripIdRequest`).
  Agent tool `resume_trip(destination|trip_id)` + prompt STEP 2 let the
  assistant offer to continue a saved plan. `execute_bookings` no longer writes
  a separate timestamped archive (history is mirrored under `trip_id`).
- **Interactive trip map panel (Session 18)**: `web/trip_view.build_map_view(trip)`
  is a pure-Python view-model returning geocoded pins (selected hotels/activities
  + destination suggestions), each tagged with its itinerary day (structured
  `stops` first, else prose `plan` match), grouped into day-colored route bands,
  plus an arrival-airport pin + map center. Served by `GET /trip/map`; the
  browser key comes from `GET /maps/config` (new `GOOGLE_MAPS_BROWSER_KEY` env
  var — a SEPARATE referrer-restricted browser key with the Maps JavaScript API
  enabled; the server-side `GOOGLE_PLACES_API_KEY` is never sent to the browser).
  `frontend/src/components/MapPanel.tsx` lazily loads the Maps JS API (only when
  the user opens the map column, to avoid billed loads), draws numbered
  day-colored pins, geodesic per-day route lines (no billed Directions API),
  day-filter chips, airport pin, and info windows. `App.tsx` has a "Show map"
  toggle mounting the map as a third desktop column on demand. `places_cache`
  now surfaces `lat`/`lng`. Trip-agent prompt STEP 4 asks for a per-day `stops`
  list (prose fallback still works). Map hides itself when the key is unset.
- **Live budget meter (Session 17)**: `web/trip_view.build_budget(trip)` is a
  pure-aggregation view-model (running spend, per-traveler split, category
  breakdown, remaining-vs-target bar) surfaced as `overview.budget` from
  `GET /trip/view` and rendered by a `BudgetMeter` card in `TripPanel.tsx`.
  `budget` + `currency` (ISO code) are now `update_trip_plan` keys the agent
  persists (prompt STEP 2 + RULE 8); `currency_symbol` maps the sticky code.
- **Phase-based tool binding (Session 17)**: `trip_agent` splits tools into
  `_CORE_TOOLS` (always bound) + `_SEARCH_TOOLS` (bound only when planning is
  active); `select_tools(messages)` is called from `graph.trip_agent` so the
  ~15 heavy search schemas aren't sent on greeting/preference turns. ToolNode
  still holds the full union (`TRIP_TOOLS`) so execution is never blocked.
- **Two run modes from one codebase:**
  - LOCAL: CLI (`cli.py`) or FastAPI (`api.py`) — persistence to `~/.tripplanner/*.json`
  - HOSTED: React SPA (`frontend/`) served by FastAPI (`api.py`) — persistence to Azure Cosmos DB.
    In production the SAME FastAPI process serves the built SPA from `frontend/dist`
    at the root origin and the API under `/api` (single origin, one container).
  - Auto-dispatch via `storage_cosmos.is_enabled()` (True when `COSMOS_ENDPOINT` env var set)
  - Per-user identity tracked via `tripplanner.user_context.get_user_id()` (ContextVar, default `"local"`)
- **Identity tracks (hosted mode)**:
  - OAuth login (Google) via standalone `web/oauth.py` → identifier `"google-<sub>"` (cross-device).
    Signed HttpOnly `mg_session` cookie (HMAC-SHA256 with `WEB_SESSION_SECRET`,
    falls back to `CHAINLIT_AUTH_SECRET` for back-compat).
  - Guest fallback → persistent `web-<uuid>` id (localStorage, same browser).
  - Setup walkthrough: `docs/development/setup-oauth.md`. All OAuth env vars are optional;
    leaving them unset keeps the app login-less.
- Single trip planner agent with 34 tools across 10 families:
  - Preferences & continuous learning (10):
    - get_travel_preferences, save_travel_preferences, record_past_trip,
      record_trip_postmortem, remember_about_user
    - update_user_profile, add_family_member, add_user_interest, add_user_dislike,
      record_trip_mention (Cosmos-aware)
  - Duffel flight search (1): search_flights_duffel — PREFERRED primary flight provider
  - Amadeus search (4): flights (fallback), hotels, activities, POI
    (Amadeus self-service is being decommissioned 2026-07-17; kept for hotels & activities)
  - Google Places ratings (4): search_places_with_reviews, get_place_reviews, nearby_restaurants,
    check_place_hours (regular+current opening hours, catches Tuesday-Louvre mistakes)
  - Routing & travel time (2): compute_route, optimize_day_route (Google Routes API v2,
    reuses GOOGLE_PLACES_API_KEY; enable "Routes API" on the same Cloud project)
  - Weather (1): get_weather_forecast (Open-Meteo, no API key; forecast within
    16-day horizon, seasonal archive proxy beyond)
  - Visa & entry (1): check_visa_requirements (Tavily-backed, biases results
    toward .gov / embassy / IATA TravelCentre; always includes disclaimer)
  - Local events (1): find_local_events (Tavily news topic; flags festivals,
    parades, public holidays overlapping the trip dates)
  - Memory recall (1): recall_relevant_memory (BM25-lite over learned_notes,
    past_trip_mentions, past_trips, family_members, interests, about_me; no
    API call, instant)
  - Tavily web search (1): web_search
  - Trip plan lifecycle (7): create/get/update/finalize/execute/list_past_trips
    + resume_trip (resume a saved trip by destination or trip_id) (Cosmos-aware)
- Trip plan lifecycle: draft → finalized → booked (with execute command)
- Persistent user preferences — expanded continuous-learning schema (Session 10):
  - `profile` {display_name, home_city, home_country, age_band, occupation}
  - `family_members` [{relationship, name, age, dietary, mobility, interests, notes}]
  - `interests`, `dislikes` — string lists, deduped case-insensitively
  - `past_trip_mentions` [{destination, when, with_whom, sentiment, notes, source, at}]
    — trips user *casually mentioned* (vs. `past_trips` = agent-planned + rated)
  - `learned_notes` — free-form observations the agent extracts passively
    (each `{note, source: stated|inferred, at}`)
  - Legacy keys preserved: `family`, `trip_style`, `budget_level`,
    `hotel_preferences`, `transport_preferences`, `food_preferences`,
    `accessibility_needs`, `past_trips`
  - Local: `~/.tripplanner/user_preferences.json`
  - Hosted: Cosmos DB `users` container, doc id `preferences`, PK `/user_id`
- Trip state:
  - Local: `~/.tripplanner/active_trip.json`, archived in `~/.tripplanner/trips/`
  - Hosted: Cosmos DB `users`/`active_trip` (active) + `trips` container (archive)
- Azure infra (Bicep): Container Apps (scale-to-zero) + one shared Cosmos DB
  lifetime free-tier account with canary/prod databases at 400 RU/s each + Log
  Analytics. Local uses the Cosmos Emulator. Image hosted on public GHCR.
  Target footprint ≤ ₹10K/mo free credit.
- 407 tests all passing (Session 22: +8 for split-TTL persisted places cache
  (`web/places_cache.py` — meta 1-week / photo-URL 50-min, durable L2, refresh);
  Session 20: +9 for persistent per-trip chat
  (`web/chat_store.py`) + map fallback-day clustering; Session 19: +15 for remembered saved trips
  — trip_id stability, mirror-on-create, start-new-keeps-previous,
  same-dates-resume vs different-duration-separate, switch/delete,
  resume_trip variants; Session 16.21: +15 for
  `usage.py` per-user monthly LLM cost cap — a LangChain
  `BaseCallbackHandler` attached to the Azure chat model in `graph.py`
  reads `LLMResult.llm_output['token_usage']` on every completion and
  feeds it to `usage.record_usage(user_id, model, prompt_tokens,
  completion_tokens)`; cost is computed against a small prefix-keyed
  rate table (gpt-5/4.1/4.1-mini/4o/4o-mini/4/3.5) and added to a
  monthly bucket keyed `(user_id, YYYYMM)`; persisted to Cosmos doc id
  `usage_<YYYYMM>` in the `users` container when enabled, else to
  `~/.tripplanner/usage/<user_id>_<YYYYMM>.json`; both `/chat` and
  `/chat/stream` run `is_over_cap(user_id)` first and short-circuit
  with a polite refusal (agent name `"cap"`) when the bucket meets or
  exceeds `MONTHLY_LLM_COST_CAP_USD` (env, default $20; `<= 0`
  disables); `GET /usage?user_id=<id>` exposes the live bucket and
  cap; Session 16.20: +16 for
  `hallucination_critic.py` deterministic fact-check on the agent's final
  reply — scans for cited prices (currency-symbol or ISO code),
  clock times (12h/24h), and URLs, then verifies each appears verbatim in
  some tool message from the same turn. Price matching is format-aware
  (Session 17.1): a price is grounded if it matches verbatim OR by numeric
  magnitude (tool `INR 19500` == reply `₹19,500`), and `am/pm` spacing is
  normalised. Unverified claims are logged as an `app_event`
  (`hallucination_critic`, `claims=[...]`) — NOT shown to the user (the
  old user-facing "Heads up" footer was removed Session 17.1 because RULE 8
  currency conversion made it fire on nearly every price); wired
  into both `/chat` and `/chat/stream` (streaming endpoint captures tool
  outputs via `on_tool_end` events as a synthetic `ToolMessage` list);
  Session 16.19: +7 for per-tool latency + error
  metrics in `observability.py` (`record_tool_call`,
  `tool_metrics_snapshot`, `reset_tool_metrics`) and a `GET /metrics/tools`
  endpoint; cache wrapper in `tools_cache.py` now reports each invocation
  (status=ok|error, cache_hit, ms, error class) so a tool served from cache
  shows up with cache_hit=True and ~0ms; recent latency window per tool is
  50 samples used for p50/p95; each call also emits a structured `tool_call`
  app event for Log Analytics; Session 16.18: +10 for `tools_cache.py` read-through
  cache wrapping every read-only tool — keyed by `(user_id, tool_name,
  canonical_args)`, Cosmos `tool_cache` container when enabled else
  in-process LRU(256) with TTL (30 min default); stateful tools like
  `update_trip_plan`/`finalize_trip`/`save_travel_preferences` bypass the
  cache; wired into `graph.py` via `wrap_tools_with_cache(TRIP_TOOLS)` that
  returns new `StructuredTool` copies so the originals are unaffected;
  Session 16.15: +10 for `web/share.py` read-only
  share-link tokens (HMAC over `(user_id, created_at)`, idempotent, sanitized
  public view) surfaced via `POST /trip/share` + `GET /trip/shared/{token}`
  and a "Share" pill next to "Add to calendar" in `TripPanel.tsx`;
  Session 16.14: +6 for `web/ics_export.py`
  RFC 5545 VCALENDAR builder surfaced via `GET /trip/export.ics` and the
  "Add to calendar" link in `TripPanel.tsx`; Session 16.13: +6 for `build_map_url` Google Maps Embed
  URL builder surfaced via `destination_overview.map_url` and rendered as an
  iframe in `DestinationOverview.tsx`; Session 16.12: +9 for `trip_diff` structural plan-diff
  surfaced from `update_trip_plan`; Session 16.11: +10 for `finalize_critic` deterministic
  self-correction rules surfaced as a "Heads up" block in `finalize_trip`;
  Session 16.10: +3 for explicit `parallel_tool_calls=True`
  guard + concurrent ToolNode execution check; Session 16.9: +5 for `_summarize_tool_input` SSE
  tool-arg preview helper used by `/chat/stream`; Session 16.8: +2 for `record_trip_postmortem`
  structured post-mortem; Session 16.7: +4 for `trip_view.family_pills`
  family-fit pills; Session 16.6: +8 for `tools/memory_recall.py` BM25-lite
  recall; Session 16.5: +5 for `tools/events.py` local events;
  Session 16.4: +6 for `tools/visa.py` visa & entry
  rules; Session 16.3: +10 for `tools/weather.py` Open-Meteo wrapper;
  Session 16.2: +11 for `tools/place_hours.py` opening-hours check;
  Session 16.1: +12 for `tools/routing.py` Google Routes v2 wrapper;
  Session 13: 5 tests for the decoupled `trip_view` view-model; Session 10
  added 25 continuous-learning tests).
- **Currency rule (Session 12)**: trip agent prompt CRITICAL RULE 8 picks ONE
  sticky display currency per plan. Domestic trips use the user's HOME currency
  (from `profile.home_country`; default INR ₹). International trips may use USD
  (or the destination's local currency) where it makes most sense, optionally
  showing the home-currency equivalent in parentheses. Converts source
  currencies (e.g. Duffel USD) to the chosen one. Fixes prices flipping
  INR↔USD between sessions.
- **Right-rail trip panel (hosted mode)**: rendered by the React SPA
  (`frontend/src/components/TripPanel.tsx` + `DestinationOverview.tsx`),
  backed server-side by `web/places_cache.py` (Google Places photos/reviews,
  parallel prefetch; 1-week details TTL + 50-min photo-URL TTL, persisted).
  The frontend additionally caches the
  `/destination/overview` response in a module-level `Map` (30-min TTL)
  and keeps the previous destination's card visible (dimmed) while a new one
  loads — switching Dubai → Paris no longer blanks the panel. When no
  hotels/activities are selected yet but a destination is known, the panel
  falls back to the destination's top hotels & attractions
  (`places_cache.top_places`) so it fills during browsing; selected items are
  merged with suggestions and marked "In trip" (Airbnb/TripAdvisor style) so
  picking one no longer hides the rest. The overview header also surfaces
  **family-fit pills** (Kid-friendly with ages, Senior-friendly with mobility
  note, Pet-friendly, Vegetarian/Jain/etc., Wheelchair access) derived
  server-side from `family_members` + `food_preferences.dietary` +
  `accessibility_needs` via `trip_view.family_pills(prefs)`.
- **UI polish (Airbnb/TripAdvisor-style)**: Tailwind theme uses coral `brand`
  (#e11d48) + teal `accent`, Inter for UI + Fraunces for display headings
  (loaded via `<link>` in `frontend/index.html`), `rounded-3xl` cards with
  `shadow-card`/`shadow-pop`, sticky composer/toolbar with backdrop blur,
  rating pills, "In trip" ribbons, and a magazine-style hero summary on the
  trip panel. Reusable component classes (`.card`, `.btn-primary`,
  `.btn-ghost`, `.pill`, `.chip`, `.display`) live in
  `frontend/src/index.css`. On mobile (`<768px`) the right-rail trip panel
  becomes a fixed bottom-sheet (88vh, slide-up, scrim) toggled by a floating
  "Trip details" pill in the bottom-right; the sheet auto-closes when the
  viewport crosses back to desktop and on Escape.
- **Decoupled trip view-model (frontend-agnostic)**: data shaping lives in
  pure-Python `web/trip_view.py` (ZERO UI imports) — `build_view(trip, focus)
  -> dict` is the single JSON view-model contract, served by the `GET /trip/view`
  FastAPI endpoint and consumed by the React `TripPanel.tsx`. `build_view` merges
  selected items with deduped destination top-places so the panel never collapses.
- Azure OpenAI **API version must be `2024-10-21`** (data-plane GA); `2024-11-20`
  is a model snapshot date and produces 404 NotFoundError. Bicepparam default,
  GitHub secret, and live container env all aligned on `2024-10-21`.
- New API keys gracefully degrade — tools return "not configured" when env var missing.
- Removed (Session 1): todo, comms, calendar, budget agents. Google OAuth / Twilio integrations.

## Files to Read for Context
- `PRD/REQUIREMENTS Auto Log.txt` — full history of requirements and decisions
- `README.md` — architecture (local + hosted), setup, project structure
- `infra/README.md` — Azure deploy walkthrough (GHCR + `az deployment group create`)
- `src/tripplanner/graph.py` — single-agent tool loop (unchanged for hosted mode)
- `src/tripplanner/chat_interactions.py` — validated structured Assistant input contract
- `src/tripplanner/agents/trip_agent.py` — trip agent with 32 tools (incl. EXTRACTION CHECKLIST prompt)
- `src/tripplanner/storage_cosmos.py` — optional Cosmos backend (lazy import)
- `src/tripplanner/user_context.py` — per-request user_id ContextVar
- `src/tripplanner/web/oauth.py` — standalone Google OAuth (HMAC `mg_session` cookie)
- `src/tripplanner/web/trip_view.py` — pure-Python frontend-agnostic view-model
  (`build_view`, `build_destination_overview` w/ Tavily news)
- `src/tripplanner/web/places_cache.py` — Google Places cache (parallel prefetch + TTL)
- `src/tripplanner/tools/preferences_merge.py` — shared About-me extract+additive-merge
  (no UI imports; used by `api.py`)
- `frontend/` — React 19 + Vite + TS SPA (the UI), served by FastAPI in prod;
  `App.tsx`, `ChatPanel.tsx`, `DestinationOverview.tsx` (reviews/photos/attractions/news),
  `SettingsModal.tsx` (About-me textbox + extractor), `TripPanel.tsx` (focus nav + item picker)
- `src/tripplanner/tools/` — Duffel (primary flights), Amadeus, Google Places, Tavily, plan state, preferences
- `infra/data-stack.bicep` + `infra/data.bicep` — shared free-tier Cosmos data plane
- `infra/main.bicep` + environment `.bicepparam` files — ACA + existing Cosmos binding

