# multiagent — AI Trip Planner

> **Owner**: Munish Goyal ([munishgoyal1](https://github.com/munishgoyal1))
> **Azure account**: munishgoyal1@gmail.com
> **Repo**: https://github.com/munishgoyal1/multiagent (private)
> **Status**: Active development — trip planner with real Amadeus API search

An AI-powered trip planner that creates complete, bookable travel plans in
under 30 minutes of user interaction. Searches real flights, hotels, and
activities via Amadeus APIs, learns from user preferences and past trips,
and can execute bookings on the user's behalf.

## Architecture

Two run modes from the same codebase — only persistence + entrypoint differ.

### Local mode (CLI / API / tests)
```
User ──► Rich CLI  or  FastAPI
                  │
                  ▼
          ┌──────────────┐
          │  Trip Agent  │  (GPT-4.1 + 19 tools)
          └──────┬───────┘
                 │
         ┌───────┼────────┬──────────┐
         ▼       ▼        ▼          ▼
      Search  Reviews   Web        Planner +
      Tools   Tools     Search     Preferences
         │      │         │            │
         ▼      ▼         ▼            ▼
      Duffel  Google   Tavily      ~/.multiagent/
      Amadeus Places   Search      *.json (local)
```

### Hosted mode (React SPA + FastAPI on Azure Container Apps)
```
Browser ──► *.azurecontainerapps.io ──► React SPA (served by FastAPI)
                                              │  /api/* (HTTP + SSE)
                                              ▼
                                       Trip Agent (same)
                                              │
                                              ▼
                                        Azure Cosmos DB
                                        (per-user docs,
                                         /user_id partition,
                                         Free Tier 1000 RU/s)
```

The React single-page app (`frontend/`) is the only UI. In production the same
FastAPI process (`api.py`) serves the built SPA from `frontend/dist` and the
`/api/*` endpoints on one port, so there is a single origin and no separate web
server.

Single-agent LangGraph graph with a tool-calling loop. The agent calls search
tools (Duffel primary, Amadeus fallback), manages a trip plan through draft →
finalized → booked lifecycle, and persists user preferences. Storage dispatch
is automatic: `storage_cosmos.is_enabled()` returns True iff `COSMOS_ENDPOINT`
is set, otherwise local JSON files are used.

## Capabilities

| Tool | Description | Status |
|---|---|---|
| `get_travel_preferences` | Load saved user/family preferences | Working |
| `save_travel_preferences` | Update preferences from conversation | Working |
| `record_past_trip` | Save trip to history with rating | Working |
| `search_flights` | Real flight search — airlines, times, stops, prices | Amadeus API |
| `search_hotels` | Real hotel search — names, ratings, rooms, prices | Amadeus API |
| `search_activities` | Sightseeing, tours, attraction tickets with prices | Amadeus API |
| `search_points_of_interest` | Landmarks, restaurants, attractions | Amadeus API |
| `search_places_with_reviews` | Hotels/attractions with real Google ratings & reviews | Google Places |
| `get_place_reviews` | Detailed reviews & editorial summary for a place | Google Places |
| `nearby_restaurants` | Top-rated restaurants by cuisine & dietary needs | Google Places |
| `check_place_hours` | Is this attraction/restaurant open at the planned time? | Google Places |
| `compute_route` | Real travel time + distance between an ordered list of stops | Google Routes |
| `optimize_day_route` | Reorder a day's stops to minimize total travel time | Google Routes |
| `get_weather_forecast` | Daily weather + seasonal estimate for trip dates | Open-Meteo |
| `web_search` | Fresh travel content (recent guides, seasonal tips) | Tavily |
| `create_trip_plan` | Initialize a new trip plan draft | Working |
| `get_trip_plan` | View current plan with selections | Working |
| `update_trip_plan` | Add flights/hotels/activities to plan | Working |
| `finalize_trip` | Lock plan, show full cost breakdown | Working |
| `execute_bookings` | Book everything and archive trip | Working |
| `list_past_trips` | View archived trip history | Working |

### User Preferences (persistent)

Stored at `~/.multiagent/user_preferences.json`, tracks:
- **Family**: adults, children (ages), elderly, pets
- **Trip style**: leisure | balanced | packed_sightseeing | adventure
- **Budget**: budget | moderate | premium | luxury
- **Hotel**: star rating, amenities, chains, room type
- **Transport**: flight class, direct flights, train/car/bus openness
- **Food**: dietary restrictions, cuisine preferences
- **Past trips**: destination, dates, rating, notes

### Workflow (designed for <30 min)

1. Agent loads preferences automatically
2. User states destination + dates (agent infers the rest)
3. Agent searches flights, hotels, activities in parallel
4. Presents a complete plan with day-by-day itinerary and costs
5. 1-2 refinement rounds if needed
6. User says "execute" → agent books everything

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best AI agent ecosystem |
| Agent framework | LangGraph | Tool-calling loop with state |
| LLM | Azure OpenAI (GPT-4.1; GPT-5 also deployed) | User's own Azure account |
| Travel APIs | Amadeus Self-Service | Flights, hotels, activities, POI |
| Web API | FastAPI + Uvicorn | Async, fast, auto-docs |
| CLI | Rich | Beautiful terminal UI |
| Persistence | JSON files (local) / Cosmos DB (hosted) | Auto-dispatch via env var |
| Hosting target | Azure Container Apps (FastAPI serves the React SPA) | Serverless, scales to zero |

> **Developing locally?** See [`docs/dev.md`](docs/dev.md) for the one-page cheat
> sheet (`.\scripts\test.ps1`, Ctrl+C / F5 loop, scripts table, keyboard shortcuts).

## Quick Start

### Local CLI
```bash
# Clone
git clone https://github.com/munishgoyal1/multiagent.git
cd multiagent

# Install with uv (recommended)
uv sync --all-extras

# Or with pip
pip install -e ".[dev]"

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your keys (see Setup section below)

# Run the assistant (CLI)
uv run python -m multiagent.cli

# Run the API server
uv run uvicorn multiagent.api:app --reload
```

### Local hosted-UI preview (React SPA + FastAPI)
```bash
# Backend (API) + Vite dev server together, with the /api proxy wired up:
scripts\dev-spa.ps1
# open http://localhost:5173
#
# Or run just the backend and have it serve a production SPA build:
cd frontend; npm install; npm run build; cd ..
uv run uvicorn multiagent.api:app --port 8000
# open http://localhost:8000
```

### Fast dev loop (recommended — sub-second iteration)

Don't wait 3–4 minutes for CI on every code change. Use the local dev script
— it runs the FastAPI backend plus the Vite dev server together:

```powershell
scripts\dev-spa.ps1                 # backend on :8000 + Vite on :5173
scripts\dev-spa.ps1 -Watch          # enable live reload for both
scripts\dev-spa.ps1 -BackendOnly    # just the API
scripts\dev-spa.ps1 -FrontendOnly   # just Vite
```

Three speeds of feedback you actually have:

| Speed | Command | When |
|---|---|---|
| ~1 sec | `.venv\Scripts\python.exe -m pytest -q` | logic/tool changes — runs 92 tests |
| ~3 sec reload | `scripts\dev-spa.ps1` | UI / agent prompt / streaming changes — Vite serves the SPA; refresh the browser |
| ~3-4 min | `git push` | only when shipping to prod, changing Dockerfile, or testing CI/Bicep |

The local loop and the deployed app run **identical code**. Only persistence
differs: leave `COSMOS_ENDPOINT` unset → `~/.multiagent/*.json`; set it →
Cosmos. Leave `WEB_SESSION_SECRET` unset → no login (guest-only). So the
inner loop is essentially: edit code → save → tab to browser → refresh.

### Deploy to Azure (hosted, multi-user, Cosmos-backed)
See [infra/README.md](infra/README.md) for the full deploy walkthrough
(GHCR push + `az deployment group create`). Designed to stay inside the
₹10,000/mo Azure free credit by combining Container Apps scale-to-zero
with Cosmos DB Free Tier (1000 RU/s + 25 GB free).

## Setup

### Azure OpenAI (required)
1. Create an Azure OpenAI resource at portal.azure.com
2. Deploy a `gpt-4.1` model (or `gpt-5` for top reasoning)
3. Set in `.env`:
   ```
   AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
   AZURE_OPENAI_API_KEY=your-key
   AZURE_OPENAI_DEPLOYMENT=gpt-4.1
   ```

### Amadeus API (required for real search)
1. Sign up free at [developers.amadeus.com](https://developers.amadeus.com)
2. Create a Self-Service app → get API Key + Secret
3. Set in `.env`:
   ```
   AMADEUS_API_KEY=your-key
   AMADEUS_API_SECRET=your-secret
   AMADEUS_BASE_URL=https://test.api.amadeus.com
   ```
   Use `https://api.amadeus.com` for production (real bookings).
   Free tier: 2,000 API calls/month.

### Google Places API (recommended — adds real ratings & reviews)
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create/select a project → enable **Places API (New)**
3. Create an API key under "Credentials"
4. Set in `.env`:
   ```
   GOOGLE_PLACES_API_KEY=your-key
   ```
   Free tier: $200/month credit (~10K text searches).
   Without this key, the agent still works but can't show real ratings.

### Tavily Web Search (recommended — fresh content beyond LLM cutoff)
1. Sign up free at [tavily.com](https://tavily.com)
2. Copy your API key
3. Set in `.env`:
   ```
   TAVILY_API_KEY=your-key
   ```
   Free tier: 1,000 searches/month.
   Used for "best things to do in X (2026)", seasonal advice, recent openings.

## Project Structure

```
multiagent/
├── REQUIREMENTS.txt              # Running log of all requirements & decisions
├── .github/copilot-instructions.md  # Agent context for Copilot/AI sessions
├── pyproject.toml                # Dependencies & project config
├── Dockerfile                    # Multistage: build SPA (node) + run FastAPI (uvicorn)
│
├── frontend/                     # React 19 + Vite + TS single-page app (the UI)
│   ├── src/                      # App.tsx, ChatPanel, TripPanel, DestinationOverview, ...
│   └── dist/                     # Production build, served by FastAPI in prod
│
├── infra/
│   ├── main.bicep                # RG-scope IaC (ACA + Cosmos + Log Analytics)
│   ├── main.bicepparam           # Pulls values from env vars
│   └── README.md                 # Deploy walkthrough
│
├── src/multiagent/
│   ├── __init__.py
│   ├── __main__.py               # Entry: python -m multiagent
│   ├── config.py                 # Pydantic Settings from .env (incl. Cosmos)
│   ├── graph.py                  # LangGraph single-agent with tool loop
│   ├── cli.py                    # Rich interactive CLI (local)
│   ├── api.py                    # FastAPI server: /api endpoints + serves the SPA
│   ├── user_context.py           # ContextVar holding current user_id
│   ├── storage_cosmos.py         # Optional Cosmos backend (lazy import)
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── trip_view.py          # Pure-Python view-model (frontend-agnostic)
│   │   ├── places_cache.py       # Google Places cache (photos/reviews)
│   │   └── oauth.py              # Standalone Google OAuth (HMAC session cookie)
│   │
│   ├── agents/
│   │   └── trip_agent.py         # Trip planner (19 tools, preference-aware)
│   │
│   └── tools/
│       ├── duffel_flights.py     # Duffel flight search (PRIMARY)
│       ├── amadeus_client.py     # Amadeus OAuth2 client
│       ├── flight_search.py      # Amadeus flight search (fallback)
│       ├── hotel_search.py       # Amadeus hotel search
│       ├── activities_search.py  # Amadeus tours & POI
│       ├── google_places.py      # Real ratings, reviews, restaurants
│       ├── web_search.py         # Tavily live web search
│       ├── trip_planner.py       # Trip lifecycle (Cosmos-aware)
│       └── user_preferences.py   # Preference store (Cosmos-aware)
│
├── tests/
│   └── test_trip.py              # 46 tests (prefs, planner, helpers, Cosmos dispatch)
│
└── ~/.multiagent/                # User data when running locally
    ├── user_preferences.json     # Preferences & past trip history
    ├── active_trip.json          # Current trip plan in progress
    └── trips/                    # Archived booked trips
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Send a message, get agent response |
| GET | `/health` | Health check |

## Running Tests

```bash
uv run pytest -v
```

## Roadmap

- [x] Persistent user preference memory
- [x] Real flight search via Duffel (primary) + Amadeus (fallback)
- [x] Real hotel/activity search via Amadeus
- [x] Real ratings & reviews via Google Places
- [x] Fresh web content via Tavily search
- [x] Trip plan lifecycle (draft → finalize → book)
- [x] Past trip history for learning
- [x] React SPA (served by FastAPI) for hosted multi-user mode
- [x] Azure Cosmos DB persistence (auto-dispatch when configured)
- [x] Azure Container Apps Bicep IaC (Free Tier compatible)
- [ ] TripAdvisor Content API (deeper review data, requires approval)
- [ ] Real booking execution via Duffel Orders API
- [ ] Hotel booking integration (Booking.com / Agoda API)
- [ ] Activity booking integration (Viator / GetYourGuide)
- [ ] Multi-city trip support
- [ ] Group trip planning (multiple families)
- [ ] Custom domain + auth on top of the hosted SPA

## Key Files for New Agents/Sessions

If you're an AI agent picking up this project:
1. Read `REQUIREMENTS.txt` for full history of decisions and requirements
2. Read `.github/copilot-instructions.md` for codebase conventions
3. The graph is in `src/multiagent/graph.py` — single-agent tool loop
4. The agent is in `src/multiagent/agents/trip_agent.py`
5. Tools/connectors are in `src/multiagent/tools/`
6. Always commit AND push after changes (user preference)

## License

MIT
