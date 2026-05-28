"""LangGraph multi-agent orchestration graph.

The orchestrator routes user requests to the appropriate sub-agent:
  - todo    → Todo Agent
  - comms   → Communications Agent
  - calendar→ Calendar Agent
  - trip    → Trip Planner Agent
  - budget  → Budget Agent
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from multiagent.agents.budget_agent import BUDGET_SYSTEM_PROMPT, BUDGET_TOOLS
from multiagent.agents.calendar_agent import CALENDAR_SYSTEM_PROMPT, CALENDAR_TOOLS
from multiagent.agents.comms_agent import COMMS_SYSTEM_PROMPT, COMMS_TOOLS
from multiagent.agents.todo_agent import TODO_SYSTEM_PROMPT, TODO_TOOLS
from multiagent.agents.trip_agent import TRIP_SYSTEM_PROMPT, TRIP_TOOLS
from multiagent.config import get_settings


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    current_agent: str


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
def _get_llm() -> AzureChatOpenAI:
    s = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        azure_deployment=s.azure_openai_deployment,
        api_version=s.azure_openai_api_version,
        temperature=0.3,
    )


# ---------------------------------------------------------------------------
# Router — decides which sub-agent to invoke
# ---------------------------------------------------------------------------
ROUTER_PROMPT = SystemMessage(content="""\
You are an orchestrator that routes the user's request to the correct sub-agent.
Respond with EXACTLY one word — the agent name:
  todo, comms, calendar, trip, budget, or general

Rules:
- Tasks, reminders, follow-ups → todo
- SMS, email, phone calls → comms
- Calendar events, scheduling, free time → calendar
- Travel, flights, hotels, itineraries → trip
- Expenses, money, budgets, spending → budget
- Anything else → general
""")


def router(state: AgentState) -> AgentState:
    llm = _get_llm()
    response = llm.invoke([ROUTER_PROMPT] + state["messages"][-3:])
    agent_name = response.content.strip().lower().split()[0] if response.content else "general"
    valid = {"todo", "comms", "calendar", "trip", "budget", "general"}
    if agent_name not in valid:
        agent_name = "general"
    return {"messages": [], "current_agent": agent_name}


# ---------------------------------------------------------------------------
# Sub-agent nodes
# ---------------------------------------------------------------------------
AGENT_CONFIG = {
    "todo": (TODO_SYSTEM_PROMPT, TODO_TOOLS),
    "comms": (COMMS_SYSTEM_PROMPT, COMMS_TOOLS),
    "calendar": (CALENDAR_SYSTEM_PROMPT, CALENDAR_TOOLS),
    "trip": (TRIP_SYSTEM_PROMPT, TRIP_TOOLS),
    "budget": (BUDGET_SYSTEM_PROMPT, BUDGET_TOOLS),
}


def _make_agent_node(agent_name: str):
    """Create a node function for a sub-agent."""
    system_prompt, tools = AGENT_CONFIG[agent_name]

    def agent_node(state: AgentState) -> AgentState:
        llm = _get_llm().bind_tools(tools)
        response = llm.invoke([system_prompt] + state["messages"])
        return {"messages": [response], "current_agent": agent_name}

    return agent_node


def general_node(state: AgentState) -> AgentState:
    """Fallback: answer directly without specialized tools."""
    llm = _get_llm()
    system = SystemMessage(content="You are a helpful personal assistant. Answer the user's question directly.")
    response = llm.invoke([system] + state["messages"])
    return {"messages": [response], "current_agent": "general"}


# ---------------------------------------------------------------------------
# Tool execution nodes
# ---------------------------------------------------------------------------
ALL_TOOLS = TODO_TOOLS + COMMS_TOOLS + CALENDAR_TOOLS + TRIP_TOOLS + BUDGET_TOOLS
tool_node = ToolNode(ALL_TOOLS)


def should_use_tools(state: AgentState) -> str:
    """Check if the last message has tool calls."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("router", router)
    for name in AGENT_CONFIG:
        graph.add_node(name, _make_agent_node(name))
    graph.add_node("general", general_node)
    graph.add_node("tools", tool_node)

    # Entry point
    graph.set_entry_point("router")

    # Router → sub-agent
    graph.add_conditional_edges(
        "router",
        lambda s: s["current_agent"],
        {name: name for name in list(AGENT_CONFIG) + ["general"]},
    )

    # Each sub-agent → tools or end
    for name in AGENT_CONFIG:
        graph.add_conditional_edges(name, should_use_tools, {"tools": "tools", "end": END})

    # General → end (no tools)
    graph.add_edge("general", END)

    # Tools → end
    graph.add_edge("tools", END)

    return graph.compile()


# Singleton compiled graph
app_graph = build_graph()
