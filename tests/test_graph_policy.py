from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from tripplanner.graph_policy import (
    MAX_TOOL_PHASES_PER_TURN,
    resolve_completion_policy,
)


def _tool_call(name: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": call_id}],
    )


def _tool_phases(count: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for phase in range(count):
        call_id = f"phase-{phase}"
        messages.extend([
            _tool_call("get_trip_plan", call_id),
            ToolMessage(content="Loaded", tool_call_id=call_id),
        ])
    return messages


def test_new_trip_kickoff_preempts_incomplete_active_trip() -> None:
    decision = resolve_completion_policy(
        messages=[HumanMessage(content="Create a separate new Hawaii trip")],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "get_travel_preferences"
    assert decision.forced_reason == "trip_kickoff"


def test_explicit_destination_switch_preempts_old_trip_completion() -> None:
    decision = resolve_completion_policy(
        messages=[HumanMessage(content="Plan a trip to Hawaii")],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "create_trip_plan"
    assert decision.forced_reason == "new_trip_creation"


def test_answered_kickoff_preempts_old_trip_completion() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Create a separate new Hawaii trip"),
            _tool_call("request_trip_input", "kickoff-1"),
            ToolMessage(content="Review choices", tool_call_id="kickoff-1"),
            HumanMessage(content="Use these choices and build it"),
        ],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=False,
    )

    assert decision.forced_tool == "create_trip_plan"
    assert decision.forced_reason == "kickoff_answered"


def test_hotel_provider_fallback_preempts_enrichment_persistence() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Improve my Paris itinerary"),
            _tool_call("search_hotels", "hotel-1"),
            ToolMessage(content="No hotels found for Paris.", tool_call_id="hotel-1"),
        ],
        active_trip={
            "destination": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
            "selected_hotels": [],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "search_places_with_reviews"
    assert decision.forced_reason == "hotel_provider_fallback"


def test_tool_phase_budget_preempts_every_completion_gate() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a trip to Hawaii"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN),
        ],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.tool_phases == MAX_TOOL_PHASES_PER_TURN
    assert decision.budget_exhausted
    assert decision.forced_tool is None
    assert decision.forced_reason == "tool_phase_budget"


def test_one_remaining_tool_phase_still_allows_completion_repair() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Improve this itinerary"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.tool_phases == MAX_TOOL_PHASES_PER_TURN - 1
    assert not decision.budget_exhausted
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"


def test_origin_correction_forces_persistence_even_without_planning_intent() -> None:
    decision = resolve_completion_policy(
        messages=[HumanMessage(content="My origin city is Bangalore.")],
        active_trip={"destination": "Goa", "origin": "Delhi", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=False,
    )

    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "origin_correction"


def test_proposal_only_ignores_tool_phase_budget_and_completion_gates() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Review this itinerary"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN),
        ],
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=True,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool is None
    assert decision.forced_reason == "model_choice"
