# tripplanner — AI Trip Planner

> **Owner**: Munish Goyal ([munishgoyal1](https://github.com/munishgoyal1))
> **Azure account**: munishgoyal1@gmail.com
> **Repo**: https://github.com/munishgoyal1/tripplanner (private)
> **Status**: Active development — trip planner with real Amadeus API search

An AI-powered trip planner that creates complete, booking-ready travel plans in
under 30 minutes of user interaction. It searches real flights, hotels, and
activities through capability-specific providers, learns from user preferences
and past trips, and preserves provider handoffs without charging or booking.

## Architecture

Two run modes from the same codebase — only persistence + entrypoint differ.

### Local mode (CLI / API / tests)
```
User ──► Rich CLI  or  FastAPI
                  │
                  ▼
          ┌──────────────┐
          │  Trip Agent  │  (GPT-4.1)
          └──────┬───────┘
                 │
         ┌───────┼────────┬──────────┐
         ▼       ▼        ▼          ▼
      Search  Reviews   Web        Planner +
      Tools   Tools     Search     Preferences
         │      │         │            │
         ▼      ▼         ▼            ▼
      Duffel  Google   Tavily      ~/.tripplanner/
      Amadeus Places   Search      *.json (local)
```

### Hosted mode (React SPA + FastAPI on Azure Container Apps)
```
Browser ──► aitripplanner.co ──► Azure Container Apps ──► React SPA (FastAPI)
                                              │  /api/* (HTTP + SSE)
                                              ▼
                                       Trip Agent (same)
                                              │
                                              ▼
                                        Azure Cosmos DB
                                        (per-user docs,
                                         /user_id partition,
                                         shared Free Tier,
                                         isolated databases)
```

The product has a React SPA (`frontend/`) and native Expo client (`mobile/`).
Both consume contracts, transport, SSE parsing, and workspace state from
`packages/tripplanner-client/`. In production the FastAPI process (`api.py`)
serves the built SPA from `frontend/dist` and the `/api/*` endpoints on one
port. Production is available at <https://aitripplanner.co>; the generated
Azure hostname remains available for rollback access. The iOS/Android app calls
the same hosted endpoints directly and uses
native browser OAuth to adopt the web app's stable Google identity. Hosted API
access is authorized by signed web/mobile sessions or a signed anonymous guest
capability; caller-supplied account ids are never authoritative.

Single-agent LangGraph graph with a tool-calling loop. The agent calls search
tools (Duffel primary, Amadeus fallback), manages a trip plan through draft →
finalized → booked lifecycle, and persists user preferences. Storage dispatch
is automatic: `storage_cosmos.is_enabled()` returns True iff `COSMOS_ENDPOINT`
is set, otherwise local JSON files are used. Local trip, history, chat, and
Places-cache writes use atomic replacement. FastAPI runs complete blocking
trip load/mutate/render operations in worker threads so they do not stall the
async request loop.

Direct itinerary edits use a two-speed planner-review contract. The mutation is
applied immediately and returns its final authoritative day after any reflow. A
deterministic impact check stays silent for routine edits but returns a shared
`PlannerReview` when the result is materially crowded, travel-heavy, empty, or
missing a meal. The SPA then lets the user keep the valid change or start a
proposal-only Assistant turn; no AI rearrangement occurs without explicit
approval. Proposal mode is enforced in the graph with read-only tool binding
and execution, and the API disables itinerary fallback persistence and passive
learning for that turn.

## Capabilities

| Tool | Description | Status |
|---|---|---|
| `get_travel_preferences` | Load saved user/family preferences | Working |
| `save_travel_preferences` | Update preferences from conversation | Working |
| `record_past_trip` | Save trip to history with rating | Working |
| `record_trip_postmortem` | Structured post-mortem (rating + what worked/didn't), feeds learned_notes | Working |
| `search_flights` | Real flight search — airlines, times, stops, prices | Amadeus API |
| `search_hotels` | Live hotel rates with legacy property fallback | LiteAPI / legacy |
| `search_activities` | Tours, schedules, and from-prices with legacy fallback | Viator / Amadeus |
| `search_points_of_interest` | Landmarks, restaurants, attractions | Amadeus API |
| `search_places_with_reviews` | Hotels/attractions with real Google ratings & reviews | Google Places |
| `get_place_reviews` | Detailed reviews & editorial summary for a place | Google Places |
| `nearby_restaurants` | Top-rated restaurants by cuisine & dietary needs | Google Places |
| `check_place_hours` | Is this attraction/restaurant open at the planned time? | Google Places |
| `compute_route` | Real travel time + distance between an ordered list of stops | Google Routes |
| `optimize_day_route` | Reorder a day's stops to minimize total travel time | Google Routes |
| `get_weather_forecast` | Daily weather + seasonal estimate for trip dates | Open-Meteo |
| `check_visa_requirements` | Visa/entry rules for passport → destination, with official-source links | Tavily |
| `find_local_events` | Festivals / parades / public holidays overlapping trip dates | Tavily |
| `recall_relevant_memory` | Top-K relevant items from learned notes / past trips / family / about-me | BM25-lite (no API) |
| `web_search` | Fresh travel content (recent guides, seasonal tips) | Tavily |
| `create_trip_plan` | Initialize a new trip plan draft | Working |
| `get_trip_plan` | View current plan with selections | Working |
| `update_trip_plan` | Add flights/hotels/activities to plan | Working |
| `finalize_trip` | Lock plan, show full cost breakdown | Working |
| `execute_bookings` | Book everything and archive trip | Working |
| `list_past_trips` | View archived trip history | Working |

### User Preferences (persistent)

Stored at `~/.tripplanner/user_preferences.json`, tracks:
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

> **Developing locally?** Run `scripts\win\Setup-Tripplanner-Dev.cmd` on Windows or
> `./scripts/mac/Setup-Tripplanner-Dev.command` on macOS to reproduce the full toolchain
> and VS Code/Copilot configuration. See
> [`docs/development/new-machine-setup.md`](docs/development/new-machine-setup.md)
> for manual sign-ins and non-portable state, then see
> [`docs/development/dev.md`](docs/development/dev.md) for the `.\scripts\dev\dev-spa.ps1` workflow.
> For isolated feature work, use the sandbox workflow described in
> [`docs/development/parallel-agent-development.md`](docs/development/parallel-agent-development.md).

## Quick Start

### One-click Windows setup
```powershell
.\scripts\win\Setup-Tripplanner-Dev.cmd
.\scripts\dev\dev-spa.ps1
```

### One-click macOS setup
```bash
./scripts/mac/Setup-Tripplanner-Dev.command
pwsh -File scripts/dev/dev-spa.ps1
```

The setup command installs missing prerequisites, restores locked dependencies,
applies portable VS Code/Copilot configuration, and preserves any existing `.env`.
See [docs/development/new-machine-setup.md](docs/development/new-machine-setup.md)
for required manual authentication, and [docs/operations/deployment-flow.md](docs/operations/deployment-flow.md)
for the two-stage canary and production release flow.

### Local CLI
```bash
# Clone
git clone https://github.com/munishgoyal1/tripplanner.git
cd tripplanner

# Install with uv (recommended)
uv sync --all-extras

# Or with pip
pip install -e ".[dev]"

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your keys (see Setup section below)

# Run the assistant (CLI)
uv run python -m tripplanner.cli

# Run the API server
uv run uvicorn tripplanner.api:app --reload
```

### Local hosted-UI preview (React SPA + FastAPI)
```bash
# Backend (API) + Vite dev server together, with the /api proxy wired up:
scripts\dev\dev-spa.ps1
# open http://localhost:5173
#
# Or run just the backend and have it serve a production SPA build:
cd frontend; npm install; npm run build; cd ..
uv run uvicorn tripplanner.api:app --port 8000
# open http://localhost:8000
```

### Native mobile app (Expo Go)
```powershell
cd mobile
npm install
npx expo start --tunnel
```

Open the project from Expo Go on iOS or Android. The production API is the
default; set `EXPO_PUBLIC_API_BASE_URL` to a reachable canary or development
URL to override it. See [mobile/README.md](mobile/README.md) for platform run
commands, Google sign-in, EAS builds, and store submission steps.

### Fast dev loop (recommended — sub-second iteration)

Don't wait 3–4 minutes for CI on every code change. Use the local dev script
— it runs the FastAPI backend plus the Vite dev server together:

```powershell
scripts\dev\dev-spa.ps1                 # backend on :8000 + Vite on :5173
scripts\dev\dev-spa.ps1 -Watch          # enable live reload for both
scripts\dev\dev-spa.ps1 -BackendOnly    # just the API
scripts\dev\dev-spa.ps1 -FrontendOnly   # just Vite
scripts\dev\dev-spa.ps1 -CosmosBackend azure # explicitly use Azure tripplanner-local
scripts\dev\dev-spa.ps1 -UseCanaryData  # explicitly share hosted canary data
```

By default, `scripts\dev\dev-spa.ps1` launches Docker Desktop when needed, starts
the official Dockerized **Cosmos DB Emulator**, and uses its isolated
`tripplanner-local` database. Emulator data persists in a named Docker volume.
Rerunning the script force-stops process trees listening on the enabled API,
frontend, and Labs ports and verifies each port is released before restart. Use
custom port parameters before launch when another application needs a default port.
Docker Desktop must already be installed; startup waits up to two minutes for
its daemon and reports a clear error without resetting emulator data. Set
`COSMOS_DEV_BACKEND=azure` in `.env` or pass `-CosmosBackend azure` to explicitly
use the shared Azure account's isolated `tripplanner-local` database. Azure mode
requires Azure CLI sign-in; credentials are resolved at startup and never written to `.env`.
`-UseCanaryData` remains a separate advanced override for hosted canary data.


Three speeds of feedback you actually have:

| Speed | Command | When |
|---|---|---|
| Fast | `.venv\Scripts\python.exe -m pytest -q` | Backend logic and tool changes |
| ~3 sec reload | `scripts\dev\dev-spa.ps1` | UI / agent prompt / streaming changes — Vite serves the SPA; refresh the browser |
| Release | `infra\deploy-canary.ps1` | Build, deploy, and smoke the immutable canary image |

The local loop and deployed app run **identical code**. The dev script sets the
emulator endpoint explicitly, while hosted Container Apps use environment-
specific databases in the shared account. Leave `COSMOS_ENDPOINT` unset when
running the CLI directly to retain the local JSON fallback.

### Deploy to Azure (hosted, multi-user, Cosmos-backed)
See the canonical [deployment flow](docs/operations/deployment-flow.md) for the
release procedure and [infra/README.md](infra/README.md) for infrastructure
ownership. One
lifetime free-tier account hosts separate 400-RU/s canary and production
databases (800 RU/s total), while Container Apps remain scale-to-zero.

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

### LiteAPI (recommended for live hotel and flight availability)
1. Create an account and obtain a server-side API key from LiteAPI.
2. Set in `.env`:
   ```
   LITEAPI_API_KEY=your-key
   TRAVEL_HOTEL_PROVIDER=auto
   TRAVEL_FLIGHT_PROVIDER=auto
   ```
   `auto` prefers LiteAPI when configured and otherwise preserves the legacy
   providers. The key is backend-only. This integration searches and verifies
   rates; it does not prebook, book, charge, cancel, or create orders.

### Viator (recommended for live activity discovery)
1. Obtain a Basic Access Affiliate sandbox API key from Viator.
2. Paste it into the existing blank `VIATOR_API_KEY=` entry in `.env`.
   `TRAVEL_ACTIVITY_PROVIDER=auto` selects Viator when configured and otherwise
   preserves Amadeus fallback. Results include schedules and from-prices only;
   no availability check, reservation, booking, payment, or cancellation is made.

### Amadeus API (legacy activities and search fallback)
1. Sign up free at [developers.amadeus.com](https://developers.amadeus.com)
2. Create a Self-Service app → get API Key + Secret
3. Set in `.env`:
   ```
   AMADEUS_API_KEY=your-key
   AMADEUS_API_SECRET=your-secret
   AMADEUS_BASE_URL=https://test.api.amadeus.com
   ```
   Use `https://api.amadeus.com` only for supported production search traffic.
   Free tier: 2,000 API calls/month.

### Email export (optional)
`Send to email` only works when you configure an actual mail transport. Two supported options:

1. Azure Communication Services Email
   ```
   AZURE_COMMUNICATION_CONNECTION_STRING=endpoint=https://...;accesskey=...
   AZURE_COMMUNICATION_EMAIL_SENDER=DoNotReply@YOUR_DOMAIN.azurecomm.net
   ```

2. SMTP
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-user
   SMTP_PASSWORD=your-password-or-app-password
   SMTP_FROM=your-from-address
   SMTP_USE_TLS=1
   ```

If neither is set, the app falls back to opening a local `mailto:` draft.

### Map-rich itinerary export

Preview, Print / Save PDF, direct PDF, and email exports can include embedded
day route maps plus place photos and details. The server-side
`GOOGLE_PLACES_API_KEY` must allow both Places API (New) and Maps Static API;
the export falls back to the labeled route circuit when Static Maps is unavailable.

### Coherent place changes

Add/remove responses update Details, Itinerary, and Map from the same saved trip
state. When a place appears more than once, the itinerary trash action removes
that exact day/stop. Details and Map provide an occurrence menu with day/time
context plus a separate **Remove everywhere** action; this does not rely on the
Assistant pane being open.

### Google Places API (recommended — adds real ratings & reviews)
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Use the environment project: `aitripplanner-local`, `aitripplanner-canary`,
   or `aitripplanner-prod`. The projects share billing, not credentials.
3. Enable **Maps JavaScript API**, **Places API (New)**, **Routes API**, and
   **Maps Static API**.
4. Create a server key restricted to Places, Routes, and Static Maps, plus a
   separate browser key restricted by environment referrer to Maps JavaScript
   and Places.
5. Set them in `.env`, `.env.canary`, or `.env.prod` as appropriate:
   ```
   GOOGLE_PLACES_API_KEY=your-server-key
   GOOGLE_MAPS_BROWSER_KEY=your-browser-key
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
tripplanner/
├── docs/README.md                # Documentation index and ownership guide
├── docs/REQUIREMENTS.md          # Current capability baseline + proposed roadmap
├── docs/reference/               # Owner inputs + chronological history
├── docs/roadmap/                 # Consolidated future feature candidates
├── docs/feature-briefs/          # Reusable template + editable next increment
├── .github/copilot-instructions.md  # Agent context for Copilot/AI sessions
├── pyproject.toml                # Dependencies & project config
├── Dockerfile                    # Multistage: build SPA (node) + run FastAPI (uvicorn)
│
├── frontend/                     # React 19 + Vite + TS single-page app (the UI)
│   ├── labs/                     # Isolated UX experiments and build configuration
│   ├── src/                      # App.tsx, ChatPanel, TripPanel, DestinationOverview, ...
│   └── dist/                     # Production build, served by FastAPI in prod
│
├── packages/tripplanner-client/  # Shared web/native contracts and request helpers
│
├── scripts/
│   ├── README.md                 # Developer workflow + utility ownership
│   ├── user/                     # Regular owner-facing launchers
│   └── dev/                      # Local stack, worktrees, sync, and emulator
│       └── cosmos-emulator.compose.yml  # Portable local persistence
│
├── infra/
│   ├── data-stack.bicep          # Subscription-scope shared data bootstrap
│   ├── data.bicep                # Free-tier Cosmos account + databases
│   ├── main.bicep                # RG-scope IaC (ACA + Log Analytics)
│   ├── canary.bicepparam         # Canary app + database binding
│   ├── prod.bicepparam           # Production app + database binding
│   └── README.md                 # Deploy walkthrough
│
├── src/tripplanner/
│   ├── __init__.py
│   ├── __main__.py               # Entry: python -m tripplanner
│   ├── config.py                 # Pydantic Settings from .env (incl. Cosmos)
│   ├── graph.py                  # LangGraph single-agent with tool loop
│   ├── cli.py                    # Rich interactive CLI (local)
│   ├── api.py                    # FastAPI server: /api endpoints + serves the SPA
│   ├── user_context.py           # ContextVar holding current user_id
│   ├── json_store.py             # Atomic local JSON persistence
│   ├── storage_cosmos.py         # Cosmos backend + conditional create/replace/delete
│   │
│   ├── web/
│   │   ├── __init__.py
│   │   ├── trip_view.py          # Pure-Python view-model (frontend-agnostic)
│   │   ├── places_cache.py       # Synchronized Google Places cache
│   │   ├── trip_operations.py    # Blocking trip operations used by async routes
│   │   ├── chat_store.py         # Trip transcripts + principal request replay index
│   │   └── oauth.py              # Standalone Google OAuth (HMAC session cookie)
│   │
│   ├── agents/
│   │   └── trip_agent.py         # Preference-aware trip planner
│   │
│   └── tools/
│       ├── duffel_flights.py     # Duffel flight search (PRIMARY)
│       ├── amadeus_client.py     # Amadeus OAuth2 client
│       ├── flight_search.py      # Amadeus flight search (fallback)
│       ├── hotel_search.py       # Amadeus hotel search
│       ├── activities_search.py  # Viator activity boundary + Amadeus fallback/POI
│       ├── google_places.py      # Real ratings, reviews, restaurants
│       ├── web_search.py         # Tavily live web search
│       ├── trip_planner.py       # Trip lifecycle (Cosmos-aware)
│       └── user_preferences.py   # Sparse/explicit preference merge + replayable mutations
│
├── tests/
│   └── test_trip.py              # Preferences, planner, helpers, Cosmos dispatch
│
└── ~/.tripplanner/                # User data when running locally
    ├── user_preferences.json     # Preferences & past trip history
    ├── active_trip.json          # Current trip plan in progress
   ├── trips/                    # Archived booked trips
   └── chats/                    # Trip transcripts + bounded chat_operations index
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

The current capability baseline, explicit gaps, and proposed roadmap live in
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md). Roadmap entries are
candidate outcomes, not automatic approval. The consolidated longer-term
feature backlog lives in
[`docs/roadmap/FUTURE_FEATURES.md`](docs/roadmap/FUTURE_FEATURES.md). Use
[`docs/feature-briefs/NEXT_INCREMENT.md`](docs/feature-briefs/NEXT_INCREMENT.md)
to scope the next coherent milestone.

## Key Files for New Agents/Sessions

If you're an AI agent picking up this project:
1. Read `docs/README.md`, `docs/CODEMAP.md`, `docs/PRODUCT.md`, and `docs/REQUIREMENTS.md`
2. Read `.github/copilot-instructions.md` for codebase conventions
3. Read `docs/reference/README.md` only when original intent or history is needed
4. For planned feature work, read the active brief under `docs/feature-briefs/`
5. The graph is in `src/tripplanner/graph.py` and tools are in `src/tripplanner/tools/`
6. Always commit AND push after changes (user preference)

## License

MIT
