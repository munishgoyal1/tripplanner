# Copilot Instructions — multiagent

> **Read [docs/CODEMAP.md](../docs/CODEMAP.md) (where) and
> [docs/PRODUCT.md](../docs/PRODUCT.md) (what/why + taste) FIRST.**
> They are the canonical, committed sources of truth and are kept up to date
> with the code. Use them instead of grepping the repo to "rediscover"
> structure or owner intent on every task.

## Agent efficiency rules (avoid wasting the user's time)
- Read big chunks (50–200 lines) and read multiple files in parallel.
  Do NOT dribble 5-line reads.
- Batch independent tool calls into ONE turn. Only chain when an output is
  needed for the next input.
- Trust this file + `docs/CODEMAP.md` + `docs/PRODUCT.md` +
  `/memories/repo/multiagent.md`. Skip re-exploration on every task.
- Run validation (tsc, pytest, build) ONCE at the end of a milestone, not
  after every micro-edit (exception: when a mid-edit failure is suspected).
- One milestone = one commit + push. Per owner rule, never leave unpushed work.
- Do not add docstrings/type-hints/comments to code you didn't touch.

## Memory maintenance (KEEP CONTEXT FRESH — do this every session)
Whenever the owner teaches a new preference, taste, or requirement, update
the right place IN THE SAME TURN so future sessions don't relearn it:

| What changed                                | Update                                |
|---------------------------------------------|---------------------------------------|
| Cross-project habit (terse, no servers, …)  | `/memories/preferences.md`            |
| Repo-only gotcha / landmine                 | `/memories/repo/multiagent.md`        |
| Vision / scope / taste / design language    | `docs/PRODUCT.md` (commit)            |
| File layout / commands / contracts          | `docs/CODEMAP.md` (commit)            |
| New requirement / decision (with date)      | `REQUIREMENTS.txt` (commit)           |
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
- Tavily: free 1000 searches/month

## Codebase Conventions
- Python 3.11+, typed with `from __future__ import annotations`
- Single agent in `src/multiagent/agents/trip_agent.py`
- Tools as `@tool`-decorated functions (langchain_core.tools)
- Agent exports: `build_trip_system_prompt()` factory (injects today's date) and `TRIP_TOOLS` (list). `TRIP_SYSTEM_PROMPT` snapshot kept for back-compat.
- API clients and search tools go in `src/multiagent/tools/`
- Config via Pydantic `Settings` from `.env` (see `config.py`)
- Graph in `graph.py` — single-agent tool-calling loop
- Tests in `tests/` — use pytest, no mocks for pure logic tests
- Line length: 100 (ruff)
- No unnecessary comments — only non-obvious choices

## Key Architecture
- `graph.py`: LangGraph StateGraph with agent → tools → agent loop → END
- No router — single trip agent handles everything
- Agent: system prompt + 14 tools, bound via `bind_tools()`
- Two entrypoints: CLI (`cli.py`) and FastAPI (`api.py`)

## Working Preferences (from user)
- Always commit AND push after every change
- Keep it simple, modular — no over-engineering
- No major functional changes without user consent
- Update REQUIREMENTS.txt when new requirements come in
- Update README.md when architecture changes
- This file must always reflect current state

## Current State (last updated 2026-06-11)
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
  - LOCAL: CLI (`cli.py`) or FastAPI (`api.py`) — persistence to `~/.multiagent/*.json`
  - HOSTED: React SPA (`frontend/`) served by FastAPI (`api.py`) — persistence to Azure Cosmos DB.
    In production the SAME FastAPI process serves the built SPA from `frontend/dist`
    at the root origin and the API under `/api` (single origin, one container).
  - Auto-dispatch via `storage_cosmos.is_enabled()` (True when `COSMOS_ENDPOINT` env var set)
  - Per-user identity tracked via `multiagent.user_context.get_user_id()` (ContextVar, default `"local"`)
- **Identity tracks (hosted mode)**:
  - OAuth login (Google) via standalone `web/oauth.py` → identifier `"google-<sub>"` (cross-device).
    Signed HttpOnly `mg_session` cookie (HMAC-SHA256 with `WEB_SESSION_SECRET`,
    falls back to `CHAINLIT_AUTH_SECRET` for back-compat).
  - Guest fallback → persistent `web-<uuid>` id (localStorage, same browser).
  - Setup walkthrough: `docs/setup-oauth.md`. All OAuth env vars are optional;
    leaving them unset keeps the app login-less.
- Single trip planner agent with 33 tools across 10 families:
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
  - Trip plan lifecycle (6): create/get/update/finalize/execute/list_past_trips (Cosmos-aware)
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
  - Local: `~/.multiagent/user_preferences.json`
  - Hosted: Cosmos DB `users` container, doc id `preferences`, PK `/user_id`
- Trip state:
  - Local: `~/.multiagent/active_trip.json`, archived in `~/.multiagent/trips/`
  - Hosted: Cosmos DB `users`/`active_trip` (active) + `trips` container (archive)
- Azure infra (Bicep): Container Apps (scale-to-zero) + Cosmos DB (Free Tier 1000 RU/s) +
  Log Analytics. Image hosted on GHCR public. Target footprint ≤ ₹10K/mo free credit.
- 322 tests all passing (Session 16.21: +15 for
  `usage.py` per-user monthly LLM cost cap — a LangChain
  `BaseCallbackHandler` attached to the Azure chat model in `graph.py`
  reads `LLMResult.llm_output['token_usage']` on every completion and
  feeds it to `usage.record_usage(user_id, model, prompt_tokens,
  completion_tokens)`; cost is computed against a small prefix-keyed
  rate table (gpt-5/4.1/4.1-mini/4o/4o-mini/4/3.5) and added to a
  monthly bucket keyed `(user_id, YYYYMM)`; persisted to Cosmos doc id
  `usage_<YYYYMM>` in the `users` container when enabled, else to
  `~/.multiagent/usage/<user_id>_<YYYYMM>.json`; both `/chat` and
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
  parallel prefetch + 30-min TTL). The frontend additionally caches the
  `/destination/overview` response in a module-level `Map` (same 30-min TTL)
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
- `REQUIREMENTS.txt` — full history of requirements and decisions (Session 6 = hosted mode)
- `README.md` — architecture (local + hosted), setup, project structure
- `infra/README.md` — Azure deploy walkthrough (GHCR + `az deployment group create`)
- `src/multiagent/graph.py` — single-agent tool loop (unchanged for hosted mode)
- `src/multiagent/agents/trip_agent.py` — trip agent with 32 tools (incl. EXTRACTION CHECKLIST prompt)
- `src/multiagent/storage_cosmos.py` — optional Cosmos backend (lazy import)
- `src/multiagent/user_context.py` — per-request user_id ContextVar
- `src/multiagent/web/oauth.py` — standalone Google OAuth (HMAC `mg_session` cookie)
- `src/multiagent/web/trip_view.py` — pure-Python frontend-agnostic view-model
  (`build_view`, `build_destination_overview` w/ Tavily news)
- `src/multiagent/web/places_cache.py` — Google Places cache (parallel prefetch + TTL)
- `src/multiagent/tools/preferences_merge.py` — shared About-me extract+additive-merge
  (no UI imports; used by `api.py`)
- `frontend/` — React 19 + Vite + TS SPA (the UI), served by FastAPI in prod;
  `App.tsx`, `ChatPanel.tsx`, `DestinationOverview.tsx` (reviews/photos/attractions/news),
  `SettingsModal.tsx` (About-me textbox + extractor), `TripPanel.tsx` (focus nav + item picker)
- `src/multiagent/tools/` — Duffel (primary flights), Amadeus, Google Places, Tavily, plan state, preferences
- `infra/main.bicep` + `infra/main.bicepparam` — IaC for ACA + Cosmos Free Tier

