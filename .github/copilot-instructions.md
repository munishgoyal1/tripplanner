# Copilot Instructions — multiagent

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
  - HOSTED: Chainlit chat UI (`web/app.py`) — persistence to Azure Cosmos DB
  - Auto-dispatch via `storage_cosmos.is_enabled()` (True when `COSMOS_ENDPOINT` env var set)
  - Per-user identity tracked via `multiagent.user_context.get_user_id()` (ContextVar, default `"local"`)
- **Identity tracks (Session 11, hosted mode only)**:
  - OAuth login (Google + GitHub) → identifier `"{provider}-{external_id}"` (cross-device)
  - Persistent guest cookie `multiagent_guest_id` → identifier `"guest-<uuid>"` (same browser, 1 year)
  - Per-session fallback → Chainlit session id (legacy, used when `CHAINLIT_AUTH_SECRET` unset)
  - Facebook OAuth is **not** wired (not in Chainlit's built-in providers); GitHub was added instead.
  - Setup walkthrough: `docs/setup-oauth.md`. All OAuth env vars are optional;
    leaving them unset keeps the app login-less.
- Single trip planner agent with 25 tools across 5 families:
  - Preferences & continuous learning (9):
    - get_travel_preferences, save_travel_preferences, record_past_trip, remember_about_user
    - update_user_profile, add_family_member, add_user_interest, add_user_dislike,
      record_trip_mention (Cosmos-aware)
  - Duffel flight search (1): search_flights_duffel — PREFERRED primary flight provider
  - Amadeus search (4): flights (fallback), hotels, activities, POI
    (Amadeus self-service is being decommissioned 2026-07-17; kept for hotels & activities)
  - Google Places ratings (3): search_places_with_reviews, get_place_reviews, nearby_restaurants
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
- 182 tests all passing (Session 13: 5 tests for the decoupled `trip_view`
  view-model; Session 12: 20 tests for the right-rail sidebar panels +
  focus-action builder + destination-highlights fallback; Session 10 added 25
  continuous-learning tests).
- **Currency rule (Session 12)**: trip agent prompt CRITICAL RULE 8 picks ONE
  sticky display currency per plan. Domestic trips use the user's HOME currency
  (from `profile.home_country`; default INR ₹). International trips may use USD
  (or the destination's local currency) where it makes most sense, optionally
  showing the home-currency equivalent in parentheses. Converts source
  currencies (e.g. Duffel USD) to the chosen one. Fixes prices flipping
  INR↔USD between sessions.
- **Right-rail sidebar (Session 12, hosted mode only)**: `web/sidebar.py` +
  `web/places_cache.py`. Plugin-style — each panel is a function
  `render(SidebarContext) -> list[Element]` registered in `PANELS`. v1 panels
  are Overview, Photo gallery (Google Places photos), Reviews & descriptions.
  Refreshes automatically after every agent turn. Hotels/attractions in the
  reply get `cl.Action` "🏨/🎯/🌐 Whole trip" buttons that zoom the sidebar via
  `@cl.action_callback("focus_item")`. Places lookups (Text Search + Photo
  URI + Reviews) cached per-session under `cl.user_session["places_cache"]`.
  No `place_id` is stored in the trip plan — sidebar resolves by name+city
  on demand. To add a panel: append to `PANELS`. To re-order/hide: edit
  that list. No other changes needed.
  When no hotels/activities are selected yet but a destination is known, the
  sidebar falls back to the destination's top hotels & attractions
  (`places_cache.top_places`) so panels fill during browsing instead of
  staying blank; a "popular spots" note flags these as suggestions.
- **Decoupled trip panel (Session 13, frontend-agnostic)**: data shaping moved
  into pure-Python `web/trip_view.py` (ZERO Chainlit imports) — `build_view(trip,
  focus) -> dict` is the single JSON view-model contract. Consumed by BOTH the
  Chainlit panel and the `GET /trip/view` FastAPI endpoint (`api.py`), so a
  future standalone React/HTML frontend (option C) reuses the same contract with
  no backend rework. Rendering is the interactive React custom element
  `public/elements/TripPanel.jsx` (overview header, per-item photo/review cards,
  in-element "Back to whole trip" button, and an "Add to trip" button →
  `select_item` action → `trip_planner.add_selection`). `web/sidebar.py` is now
  a thin adapter: helpers delegate to `trip_view`, `render_sidebar` pushes a
  single `cl.CustomElement(name="TripPanel", props=build_view(...))` and falls
  back to the legacy `PANELS` (cl.Text/cl.Image) only if the custom element
  fails. This answers the panel-recovery question: the rail auto-reopens on the
  next `set_elements` (every turn) and the element has its own Back control, so
  Chainlit's built-in collapse arrow is no longer the only way back.
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
- `src/multiagent/agents/trip_agent.py` — trip agent with 25 tools (incl. EXTRACTION CHECKLIST prompt)
- `src/multiagent/storage_cosmos.py` — optional Cosmos backend (lazy import)
- `src/multiagent/user_context.py` — per-request user_id ContextVar
- `src/multiagent/web/app.py` — Chainlit hosted chat entrypoint (wires sidebar)
- `src/multiagent/web/trip_view.py` — pure-Python frontend-agnostic view-model (`build_view`)
- `src/multiagent/web/sidebar.py` — thin Chainlit adapter (renders `TripPanel` custom element)
- `public/elements/TripPanel.jsx` — interactive React custom element for the trip panel
- `src/multiagent/web/places_cache.py` — per-session Google Places cache for the sidebar
- `src/multiagent/tools/` — Duffel (primary flights), Amadeus, Google Places, Tavily, plan state, preferences
- `infra/main.bicep` + `infra/main.bicepparam` — IaC for ACA + Cosmos Free Tier

