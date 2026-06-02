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
- 92 tests all passing (Session 10: 25 new tests for continuous-learning schema +
  5 extraction tools + EXTRACTION CHECKLIST prompt rules).
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
- `src/multiagent/web/app.py` — Chainlit hosted chat entrypoint
- `src/multiagent/tools/` — Duffel (primary flights), Amadeus, Google Places, Tavily, plan state, preferences
- `infra/main.bicep` + `infra/main.bicepparam` — IaC for ACA + Cosmos Free Tier

