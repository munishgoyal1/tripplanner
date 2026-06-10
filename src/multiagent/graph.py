"""LangGraph trip planner orchestration graph.

Single-agent graph focused on trip planning with tool-calling loop:
  Trip Agent → Tools → Trip Agent → ... → END
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from multiagent.agents.trip_agent import TRIP_TOOLS, build_trip_system_prompt, select_tools
from multiagent.config import get_settings
from multiagent.tools_cache import wrap_tools_with_cache
from multiagent.usage import record_usage
from multiagent.user_context import get_user_id


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    current_agent: str


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
class _UsageCallback(BaseCallbackHandler):
    """Record per-user LLM token usage after every chat completion.

    Pulls ``token_usage`` out of ``LLMResult.llm_output`` (Azure OpenAI puts it
    there) and feeds it to :mod:`multiagent.usage`, which handles the monthly
    cost bucket and persistence.
    """

    def __init__(self, model: str) -> None:
        self._model = model

    def on_llm_end(self, response: Any, **_: Any) -> None:  # noqa: D401
        try:
            usage = (response.llm_output or {}).get("token_usage") or {}
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            if prompt == 0 and completion == 0:
                return
            record_usage(
                get_user_id() or "local",
                model=self._model,
                prompt_tokens=prompt,
                completion_tokens=completion,
            )
        except Exception:
            # Accounting must never break a turn.
            pass


def _get_llm() -> AzureChatOpenAI:
    s = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        azure_deployment=s.azure_openai_deployment,
        api_version=s.azure_openai_api_version,
        temperature=0.3,
        # Stream tokens so astream_events emits on_chat_model_stream chunks —
        # this is what lets the web UIs render the reply as it's typed instead
        # of waiting for the whole turn (which felt "stuck").
        streaming=True,
        callbacks=[_UsageCallback(s.azure_openai_deployment)],
    )


# ---------------------------------------------------------------------------
# Trip agent node
# ---------------------------------------------------------------------------
def trip_agent(state: AgentState) -> AgentState:
    """The trip planner agent — invokes LLM with tools bound."""
    # parallel_tool_calls=True asks the model to emit independent calls in a
    # single turn so ToolNode can execute them concurrently — cuts the
    # round-trip cost in half when we need flights AND hotels AND weather etc.
    # select_tools() binds only the relevant subset (heavy search tools are
    # added only once planning is active) to trim per-turn prompt tokens.
    tools = select_tools(state["messages"])
    llm = _get_llm().bind_tools(tools, parallel_tool_calls=True)
    response = llm.invoke([build_trip_system_prompt()] + state["messages"])
    return {"messages": [response], "current_agent": "trip"}


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
# Wrap the tools with read-through caching for deterministic lookups (flights,
# place reviews, weather, etc.); stateful tools (write/finalize) pass through
# untouched. This is what stops the agent from re-billing Amadeus/Google on
# every turn for the same query.
_CACHED_TOOLS = wrap_tools_with_cache(list(TRIP_TOOLS))
tool_node = ToolNode(_CACHED_TOOLS)


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
