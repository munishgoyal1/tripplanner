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

## Current State (last updated 2026-06-02)
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
- Single trip planner agent with 32 tools across 10 families:
  - Preferences & continuous learning (9):
    - get_travel_preferences, save_travel_preferences, record_past_trip, remember_about_user
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
- 219 tests all passing (Session 16.6: +8 for `tools/memory_recall.py` BM25-lite
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
  picking one no longer hides the rest.
- **UI polish (Airbnb/TripAdvisor-style)**: Tailwind theme uses coral `brand`
  (#e11d48) + teal `accent`, Inter for UI + Fraunces for display headings
  (loaded via `<link>` in `frontend/index.html`), `rounded-3xl` cards with
  `shadow-card`/`shadow-pop`, sticky composer/toolbar with backdrop blur,
  rating pills, "In trip" ribbons, and a magazine-style hero summary on the
  trip panel. Reusable component classes (`.card`, `.btn-primary`,
  `.btn-ghost`, `.pill`, `.chip`, `.display`) live in
  `frontend/src/index.css`.
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

