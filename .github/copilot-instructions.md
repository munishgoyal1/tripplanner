# Copilot Instructions — multiagent

## What is this project?
An AI-powered trip planner for Munish Goyal (munishgoyal1).
It uses LangGraph with a single Trip Agent + 18 tools to create complete,
bookable travel plans. Searches real flights/hotels/activities (Amadeus),
real ratings & reviews (Google Places), and fresh travel content (Tavily).
Learns from user preferences and past trips.

## Owner & Accounts
- GitHub: munishgoyal1 — repo is private
- Azure: munishgoyal1@gmail.com (personal subscription, GPT-4o deployed)
- Amadeus: Self-Service API (test environment, 2000 calls/month free)
- Google Places: free $200/month credit (Places API New)
- Tavily: free 1000 searches/month

## Codebase Conventions
- Python 3.11+, typed with `from __future__ import annotations`
- Single agent in `src/multiagent/agents/trip_agent.py`
- Tools as `@tool`-decorated functions (langchain_core.tools)
- Agent exports: `TRIP_SYSTEM_PROMPT` (SystemMessage) and `TRIP_TOOLS` (list)
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

## Current State (last updated 2026-05-31)
- **Two run modes from one codebase:**
  - LOCAL: CLI (`cli.py`) or FastAPI (`api.py`) — persistence to `~/.multiagent/*.json`
  - HOSTED: Chainlit chat UI (`web/app.py`) — persistence to Azure Cosmos DB
  - Auto-dispatch via `storage_cosmos.is_enabled()` (True when `COSMOS_ENDPOINT` env var set)
  - Per-user identity tracked via `multiagent.user_context.get_user_id()` (ContextVar, default `"local"`)
- Single trip planner agent with 19 tools across 5 families:
  - Preferences (3): get/save/record_past_trip (Cosmos-aware)
  - Duffel flight search (1): search_flights_duffel — PREFERRED primary flight provider
  - Amadeus search (4): flights (fallback), hotels, activities, POI
    (Amadeus self-service is being decommissioned 2026-07-17; kept for hotels & activities)
  - Google Places ratings (3): search_places_with_reviews, get_place_reviews, nearby_restaurants
  - Tavily web search (1): web_search
  - Trip plan lifecycle (6): create/get/update/finalize/execute/list_past_trips (Cosmos-aware)
- Trip plan lifecycle: draft → finalized → booked (with execute command)
- Persistent user preferences:
  - Local: `~/.multiagent/user_preferences.json`
  - Hosted: Cosmos DB `users` container, doc id `preferences`, PK `/user_id`
- Trip state:
  - Local: `~/.multiagent/active_trip.json`, archived in `~/.multiagent/trips/`
  - Hosted: Cosmos DB `users`/`active_trip` (active) + `trips` container (archive)
- Azure infra (Bicep): Container Apps (scale-to-zero) + Cosmos DB (Free Tier 1000 RU/s) +
  Log Analytics. Image hosted on GHCR public. Target footprint ≤ ₹10K/mo free credit.
- 46 tests all passing (10 new Cosmos dispatch + user_context tests added in Session 6)
- New API keys gracefully degrade — tools return "not configured" when env var missing.
- Removed (Session 1): todo, comms, calendar, budget agents. Google OAuth / Twilio integrations.

## Files to Read for Context
- `REQUIREMENTS.txt` — full history of requirements and decisions (Session 6 = hosted mode)
- `README.md` — architecture (local + hosted), setup, project structure
- `infra/README.md` — Azure deploy walkthrough (GHCR + `az deployment group create`)
- `src/multiagent/graph.py` — single-agent tool loop (unchanged for hosted mode)
- `src/multiagent/agents/trip_agent.py` — trip agent with 19 tools
- `src/multiagent/storage_cosmos.py` — optional Cosmos backend (lazy import)
- `src/multiagent/user_context.py` — per-request user_id ContextVar
- `src/multiagent/web/app.py` — Chainlit hosted chat entrypoint
- `src/multiagent/tools/` — Duffel (primary flights), Amadeus, Google Places, Tavily, plan state, preferences
- `infra/main.bicep` + `infra/main.bicepparam` — IaC for ACA + Cosmos Free Tier

