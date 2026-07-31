"""LangGraph trip planner orchestration graph.

Single-agent graph focused on trip planning with tool-calling loop:
  Trip Agent → Tools → Trip Agent → ... → END
"""

from __future__ import annotations

import operator
import re
from typing import Annotated, Any, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from tripplanner.agents.trip_agent import (
    TRIP_TOOLS,
    build_trip_system_prompt,
    latest_user_has_planning_intent,
    proposal_tools,
    select_tools,
)
from tripplanner.config import get_settings
from tripplanner.tools.trip_planner import load_active_trip_dict, planning_completion_gaps
from tripplanner.tools_cache import wrap_tools_with_cache
from tripplanner.usage import record_usage
from tripplanner.user_context import get_user_id


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    current_agent: str
    proposal_only: bool


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
class _UsageCallback(BaseCallbackHandler):
    """Record per-user LLM token usage after every chat completion.

    Pulls ``token_usage`` out of ``LLMResult.llm_output`` (Azure OpenAI puts it
    there) and feeds it to :mod:`tripplanner.usage`, which handles the monthly
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
def _tool_was_called(messages: list[BaseMessage], tool_name: str) -> bool:
    for message in messages:
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            if name == tool_name:
                return True
    return False


_COMPLETION_RESEARCH_TOOLS = {
    "search_flights_duffel",
    "search_flights",
    "search_hotels",
    "search_activities",
    "search_points_of_interest",
    "search_places_with_reviews",
    "nearby_restaurants",
    "get_weather_forecast",
    "check_visa_requirements",
    "find_local_events",
}
_MAX_POST_RESEARCH_UPDATES = 2
_MAX_INITIAL_ITINERARY_UPDATES = 2


def _tool_call_positions(messages: list[BaseMessage]) -> list[tuple[int, str]]:
    positions: list[tuple[int, str]] = []
    for index, message in enumerate(messages):
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            if name:
                positions.append((index, name))
    return positions


def _tool_result_texts(messages: list[BaseMessage], tool_name: str) -> list[str]:
    call_ids: set[str] = set()
    for message in messages:
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            call_id = (
                tool_call.get("id")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "id", None)
            )
            if name == tool_name and call_id:
                call_ids.add(str(call_id))
    return [
        str(message.content or "")
        for message in messages
        if str(getattr(message, "tool_call_id", "")) in call_ids
    ]


def _trip_update_requirement(messages: list[BaseMessage]) -> str | None:
    positions = _tool_call_positions(messages)
    created_this_turn = any(name == "create_trip_plan" for _, name in positions)
    try:
        trip = load_active_trip_dict() or {}
    except Exception:
        return None
    if not trip.get("destination"):
        return None
    if not created_this_turn and not latest_user_has_planning_intent(messages):
        return None

    update_positions = [index for index, name in positions if name == "update_trip_plan"]
    if (
        not trip.get("day_wise_itinerary")
        and len(update_positions) < _MAX_INITIAL_ITINERARY_UPDATES
    ):
        return (
            "The new trip has no itinerary. Save a complete structured day_wise_itinerary "
            "now, using sensible defaults rather than asking the user to design it. "
            "A prior update may have failed or saved no days, so include the required "
            "updates_json argument with the full itinerary."
        )

    research_positions = [
        index for index, name in positions if name in _COMPLETION_RESEARCH_TOOLS
    ]
    if not research_positions:
        return None
    latest_research = max(research_positions)
    updates_after_research = [index for index in update_positions if index > latest_research]
    if not updates_after_research:
        return (
            "Research is complete but has not been persisted. Save the full enriched "
            "day_wise_itinerary and the strongest real hotel, activities, meals, costs, "
            "and other useful researched choices now."
        )

    gaps = planning_completion_gaps(trip)
    if gaps and len(updates_after_research) < _MAX_POST_RESEARCH_UPDATES:
        return (
            "The saved plan still has completion gaps: "
            + " ".join(gaps)
            + " Use the research already returned to choose sensible defaults, replace "
            "placeholders, and resubmit the full itinerary now."
        )
    return None


def _trip_hotel_search_requirement(messages: list[BaseMessage]) -> str | None:
    positions = _tool_call_positions(messages)
    if any(name == "search_hotels" for _, name in positions):
        return None
    try:
        trip = load_active_trip_dict() or {}
    except Exception:
        return None
    if not trip.get("destination") or not trip.get("day_wise_itinerary"):
        return None
    created_this_turn = any(name == "create_trip_plan" for _, name in positions)
    if not created_this_turn and not latest_user_has_planning_intent(messages):
        return None
    hotel_gaps = [
        gap for gap in planning_completion_gaps(trip) if "hotel" in gap.lower()
    ]
    if not hotel_gaps:
        return None
    return (
        "The saved itinerary still has no concrete hotel: "
        + " ".join(hotel_gaps)
        + " Search real hotels now so the strongest preference-matched option can be "
        "selected by default in the next full-plan update."
    )


def _trip_hotel_fallback_requirement(messages: list[BaseMessage]) -> str | None:
    positions = _tool_call_positions(messages)
    if not any(name == "search_hotels" for _, name in positions):
        return None
    if any(name == "search_places_with_reviews" for _, name in positions):
        return None
    results = _tool_result_texts(messages, "search_hotels")
    if not results:
        return None
    failure_markers = (
        "not configured",
        "no hotels found",
        "hotel list error",
        "hotel search error",
    )
    if not any(marker in result.lower() for result in results for marker in failure_markers):
        return None
    return (
        "The hotel provider returned no usable candidates. Search Google Places for "
        "preference-matched hotels in the destination, using a hotel-specific query. "
        "Use its real names, ratings, review counts, addresses, and place IDs to choose "
        "the strongest sensible default in the next full-plan update."
    )


_NEW_TRIP_INTENT_RE = re.compile(
    r"\b(?:new|separate|another|different)\s+(?:\w+\s+){0,3}(?:trip|vacation|holiday|getaway)\b",
    re.I,
)


def _latest_user_starts_new_trip(messages: list[BaseMessage]) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return bool(_NEW_TRIP_INTENT_RE.search(str(message.content or "")))
    return False


def _pending_trip_kickoff_answer(messages: list[BaseMessage]) -> bool:
    positions = _tool_call_positions(messages)
    latest_create = max(
        (index for index, name in positions if name == "create_trip_plan"),
        default=-1,
    )
    latest_kickoff = max(
        (
            index
            for index, name in positions
            if name == "request_trip_input" and index > latest_create
        ),
        default=-1,
    )
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    return latest_kickoff >= 0 and latest_human > latest_kickoff


def _trip_kickoff_tool_choice(messages: list[BaseMessage]) -> str | None:
    """Choose the required preference-aware step before creating a new trip."""
    try:
        active_trip = load_active_trip_dict() or {}
    except Exception:
        active_trip = {}
    if active_trip.get("destination") and not _latest_user_starts_new_trip(messages):
        return None

    positions = _tool_call_positions(messages)
    latest_create = max(
        (index for index, name in positions if name == "create_trip_plan"),
        default=-1,
    )
    if any(
        name == "request_trip_input" and index > latest_create
        for index, name in positions
    ):
        return None
    if not latest_user_has_planning_intent(messages):
        return None

    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    turn_tools = {name for index, name in positions if index > latest_human}
    if "create_trip_plan" in turn_tools:
        return None
    if "get_travel_preferences" not in turn_tools:
        return "get_travel_preferences"
    return "request_trip_input"


def trip_agent(state: AgentState) -> AgentState:
    """The trip planner agent — invokes LLM with tools bound."""
    # parallel_tool_calls=True asks the model to emit independent calls in a
    # single turn so ToolNode can execute them concurrently — cuts the
    # round-trip cost in half when we need flights AND hotels AND weather etc.
    # select_tools() binds only the relevant subset (heavy search tools are
    # added only once planning is active) to trim per-turn prompt tokens.
    proposal_only = bool(state.get("proposal_only"))
    new_trip_flow = _latest_user_starts_new_trip(
        state["messages"]
    ) or _pending_trip_kickoff_answer(state["messages"])
    hotel_fallback_requirement = (
        None
        if proposal_only or new_trip_flow
        else _trip_hotel_fallback_requirement(state["messages"])
    )
    update_requirement = (
        None
        if proposal_only or new_trip_flow or hotel_fallback_requirement
        else _trip_update_requirement(state["messages"])
    )
    hotel_search_requirement = (
        None
        if proposal_only or new_trip_flow or hotel_fallback_requirement or update_requirement
        else _trip_hotel_search_requirement(state["messages"])
    )
    kickoff_tool = (
        None if proposal_only or update_requirement or hotel_search_requirement
        else _trip_kickoff_tool_choice(state["messages"])
    )
    forced_tool = (
        "search_places_with_reviews"
        if hotel_fallback_requirement
        else "update_trip_plan"
        if update_requirement
        else "search_hotels"
        if hotel_search_requirement
        else "create_trip_plan"
        if _pending_trip_kickoff_answer(state["messages"])
        else kickoff_tool
    )
    tools = select_tools(state["messages"], proposal_only=proposal_only)
    if forced_tool:
        tools = [tool for tool in tools if tool.name == forced_tool]
    llm = _get_llm().bind_tools(
        tools,
        parallel_tool_calls=True,
        **({"tool_choice": forced_tool} if forced_tool else {}),
    )
    instructions = [build_trip_system_prompt()]
    if hotel_fallback_requirement:
        instructions.append(SystemMessage(content=(
            hotel_fallback_requirement
            + " Call search_places_with_reviews before writing any final response."
        )))
    elif update_requirement:
        instructions.append(SystemMessage(content=(
            update_requirement
            + " Call update_trip_plan before writing any final response."
        )))
    elif hotel_search_requirement:
        instructions.append(SystemMessage(content=(
            hotel_search_requirement
            + " Call search_hotels before writing any final response."
        )))
    elif kickoff_tool == "request_trip_input":
        instructions.append(SystemMessage(content=(
            "Start this new trip with one compact preference review. Call "
            "request_trip_input now. Enumerate the relevant saved preferences and "
            "past-trip signals already applied in known_context_json, and prefill "
            "useful trip-specific choices. Do not call create_trip_plan yet."
        )))
    if proposal_only:
        instructions.append(SystemMessage(content=(
            "PROPOSAL-ONLY REVIEW: analyze the itinerary and offer concise numbered options. "
            "Do not create, update, finalize, book, resume, or otherwise mutate trip or user data. "
            "Ask the user to approve an option before any later mutation turn."
        )))
    response = llm.invoke(instructions + state["messages"])
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
proposal_tool_node = ToolNode(proposal_tools(_CACHED_TOOLS))


def _should_continue(state: AgentState) -> str:
    """Route: if last message has tool calls → tools, else → end."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "proposal_tools" if state.get("proposal_only") else "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("trip_agent", trip_agent)
    graph.add_node("tools", tool_node)
    graph.add_node("proposal_tools", proposal_tool_node)

    graph.set_entry_point("trip_agent")

    # Agent → tools or end
    graph.add_conditional_edges(
        "trip_agent",
        _should_continue,
        {"tools": "tools", "proposal_tools": "proposal_tools", "end": END},
    )

    # Tools → back to agent (for multi-step tool calling)
    graph.add_edge("tools", "trip_agent")
    graph.add_edge("proposal_tools", "trip_agent")

    return graph.compile()


# Singleton compiled graph
app_graph = build_graph()
