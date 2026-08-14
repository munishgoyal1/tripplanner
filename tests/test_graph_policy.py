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


def test_a_new_request_does_not_inherit_the_previous_turns_research() -> None:
    """The reported defect: asking for a Goa trip answered the earlier Paris
    flight question and saved that research instead."""
    answered_turn: list[BaseMessage] = [
        HumanMessage(content="show me the flight segments and layovers"),
        _tool_call("search_flights", "flight-1"),
        ToolMessage(content="segments...", tool_call_id="flight-1"),
        AIMessage(content="Here are your Paris flight segments."),
    ]
    decision = resolve_completion_policy(
        messages=[*answered_turn, HumanMessage(content="plan a trip to goa for 7 days")],
        active_trip={"destination": "Paris", "day_wise_itinerary": [{"day": 1, "stops": []}]},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.requirement is None or "not been persisted" not in decision.requirement


def test_research_in_the_current_turn_must_still_be_persisted() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="add some museums"),
            _tool_call("search_activities", "act-1"),
            ToolMessage(content="museums...", tool_call_id="act-1"),
        ],
        active_trip={"destination": "Paris", "day_wise_itinerary": [{"day": 1, "stops": []}]},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.requirement is not None
    assert "not been persisted" in decision.requirement


def test_a_new_trip_must_still_save_an_itinerary_late_in_a_conversation() -> None:
    """The reported defect: a Nashik trip was narrated but saved with no days,
    because earlier turns had already spent the itinerary-save budget."""
    earlier: list[BaseMessage] = []
    for turn in range(3):
        earlier += [
            HumanMessage(content=f"earlier request {turn}"),
            _tool_call("update_trip_plan", f"old-{turn}"),
            ToolMessage(content="Trip plan updated.", tool_call_id=f"old-{turn}"),
        ]
    decision = resolve_completion_policy(
        messages=[
            *earlier,
            HumanMessage(content="plan a trip to nashik"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
        ],
        active_trip={"destination": "Nashik", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.requirement is not None
    assert "no itinerary" in decision.requirement


def test_a_broad_new_trip_must_still_save_before_the_phase_budget_traps_it() -> None:
    """The reported defect: a Varanasi/Ayodhya religious-circuit request spent
    the whole ten-phase research budget across two cities and never reached
    update_trip_plan, so the turn ended with a narrated but unsaved itinerary."""
    current_turn: list[BaseMessage] = [
        HumanMessage(content="plan a varanasi and ayodhya circuit trip"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
        *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
    ]
    decision = resolve_completion_policy(
        messages=current_turn,
        active_trip={"destination": "Varanasi", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is False
    assert decision.forced_tool == "update_trip_plan"
    assert decision.requirement is not None
    assert "no itinerary" in decision.requirement


def test_the_phase_budget_still_traps_a_turn_once_the_first_save_was_attempted() -> None:
    current_turn: list[BaseMessage] = [
        HumanMessage(content="plan a varanasi and ayodhya circuit trip"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
        _tool_call("update_trip_plan", "update-1"),
        ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        _tool_call("update_trip_plan", "update-2"),
        ToolMessage(content="Trip plan updated.", tool_call_id="update-2"),
        *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 3),
    ]
    decision = resolve_completion_policy(
        messages=current_turn,
        active_trip={"destination": "Varanasi", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is True
    assert decision.forced_tool is None


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
