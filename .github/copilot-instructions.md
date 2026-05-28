# Copilot Instructions — multiagent

## What is this project?
A personal multi-agent assistant for Munish Goyal (munishgoyal1).
It uses LangGraph to orchestrate 5+ sub-agents that handle daily life tasks:
TODOs, messaging, calendar, trip planning, and budgeting.

## Owner & Accounts
- GitHub: munishgoyal1 — repo is private
- Azure: munishgoyal1@gmail.com (personal subscription)
- Google: munishgoyal1@gmail.com (Gmail, Keep, Calendar)

## Codebase Conventions
- Python 3.11+, typed with `from __future__ import annotations`
- One agent per file in `src/multiagent/agents/`
- Tools as `@tool`-decorated functions (langchain_core.tools)
- Each agent exports: `*_SYSTEM_PROMPT` (SystemMessage) and `*_TOOLS` (list)
- Connectors/parsers go in `src/multiagent/tools/`
- Config via Pydantic `Settings` from `.env` (see `config.py`)
- Orchestration graph in `graph.py` — add new agents there
- Tests in `tests/` — use pytest, no mocks for pure logic tests
- Line length: 100 (ruff)
- No unnecessary comments — only non-obvious choices

## Key Architecture
- `graph.py`: LangGraph StateGraph with router → sub-agent → tools → END
- Router: LLM classifies intent into one of: todo, comms, calendar, trip, budget, general
- Each sub-agent: system prompt + tools, bound via `bind_tools()`
- Two entrypoints: CLI (`cli.py`) and FastAPI (`api.py`)

## How to Add a New Agent
1. Create `src/multiagent/agents/new_agent.py`
2. Define tools as `@tool` functions
3. Export `NEW_SYSTEM_PROMPT` and `NEW_TOOLS`
4. Import in `graph.py`, add to `AGENT_CONFIG` dict
5. Add the agent name to the router prompt's valid list
6. The graph auto-wires routing and tool execution

## Working Preferences (from user)
- Always commit AND push after every change
- Keep it simple, modular — no over-engineering
- No major functional changes without user consent
- Update REQUIREMENTS.txt when new requirements come in
- Update README.md when architecture changes
- This file must always reflect current state

## Current State (last updated 2026-05-28)
- 5 sub-agents: todo, comms, calendar, trip, budget
- Todo agent has 9 tools: 4 manual CRUD + 5 source scanners
- 4 source connectors: Google Keep, Gmail, WhatsApp parser, Call records parser
- LLM-powered TODO extractor combines all sources
- In-memory storage (Cosmos DB planned)
- Comms: Twilio wired for SMS/calls, Gmail stub for email
- Calendar/Trip: stubs ready for API integration
- Budget: working in-memory

## Files to Read for Context
- `REQUIREMENTS.txt` — full history of requirements and decisions
- `README.md` — architecture, setup, project structure
- `src/multiagent/graph.py` — orchestration hub
- `.env.example` — all required environment variables
