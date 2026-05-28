# multiagent — Personal Multi-Agent Assistant

A Python-based multi-agent system that acts as your personal assistant for day-to-day tasks.

## Capabilities

| Agent | What it does |
|---|---|
| **Orchestrator** | Routes requests to the right sub-agent |
| **Todo Agent** | Manage tasks, reminders, follow-ups |
| **Comms Agent** | Send SMS, emails, initiate calls via Twilio & Gmail |
| **Calendar Agent** | Read/write Google Calendar, schedule meetings |
| **Trip Planner** | Plan trips with flights, hotels, itineraries |
| **Budget Agent** | Track expenses, budgets, financial summaries |

## Tech Stack

- **Language**: Python 3.11+
- **Agent Framework**: LangGraph (multi-agent orchestration)
- **LLM**: Azure OpenAI (GPT-4o)
- **APIs**: Google (Gmail, Calendar, Contacts), Twilio (SMS/Calls)
- **Web API**: FastAPI + Uvicorn
- **Hosting**: Azure Container Apps
- **Persistence**: Azure Cosmos DB (or local SQLite)

## Quick Start

```bash
# Clone
git clone https://github.com/munishgoyal1/multiagent.git
cd multiagent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your keys

# Run the assistant (CLI)
python -m multiagent.cli

# Run the API server
uvicorn multiagent.api:app --reload
```

## Project Structure

```
multiagent/
├── src/multiagent/
│   ├── agents/           # Sub-agents (todo, comms, calendar, trip, budget)
│   ├── tools/            # Tool functions for agents
│   ├── graph.py          # LangGraph orchestration graph
│   ├── cli.py            # Interactive CLI
│   ├── api.py            # FastAPI server
│   └── config.py         # Settings & env loading
├── tests/
├── pyproject.toml
└── .env.example
```

## License

MIT
