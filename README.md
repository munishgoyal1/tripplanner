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

```
User ──► FastAPI / CLI
              │
              ▼
      ┌──────────────┐
      │  Trip Agent   │  (GPT-4o + 18 tools)
      └──────┬───────┘
             │
     ┌───────┼────────┬──────────┐
     ▼       ▼        ▼          ▼
  Search  Reviews   Web        Planner +
  Tools   Tools     Search     Preferences
     │      │         │            │
     ▼      ▼         ▼            ▼
  Amadeus  Google   Tavily      ~/.multiagent/
  APIs     Places   Search      trip state +
                                preferences
```

Single-agent LangGraph graph with a tool-calling loop. The agent calls search
tools (Amadeus API), manages a trip plan through draft → finalized → booked
lifecycle, and persists user preferences to disk for learning.

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
| LLM | Azure OpenAI (GPT-4o) | User's own Azure account |
| Travel APIs | Amadeus Self-Service | Flights, hotels, activities, POI |
| Web API | FastAPI + Uvicorn | Async, fast, auto-docs |
| CLI | Rich | Beautiful terminal UI |
| Persistence | JSON files (~/.multiagent/) | Preferences + trip history |
| Hosting target | Azure Container Apps | Serverless, scales to zero |

## Quick Start

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

## Setup

### Azure OpenAI (required)
1. Create an Azure OpenAI resource at portal.azure.com
2. Deploy a `gpt-4o` model
3. Set in `.env`:
   ```
   AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
   AZURE_OPENAI_API_KEY=your-key
   AZURE_OPENAI_DEPLOYMENT=gpt-4o
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
├── Dockerfile                    # Container image for Azure deployment
│
├── src/multiagent/
│   ├── __init__.py
│   ├── __main__.py               # Entry: python -m multiagent
│   ├── config.py                 # Pydantic Settings from .env
│   ├── graph.py                  # LangGraph single-agent with tool loop
│   ├── cli.py                    # Rich interactive CLI
│   ├── api.py                    # FastAPI server (/chat, /health)
│   │
│   ├── agents/
│   │   └── trip_agent.py         # Trip planner (14 tools, preference-aware)
│   │
│   └── tools/
│       ├── amadeus_client.py     # Amadeus API HTTP client (OAuth2)
│       ├── flight_search.py      # Flight search + IATA resolution
│       ├── hotel_search.py       # Hotel search + formatting
│       ├── activities_search.py  # Tours, attractions, POI search
│       ├── google_places.py      # Real ratings, reviews, restaurants
│       ├── web_search.py         # Tavily live web search
│       ├── trip_planner.py       # Trip plan state (draft→finalize→book)
│       └── user_preferences.py   # Persistent user preference store
│
├── tests/
│   └── test_trip.py              # 31 tests (prefs, plan state, helpers)
│
└── ~/.multiagent/                # User data (created at runtime)
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
- [x] Real flight/hotel/activity search via Amadeus
- [x] Real ratings & reviews via Google Places
- [x] Fresh web content via Tavily search
- [x] Trip plan lifecycle (draft → finalize → book)
- [x] Past trip history for learning
- [ ] TripAdvisor Content API (deeper review data, requires approval)
- [ ] Real booking execution (Amadeus Flight Orders API)
- [ ] Hotel booking integration (Booking.com / Agoda API)
- [ ] Activity booking integration (Viator / GetYourGuide)
- [ ] Multi-city trip support
- [ ] Group trip planning (multiple families)
- [ ] Deploy to Azure Container Apps via `azd`

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
