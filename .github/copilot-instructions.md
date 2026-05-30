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

## Current State (last updated 2026-05-30)
- Single trip planner agent with 18 tools across 4 families:
  - Preferences (3): get/save/record_past_trip
  - Amadeus real search (4): flights, hotels, activities, POI
  - Google Places ratings (3): search_places_with_reviews, get_place_reviews, nearby_restaurants
  - Tavily web search (1): web_search
  - Trip plan lifecycle (6): create/get/update/finalize/execute/list_past_trips
- Trip plan lifecycle: draft → finalized → booked (with execute command)
- Persistent user preferences at ~/.multiagent/user_preferences.json
  (family config, trip style, budget, hotel/transport/food prefs, past trip history)
- Trip state at ~/.multiagent/active_trip.json, archived in ~/.multiagent/trips/
- 31 tests all passing (preferences, plan state, flight/activity/places/web helpers)
- Removed: todo, comms, calendar, budget agents. Google OAuth / Twilio integrations.
- New API keys gracefully degrade — tools return "not configured" when env var missing.

## Files to Read for Context
- `REQUIREMENTS.txt` — full history of requirements and decisions
- `README.md` — architecture, setup, project structure
- `src/multiagent/graph.py` — single-agent tool loop
- `src/multiagent/agents/trip_agent.py` — trip agent with 18 tools
- `src/multiagent/tools/` — Amadeus, Google Places, Tavily, plan state, preferences
