# multiagent — Personal Multi-Agent Assistant

> **Owner**: Munish Goyal ([munishgoyal1](https://github.com/munishgoyal1))
> **Azure account**: munishgoyal1@gmail.com
> **Repo**: https://github.com/munishgoyal1/multiagent (private)
> **Status**: Active development — scaffolded, TODO builder implemented, APIs stubbed

A Python-based multi-agent system that acts as a real personal assistant for
day-to-day life: managing TODOs, sending messages/emails/calls, reading your
Google account, planning trips, and tracking budgets.

## Architecture

```
User ──► FastAPI / CLI
              │
              ▼
         ┌─────────┐
         │  Router  │  (LLM classifies intent)
         └────┬────┘
              │
    ┌─────┬──┴──┬──────┬────────┐
    ▼     ▼     ▼      ▼        ▼
  Todo  Comms Calendar Trip   Budget   ◄── sub-agents
    │     │     │      │        │
    ▼     ▼     ▼      ▼        ▼
  Tools  Tools Tools  Tools   Tools    ◄── LangGraph ToolNode
```

The orchestrator is a **LangGraph StateGraph**. A router node uses GPT-4o to
classify the user's message, then routes to the appropriate sub-agent. Each
sub-agent has its own system prompt and bound tools. Tool calls are executed
by a shared ToolNode, and results flow back to the user.

## Capabilities

| Agent | Tools | Status |
|---|---|---|
| **Todo** | add, list, complete, delete, scan_all_sources, scan_keep, scan_gmail, scan_whatsapp, scan_calls | Working (in-memory) |
| **Comms** | send_sms, send_email, initiate_call | Twilio wired, Gmail stub |
| **Calendar** | list_events, create_event, find_free_slots | Google API stub |
| **Trip Planner** | search_flights, search_hotels, create_itinerary | Stubs |
| **Budget** | add_expense, list_expenses, budget_summary | Working (in-memory) |

### TODO Builder (key feature)

The Todo Agent can auto-extract actionable items from 4 personal data sources:

| Source | Connector | How data gets in |
|---|---|---|
| Google Keep | `gkeepapi` (unofficial) | Live API — needs email + token in `.env` |
| Gmail | Official Gmail API | Live API — needs OAuth `credentials.json` |
| WhatsApp | Regex parser | Export chat as `.txt` → drop in `data/whatsapp/` |
| Call Records | JSON + CSV parser | Google Takeout export → drop in `data/calls/` |

The `TodoExtractor` combines all source text and sends it to GPT-4o, which
returns a structured JSON array of actionable TODOs with title, priority,
due date, source, context, and people involved. Items are deduplicated before
being added to the store.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best AI agent ecosystem |
| Agent framework | LangGraph | Multi-agent orchestration with state |
| LLM | Azure OpenAI (GPT-4o) | User's own Azure account |
| Google APIs | google-api-python-client | Gmail, Calendar |
| Google Keep | gkeepapi | No official API exists |
| SMS/Calls | Twilio | Reliable, Python SDK |
| Web API | FastAPI + Uvicorn | Async, fast, auto-docs |
| CLI | Rich | Beautiful terminal UI |
| Hosting target | Azure Container Apps | Serverless, scales to zero |
| Persistence (future) | Azure Cosmos DB | User's Azure account |

## Quick Start

```bash
# Clone
git clone https://github.com/munishgoyal1/multiagent.git
cd multiagent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -e ".[dev]"

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your keys (see Setup section below)

# Run the assistant (CLI)
python -m multiagent.cli

# Run the API server
uvicorn multiagent.api:app --reload
```

## Setup — Connecting Data Sources

### Azure OpenAI (required for all LLM features)
1. Create an Azure OpenAI resource at portal.azure.com
2. Deploy a `gpt-4o` model
3. Set in `.env`:
   ```
   AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
   AZURE_OPENAI_API_KEY=your-key
   AZURE_OPENAI_DEPLOYMENT=gpt-4o
   ```

### Gmail & Calendar
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project, enable Gmail API + Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json` → place in `credentials/google_credentials.json`
5. First run opens browser for OAuth consent

### Google Keep
1. Set `GOOGLE_KEEP_EMAIL=your@gmail.com` in `.env`
2. Either:
   - Generate an App Password at myaccount.google.com/apppasswords → set `GOOGLE_KEEP_APP_PASSWORD`
   - Or get a master token via `gkeepapi` → set `GOOGLE_KEEP_TOKEN`

### WhatsApp
1. On your phone: open a chat → ⋮ Menu → More → Export Chat → Without media
2. Save the `.txt` file to `data/whatsapp/`

### Call Records
1. Go to [Google Takeout](https://takeout.google.com) → export Phone data
2. Place the JSON or CSV file in `data/calls/`

### Twilio (SMS/Calls)
1. Create a Twilio account at twilio.com
2. Get a phone number
3. Set in `.env`:
   ```
   TWILIO_ACCOUNT_SID=your-sid
   TWILIO_AUTH_TOKEN=your-token
   TWILIO_PHONE_NUMBER=+1234567890
   ```

## Project Structure

```
multiagent/
├── REQUIREMENTS.txt              # Running log of all requirements & decisions
├── .github/copilot-instructions.md  # Agent context for Copilot/AI sessions
├── pyproject.toml                # Dependencies & project config
├── Dockerfile                    # Container image for Azure deployment
├── .env.example                  # Template for environment variables
│
├── src/multiagent/
│   ├── __init__.py
│   ├── __main__.py               # Entry: python -m multiagent
│   ├── config.py                 # Pydantic Settings from .env
│   ├── graph.py                  # LangGraph orchestration (router + agents)
│   ├── cli.py                    # Rich interactive CLI
│   ├── api.py                    # FastAPI server (/chat, /health)
│   │
│   ├── agents/
│   │   ├── todo_agent.py         # 9 tools: manual CRUD + 5 source scanners
│   │   ├── comms_agent.py        # SMS, email, phone calls
│   │   ├── calendar_agent.py     # Google Calendar (stub)
│   │   ├── trip_agent.py         # Trip planning (stub)
│   │   └── budget_agent.py       # Expense tracking
│   │
│   └── tools/
│       ├── google_auth.py        # Shared Google OAuth2 flow
│       ├── keep_connector.py     # Google Keep reader (gkeepapi)
│       ├── gmail_connector.py    # Gmail inbox scanner
│       ├── whatsapp_parser.py    # WhatsApp .txt chat parser
│       ├── call_records_parser.py# Call log JSON/CSV parser
│       └── todo_extractor.py     # LLM-powered TODO extraction engine
│
├── tests/
│   ├── test_todo.py
│   ├── test_budget.py
│   ├── test_whatsapp.py
│   └── test_call_records.py
│
└── data/                         # Personal data (gitignored)
    ├── whatsapp/                 # Drop exported .txt chat files here
    └── calls/                    # Drop Takeout JSON/CSV here
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Send a message, get agent response |
| GET | `/health` | Health check |

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## What's Next (Roadmap)

- [ ] Wire up Gmail connector with real OAuth flow
- [ ] Wire up Calendar agent with Google Calendar API
- [ ] Replace in-memory stores with Azure Cosmos DB
- [ ] Add contacts database (names ↔ phone/email mapping)
- [ ] Implement real flight/hotel search APIs for trip planner
- [ ] Deploy to Azure Container Apps via `azd`
- [ ] Add a simple web UI (Streamlit or React)
- [ ] Scheduled daily scan (cron / Azure Timer Function)

## Key Files for New Agents/Sessions

If you're an AI agent picking up this project:
1. Read `REQUIREMENTS.txt` for full history of decisions and requirements
2. Read `.github/copilot-instructions.md` for codebase conventions
3. The graph is in `src/multiagent/graph.py` — that's the orchestration hub
4. Each agent is self-contained in `src/multiagent/agents/`
5. Tools/connectors are in `src/multiagent/tools/`
6. Always commit AND push after changes (user preference)

## License

MIT
