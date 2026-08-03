"""Pure policy for deterministic trip-agent completion gates."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from langchain_core.messages import BaseMessage, HumanMessage

from tripplanner.tools.trip_planner import planning_completion_gaps

COMPLETION_RESEARCH_TOOLS = frozenset({
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
})
MAX_POST_RESEARCH_UPDATES = 1
MAX_INITIAL_ITINERARY_UPDATES = 2
MAX_TOOL_PHASES_PER_TURN = 10

ForcedReason: TypeAlias = Literal[
    "tool_phase_budget",
    "new_trip_creation",
    "hotel_provider_fallback",
    "persist_or_repair_plan",
    "missing_concrete_hotel",
    "kickoff_answered",
    "trip_kickoff",
    "model_choice",
]


@dataclass(frozen=True)
class CompletionPolicyDecision:
    tool_phases: int
    forced_tool: str | None
    forced_reason: ForcedReason
    requirement: str | None = None
    kickoff_tool: str | None = None
    budget_exhausted: bool = False
    completion_gaps: tuple[str, ...] = ()


_NEW_TRIP_REQUEST_RE = re.compile(
    r"\b(?:plan|create|start|build|organize|organise)\b.{0,40}"
    r"\b(?:trip|vacation|holiday|getaway)\b.{0,24}\b(?:to|in)\b",
    re.IGNORECASE,
)
_NEW_TRIP_INTENT_RE = re.compile(
    r"\b(?:new|separate|another|different)\s+(?:\w+\s+){0,3}(?:trip|vacation|holiday|getaway)\b",
    re.IGNORECASE,
)


def _tool_call_positions(messages: Sequence[BaseMessage]) -> list[tuple[int, str]]:
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


def current_turn_tool_phases(messages: Sequence[BaseMessage]) -> int:
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    return sum(
        1
        for index, message in enumerate(messages)
        if index > latest_human and bool(getattr(message, "tool_calls", None))
    )


def _tool_result_texts(
    messages: Sequence[BaseMessage],
    tool_name: str,
) -> list[str]:
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


def trip_update_requirement(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    *,
    has_planning_intent: bool,
) -> str | None:
    positions = _tool_call_positions(messages)
    created_this_turn = any(name == "create_trip_plan" for _, name in positions)
    if not active_trip.get("destination"):
        return None
    if not created_this_turn and not has_planning_intent:
        return None

    update_positions = [index for index, name in positions if name == "update_trip_plan"]
    if (
        not active_trip.get("day_wise_itinerary")
        and len(update_positions) < MAX_INITIAL_ITINERARY_UPDATES
    ):
        return (
            "The new trip has no itinerary. Save a complete structured day_wise_itinerary "
            "now, using sensible defaults rather than asking the user to design it. "
            "A prior update may have failed or saved no days, so include the required "
            "updates_json argument with the full itinerary."
        )

    research_positions = [
        index for index, name in positions if name in COMPLETION_RESEARCH_TOOLS
    ]
    if not research_positions:
        return None
    latest_research = max(research_positions)
    updates_after_research = [
        index for index in update_positions if index > latest_research
    ]
    if not updates_after_research:
        return (
            "Research is complete but has not been persisted. Save the full enriched "
            "day_wise_itinerary and the strongest real hotel, activities, meals, costs, "
            "and other useful researched choices now."
        )

    gaps = planning_completion_gaps(active_trip)
    if gaps and len(updates_after_research) < MAX_POST_RESEARCH_UPDATES:
        return (
            "The saved plan still has completion gaps: "
            + " ".join(gaps)
            + " Use the research already returned to choose sensible defaults, replace "
            "placeholders, and resubmit the full itinerary now."
        )
    return None


def trip_hotel_search_requirement(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    *,
    has_planning_intent: bool,
) -> str | None:
    positions = _tool_call_positions(messages)
    if any(name == "search_hotels" for _, name in positions):
        return None
    if not active_trip.get("destination") or not active_trip.get("day_wise_itinerary"):
        return None
    created_this_turn = any(name == "create_trip_plan" for _, name in positions)
    if not created_this_turn and not has_planning_intent:
        return None
    hotel_gaps = [
        gap for gap in planning_completion_gaps(active_trip) if "hotel" in gap.lower()
    ]
    if not hotel_gaps:
        return None
    return (
        "The saved itinerary still has no concrete hotel: "
        + " ".join(hotel_gaps)
        + " Search real hotels for every overnight city in one parallel tool-call batch "
        "so the strongest preference-matched options can be selected by default in the "
        "next full-plan update. Do not defer another city's hotel search to a later turn."
    )


def trip_hotel_fallback_requirement(
    messages: Sequence[BaseMessage],
) -> str | None:
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
    if not all(
        any(marker in result.lower() for marker in failure_markers)
        for result in results
    ):
        return None
    return (
        "The hotel provider returned no usable candidates. Search Google Places for "
        "preference-matched hotels in the destination, using a hotel-specific query. "
        "Use its real names, ratings, review counts, addresses, and place IDs to choose "
        "the strongest sensible default in the next full-plan update."
    )


def latest_user_starts_new_trip(messages: Sequence[BaseMessage]) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return bool(_NEW_TRIP_INTENT_RE.search(str(message.content or "")))
    return False


def pending_trip_kickoff_answer(messages: Sequence[BaseMessage]) -> bool:
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


def trip_kickoff_tool_choice(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    *,
    has_planning_intent: bool,
) -> str | None:
    if active_trip.get("destination") and not latest_user_starts_new_trip(messages):
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
    if not has_planning_intent:
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
    if "recommend_trip_duration" not in turn_tools:
        return "recommend_trip_duration"
    return "request_trip_input"


def trip_creation_tool_choice(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
) -> str | None:
    active_destination = str(active_trip.get("destination") or "").strip()
    if not active_destination:
        return None

    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    if latest_human < 0:
        return None
    turn_tools = {
        name for index, name in _tool_call_positions(messages) if index > latest_human
    }
    if "create_trip_plan" in turn_tools:
        return None

    request = str(messages[latest_human].content or "").strip()
    if "day trip" in request.lower() or not _NEW_TRIP_REQUEST_RE.search(request):
        return None
    if active_destination.lower() in request.lower():
        return None
    return "create_trip_plan"


def resolve_completion_policy(
    *,
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    proposal_only: bool,
    has_planning_intent: bool,
) -> CompletionPolicyDecision:
    tool_phases = current_turn_tool_phases(messages)
    if not proposal_only and tool_phases >= MAX_TOOL_PHASES_PER_TURN:
        try:
            gaps = tuple(planning_completion_gaps(active_trip))
        except Exception:
            gaps = ()
        return CompletionPolicyDecision(
            tool_phases=tool_phases,
            forced_tool=None,
            forced_reason="tool_phase_budget",
            budget_exhausted=True,
            completion_gaps=gaps,
        )

    creation_tool = (
        None if proposal_only else trip_creation_tool_choice(messages, active_trip)
    )
    new_trip_flow = latest_user_starts_new_trip(messages) or pending_trip_kickoff_answer(
        messages
    )
    hotel_fallback_requirement = (
        None
        if proposal_only or creation_tool or new_trip_flow
        else trip_hotel_fallback_requirement(messages)
    )
    update_requirement = (
        None
        if proposal_only or new_trip_flow or hotel_fallback_requirement
        else trip_update_requirement(
            messages,
            active_trip,
            has_planning_intent=has_planning_intent,
        )
    )
    hotel_search_requirement = (
        None
        if proposal_only
        or new_trip_flow
        or hotel_fallback_requirement
        or update_requirement
        else trip_hotel_search_requirement(
            messages,
            active_trip,
            has_planning_intent=has_planning_intent,
        )
    )
    kickoff_tool = (
        None
        if proposal_only or update_requirement or hotel_search_requirement
        else trip_kickoff_tool_choice(
            messages,
            active_trip,
            has_planning_intent=has_planning_intent,
        )
    )
    kickoff_answered = pending_trip_kickoff_answer(messages)
    forced_tool = (
        creation_tool
        if creation_tool
        else "search_places_with_reviews"
        if hotel_fallback_requirement
        else "update_trip_plan"
        if update_requirement
        else "search_hotels"
        if hotel_search_requirement
        else "create_trip_plan"
        if kickoff_answered
        else kickoff_tool
    )
    forced_reason: ForcedReason = (
        "new_trip_creation"
        if creation_tool
        else "hotel_provider_fallback"
        if hotel_fallback_requirement
        else "persist_or_repair_plan"
        if update_requirement
        else "missing_concrete_hotel"
        if hotel_search_requirement
        else "kickoff_answered"
        if kickoff_answered
        else "trip_kickoff"
        if kickoff_tool
        else "model_choice"
    )
    requirement = (
        hotel_fallback_requirement
        or update_requirement
        or hotel_search_requirement
    )
    return CompletionPolicyDecision(
        tool_phases=tool_phases,
        forced_tool=forced_tool,
        forced_reason=forced_reason,
        requirement=requirement,
        kickoff_tool=kickoff_tool,
    )
