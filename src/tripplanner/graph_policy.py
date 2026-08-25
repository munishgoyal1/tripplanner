"""Pure policy for deterministic trip-agent completion gates."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from langchain_core.messages import BaseMessage, HumanMessage

from tripplanner.tools.trip_planner import (
    core_planning_completion_gaps,
    planning_completion_gaps,
)

COMPLETION_RESEARCH_TOOLS = frozenset({
    "search_flights_duffel",
    "search_flights",
    "compare_transport_options",
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
    "origin_correction",
    "hotel_provider_fallback",
    "persist_or_repair_plan",
    "missing_concrete_hotel",
    "kickoff_answered",
    "awaiting_kickoff_answer",
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
    awaiting_kickoff_answer: bool = False


_NEW_TRIP_REQUEST_RE = re.compile(
    r"\b(?:plan|create|start|build|organize|organise)\b.{0,40}"
    r"\b(?:trip|vacation|holiday|getaway)\b.{0,24}\b(?:to|in)\b",
    re.IGNORECASE,
)
_NEW_TRIP_INTENT_RE = re.compile(
    r"\b(?:new|separate|another|different)\s+(?:\w+\s+){0,3}(?:trip|vacation|holiday|getaway)\b",
    re.IGNORECASE,
)
_ORIGIN_CORRECTION_RE = re.compile(
    r"\b(?:origin|departure city|departing from|flying from)\b",
    re.IGNORECASE,
)
_EXPLICIT_PARTY_RELATION_RE = re.compile(
    r"\b(?:solo|travell?ing alone|couple)\b",
    re.IGNORECASE,
)
_ADULT_COUNT_RE = re.compile(r"\b(\d+)\s*(?:adults?|grown[ -]?ups?)\b", re.IGNORECASE)
_CHILD_COUNT_RE = re.compile(r"\b(\d+)\s*(?:children|child|kids?)\b", re.IGNORECASE)
_LODGING_GAP_RE = re.compile(
    r"\b(?:hotel|lodging|bookable (?:property|stay))\b",
    re.IGNORECASE,
)


#: Tools a saved turn ran, restored by chat_store. The graph's tool messages do
#: not survive a turn, so anything deciding across turns must read this too.
RAN_TOOLS_KEY = "ran_tools"


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
        for name in (getattr(message, "additional_kwargs", None) or {}).get(RAN_TOOLS_KEY) or []:
            if name:
                positions.append((index, str(name)))
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
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    current_updates = [index for index in update_positions if index > latest_human]
    update_results = _tool_result_texts(messages, "update_trip_plan")
    if (
        current_updates
        and len(current_updates) < MAX_INITIAL_ITINERARY_UPDATES
        and update_results
        and update_results[-1].lstrip().startswith("Error:")
    ):
        return (
            "The requested trip change was not saved because update_trip_plan failed: "
            + update_results[-1]
            + " Correct the rejected fields and call update_trip_plan again before "
            "claiming the itinerary changed."
        )
    if (
        not active_trip.get("day_wise_itinerary")
        # Counting every save in the conversation retired this gate after the
        # second one, so a trip created later was free to end with no itinerary.
        and len(current_updates) < MAX_INITIAL_ITINERARY_UPDATES
    ):
        return (
            "The new trip has no itinerary. Save a complete structured day_wise_itinerary "
            "now, using sensible defaults rather than asking the user to design it. "
            "A prior update may have failed or saved no days, so include the required "
            "updates_json argument with the full itinerary."
        )

    # Research the user already got an answer about belongs to the turn that ran
    # it. Leaving this unscoped made a new request inherit the previous turn's
    # unfinished work and answer the wrong question entirely.
    research_positions = [
        index
        for index, name in positions
        if name in COMPLETION_RESEARCH_TOOLS and index > latest_human
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


def origin_correction_requirement(
    messages: Sequence[BaseMessage], active_trip: dict[str, Any]
) -> str | None:
    if not active_trip.get("destination"):
        return None
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    if latest_human < 0 or not _ORIGIN_CORRECTION_RE.search(
        str(messages[latest_human].content or "")
    ):
        return None
    turn_tools = {
        name for index, name in _tool_call_positions(messages) if index > latest_human
    }
    if "update_trip_plan" in turn_tools:
        return None
    return (
        "The traveller explicitly supplied or corrected the active trip origin. "
        "Call update_trip_plan now with the stated origin and update the itinerary's "
        "outbound and return travel before replying."
    )


def trip_hotel_search_requirement(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    *,
    has_planning_intent: bool,
) -> str | None:
    positions = _tool_call_positions(messages)
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    if any(
        index > latest_human and name == "search_hotels"
        for index, name in positions
    ):
        return None
    if not active_trip.get("destination") or not active_trip.get("day_wise_itinerary"):
        return None
    created_this_turn = any(name == "create_trip_plan" for _, name in positions)
    if not created_this_turn and not has_planning_intent:
        return None
    hotel_gaps = [
        gap for gap in planning_completion_gaps(active_trip) if _LODGING_GAP_RE.search(gap)
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
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    turn_messages = messages[latest_human + 1:]
    positions = _tool_call_positions(turn_messages)
    if not any(name == "search_hotels" for _, name in positions):
        return None
    if any(name == "search_places_with_reviews" for _, name in positions):
        return None
    results = _tool_result_texts(turn_messages, "search_hotels")
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


def latest_user_has_explicit_party(messages: Sequence[BaseMessage]) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = str(message.content or "")
            if _EXPLICIT_PARTY_RELATION_RE.search(text):
                return True
            adults = _ADULT_COUNT_RE.search(text)
            children = _CHILD_COUNT_RE.search(text)
            if adults and children:
                return int(children.group(1)) > 0 or int(adults.group(1)) == 1
            return False
    return False


def latest_user_requests_different_trip(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
) -> bool:
    """True when the newest message asks to plan somewhere other than the active trip."""
    active_destination = str(active_trip.get("destination") or "").strip()
    if not active_destination:
        return False
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    if latest_human < 0:
        return False
    request = str(messages[latest_human].content or "").strip()
    if "day trip" in request.lower() or not _NEW_TRIP_REQUEST_RE.search(request):
        return False
    return active_destination.lower() not in request.lower()


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


def awaiting_trip_kickoff_answer(messages: Sequence[BaseMessage]) -> bool:
    """True while the prefilled review has been asked and the traveller has not replied."""
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    return any(
        name == "request_trip_input" and index > latest_human
        for index, name in _tool_call_positions(messages)
    )


def trip_kickoff_tool_choice(
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    *,
    has_planning_intent: bool,
    interactive: bool = False,
) -> str | None:
    # A turn that will create a different trip must still run the kickoff; otherwise the
    # creation policy silently replaces the workspace without asking anything.
    if active_trip.get("destination") and not (
        latest_user_starts_new_trip(messages)
        or latest_user_requests_different_trip(messages, active_trip)
    ):
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
    # Party composition is trip-specific: a saved family roster does not establish
    # who is joining this trip. Direct mode can skip the review only when the user
    # already supplied a usable party; interactive mode still promises one review.
    if interactive or not latest_user_has_explicit_party(messages):
        return "request_trip_input"
    return None


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

    if not latest_user_requests_different_trip(messages, active_trip):
        return None
    return "create_trip_plan"


def resolve_completion_policy(
    *,
    messages: Sequence[BaseMessage],
    active_trip: dict[str, Any],
    proposal_only: bool,
    has_planning_intent: bool,
    interactive_questions: bool = False,
) -> CompletionPolicyDecision:
    tool_phases = current_turn_tool_phases(messages)
    positions = _tool_call_positions(messages)
    latest_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    current_turn_names = {name for index, name in positions if index > latest_human}
    created_this_turn = "create_trip_plan" in current_turn_names
    updated_this_turn = "update_trip_plan" in current_turn_names
    core_gaps_for_planning_turn = (
        tuple(core_planning_completion_gaps(active_trip))
        if (
            not proposal_only
            and (created_this_turn or (has_planning_intent and updated_this_turn))
        )
        else ()
    )
    # Asking the review and then planning anyway would make it decoration, so the
    # turn stops at the question until the traveller answers or skips it.
    if not proposal_only and awaiting_trip_kickoff_answer(messages):
        return CompletionPolicyDecision(
            tool_phases=tool_phases,
            forced_tool=None,
            forced_reason="awaiting_kickoff_answer",
            awaiting_kickoff_answer=True,
        )
    if not proposal_only and tool_phases >= MAX_TOOL_PHASES_PER_TURN:
        # A broad multi-city research turn (e.g. two destinations plus "nearby
        # sites") can spend the whole budget on search before ever calling
        # update_trip_plan. Trapping the turn here left the trip with no
        # itinerary at all, narrated in chat but absent from every other pane.
        # Let the still-owed first save through before honoring the cap.
        current_updates = [
            index for index, name in positions
            if name == "update_trip_plan" and index > latest_human
        ]
        still_owes_first_save = (
            "create_trip_plan" in current_turn_names
            and not active_trip.get("day_wise_itinerary")
            and len(current_updates) < MAX_INITIAL_ITINERARY_UPDATES
        )
        if not still_owes_first_save and not (
            created_this_turn and core_gaps_for_planning_turn
        ):
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
    new_trip_flow = not created_this_turn and (
        latest_user_starts_new_trip(messages)
        or latest_user_requests_different_trip(messages, active_trip)
        or pending_trip_kickoff_answer(messages)
    )
    hotel_fallback_requirement = (
        None
        if proposal_only or creation_tool or new_trip_flow
        else trip_hotel_fallback_requirement(messages)
    )
    origin_requirement = (
        None
        if proposal_only or creation_tool or new_trip_flow or hotel_fallback_requirement
        else origin_correction_requirement(messages, active_trip)
    )
    update_requirement = (
        None
        if proposal_only or new_trip_flow or hotel_fallback_requirement or origin_requirement
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
    if (
        core_gaps_for_planning_turn
        and not hotel_fallback_requirement
        and not origin_requirement
        and not update_requirement
        and not hotel_search_requirement
    ):
        update_requirement = (
            "The planning turn cannot end because the saved trip still has core "
            "completion gaps: "
            + " ".join(core_gaps_for_planning_turn)
            + " Continue planning and call update_trip_plan with a complete corrected "
            "plan. Do not give a final response until these core gaps are resolved. "
            "Weather and other enrichment may remain deferred."
        )
    kickoff_tool = (
        None
        if proposal_only or update_requirement or hotel_search_requirement
        else trip_kickoff_tool_choice(
            messages,
            active_trip,
            has_planning_intent=has_planning_intent,
            interactive=interactive_questions,
        )
    )
    kickoff_answered = pending_trip_kickoff_answer(messages)
    # The kickoff outranks creation, otherwise switching destination would build the new
    # trip before asking anything. Creation resumes once the kickoff is answered.
    if kickoff_tool:
        creation_tool = None
    forced_tool = (
        creation_tool
        if creation_tool
        else "search_places_with_reviews"
        if hotel_fallback_requirement
        else "update_trip_plan"
        if origin_requirement
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
        else "origin_correction"
        if origin_requirement
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
        or origin_requirement
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
