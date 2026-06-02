"""LangGraph trip planner orchestration graph.

Single-agent graph focused on trip planning with tool-calling loop:
  Trip Agent → Tools → Trip Agent → ... → END
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from multiagent.agents.trip_agent import TRIP_TOOLS, build_trip_system_prompt
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
# Trip agent node
# ---------------------------------------------------------------------------
def trip_agent(state: AgentState) -> AgentState:
    """The trip planner agent — invokes LLM with tools bound."""
    llm = _get_llm().bind_tools(TRIP_TOOLS)
    response = llm.invoke([build_trip_system_prompt()] + state["messages"])
    return {"messages": [response], "current_agent": "trip"}


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
tool_node = ToolNode(TRIP_TOOLS)


def _should_continue(state: AgentState) -> str:
    """Route: if last message has tool calls → tools, else → end."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("trip_agent", trip_agent)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("trip_agent")

    # Agent → tools or end
    graph.add_conditional_edges("trip_agent", _should_continue, {"tools": "tools", "end": END})

    # Tools → back to agent (for multi-step tool calling)
    graph.add_edge("tools", "trip_agent")

    return graph.compile()


# Singleton compiled graph
app_graph = build_graph()
