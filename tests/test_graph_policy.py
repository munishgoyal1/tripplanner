from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from tripplanner.graph_policy import (
    MAX_INITIAL_ITINERARY_UPDATES,
    MAX_TOOL_PHASES_PER_TURN,
    resolve_completion_policy,
)
from tripplanner.tools.trip_validation import core_planning_completion_gaps


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


def test_unstructured_days_do_not_satisfy_the_initial_itinerary_gate() -> None:
    gaps = core_planning_completion_gaps({
        "destination": "Nashik",
        "day_wise_itinerary": [{"day": 1}],
    })

    assert len(gaps) == 1
    assert "full structured day_wise_itinerary" in gaps[0]


def test_the_phase_budget_ends_after_bounded_first_turn_save_attempts() -> None:
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

    assert decision.budget_exhausted
    assert decision.forced_tool is None
    assert decision.forced_reason == "tool_phase_budget"


def test_the_phase_budget_does_not_end_with_a_short_departure_buffer() -> None:
    current_turn: list[BaseMessage] = [
        HumanMessage(content="plan a trip to goa"),
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
        active_trip={
            "destination": "Goa",
            "travel_scope": "destination_only",
            "day_wise_itinerary": [
                {
                    "day": 4,
                    "stops": [
                        {
                            "name": "Brunch",
                            "kind": "meal",
                            "time": "12:00",
                            "duration_min": 60,
                        },
                        {
                            "name": "Flight: Goa to Bangalore",
                            "kind": "flight",
                            "time": "14:00",
                            "duration_min": 90,
                        },
                    ],
                }
            ],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is False
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    assert "leaves only 60 minutes" in (decision.requirement or "")


def test_the_phase_budget_does_not_end_with_an_intercity_continuity_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_turn: list[BaseMessage] = [
        HumanMessage(content="plan a Delhi, Agra, and Jaipur trip"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
        _tool_call("update_trip_plan", "update-1"),
        ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        _tool_call("update_trip_plan", "update-2"),
        ToolMessage(content="Trip plan updated.", tool_call_id="update-2"),
        *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 3),
    ]
    continuity_gap = (
        "Trident Jaipur is far from Trident Agra on Day 4, "
        "and no journey connects them."
    )
    monkeypatch.setattr(
        "tripplanner.graph_policy.core_planning_completion_gaps",
        lambda _plan: [continuity_gap],
    )

    decision = resolve_completion_policy(
        messages=current_turn,
        active_trip={
            "destination": "Delhi, Agra, Jaipur",
            "day_wise_itinerary": [{"day": 4, "stops": []}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is False
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    assert continuity_gap in (decision.requirement or "")


def test_the_phase_budget_does_not_end_with_a_hotel_only_day() -> None:
    current_turn: list[BaseMessage] = [
        HumanMessage(content="plan a seven-day Bali trip"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
        _tool_call("update_trip_plan", "update-1"),
        ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 2),
    ]
    decision = resolve_completion_policy(
        messages=current_turn,
        active_trip={
            "destination": "Bali",
            "origin": "Bali",
            "day_wise_itinerary": [{
                "day": 7,
                "stops": [{"name": "Maya Sanur Resort", "kind": "hotel"}],
            }],
            "selected_hotels": [{"name": "Maya Sanur Resort"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is False
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    assert "Day 7 has no planned places beyond the hotel" in (decision.requirement or "")


def test_the_phase_budget_does_not_end_with_advisor_flagged_sparse_days() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="plan a seven-day Mysore heritage trip"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 3),
            _tool_call("nearby_restaurants", "restaurants-1"),
            ToolMessage(content="Nearby restaurants", tool_call_id="restaurants-1"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        ],
        active_trip={
            "destination": "Mysore",
            "origin": "Mysore",
            "planning_recommendation": {
                "target_active_minutes_per_full_day": 360,
                "recommended_days": 7,
            },
            "preferences_snapshot": {"trip_style": "balanced"},
            "day_wise_itinerary": [
                {
                    "day": day,
                    "title": title,
                    "stops": [
                        {"name": "Radisson Blu Plaza Hotel Mysore", "kind": "hotel"},
                        {"name": first, "kind": "attraction", "duration_min": 90},
                        {"name": second, "kind": "attraction", "duration_min": 60},
                        {"name": "Radisson Blu Plaza Hotel Mysore", "kind": "hotel"},
                    ],
                }
                for day, title, first, second in (
                    (
                        2,
                        "Jaganmohan Palace and Devaraja Market",
                        "Jaganmohan Palace and Art Gallery",
                        "Devaraja Market",
                    ),
                    (
                        3,
                        "Chamundi Hill and St. Philomena's Cathedral",
                        "Chamundi Hill and Temple",
                        "St. Philomena's Cathedral",
                    ),
                    (
                        4,
                        "Lalitha Mahal and Rail Museum",
                        "Lalitha Mahal Palace",
                        "Mysore Rail Museum",
                    ),
                )
            ],
            "selected_hotels": [{"name": "Radisson Blu Plaza Hotel Mysore"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted is False
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    requirement = decision.requirement or ""
    assert "Day 2 has about 150 planned minutes" in requirement
    assert "Day 3 has about 150 planned minutes" in requirement
    assert "Day 4 has about 150 planned minutes" in requirement
    assert "meaningful nearby stops" in requirement


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

    # Switching destination starts the kickoff rather than completing Paris; the new
    # trip is created after the kickoff is answered.
    assert decision.forced_tool == "get_travel_preferences"
    assert decision.forced_reason == "trip_kickoff"


def test_unphrased_planning_request_leaves_creation_to_the_model() -> None:
    decision = resolve_completion_policy(
        messages=[HumanMessage(content="plan a 6 day leh ladakh trip")],
        active_trip={
            "destination": "Dehradun",
            "day_wise_itinerary": [{"day": 1, "stops": [{"name": "Clock Tower"}]}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool is None
    assert decision.forced_reason == "model_choice"


def test_answered_optional_review_can_force_creation() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="plan a 6 day leh ladakh trip"),
            _tool_call("request_trip_input", "kickoff"),
            ToolMessage(content="ok", tool_call_id="kickoff"),
            HumanMessage(content="Use these and continue"),
        ],
        active_trip={"destination": "Dehradun", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "create_trip_plan"


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


def test_missing_lodging_anchor_forces_hotel_research() -> None:
    decision = resolve_completion_policy(
        messages=[HumanMessage(content="Finish planning my Udaipur trip")],
        active_trip={
            "destination": "Udaipur",
            "travel_scope": "destination_only",
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [{"name": "City Palace", "kind": "attraction"}],
                },
                {
                    "day": 2,
                    "stops": [{"name": "Jag Mandir", "kind": "attraction"}],
                },
            ],
            "selected_hotels": [{"name": "Trident Udaipur"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "search_hotels"
    assert decision.forced_reason == "missing_concrete_hotel"
    assert "lodging anchor" in (decision.requirement or "")


def test_prior_turn_hotel_search_does_not_retire_stay_repair() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan my Udaipur trip"),
            _tool_call("search_hotels", "hotel-old"),
            ToolMessage(content="No hotels found for Udaipur.", tool_call_id="hotel-old"),
            HumanMessage(content="Finish the stay planning"),
        ],
        active_trip={
            "destination": "Udaipur",
            "travel_scope": "destination_only",
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
                },
                {
                    "day": 2,
                    "stops": [{"name": "City Palace", "kind": "attraction"}],
                },
            ],
            "selected_hotels": [],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "search_hotels"
    assert decision.forced_reason == "missing_concrete_hotel"


def test_resumed_hotel_gap_ignores_prior_turn_hotel_search() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan my Paris stay"),
            _tool_call("search_hotels", "hotel-old"),
            ToolMessage(
                content='[{"name": "Hotel Le Six"}]',
                tool_call_id="hotel-old",
            ),
            HumanMessage(content="Finish the incomplete itinerary"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
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

    assert decision.forced_tool == "search_hotels"
    assert decision.forced_reason == "missing_concrete_hotel"


def test_resumed_hotel_gap_does_not_fallback_from_prior_turn_failure() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan my Paris stay"),
            _tool_call("search_hotels", "hotel-old"),
            ToolMessage(
                content="No hotels found for Paris.",
                tool_call_id="hotel-old",
            ),
            HumanMessage(content="Finish the incomplete itinerary"),
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

    assert decision.forced_tool == "search_hotels"
    assert decision.forced_reason == "missing_concrete_hotel"


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


def test_phase_budget_stops_after_bounded_initial_save_repairs() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="Plan a Paris stay"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
    ]
    for attempt in range(MAX_INITIAL_ITINERARY_UPDATES):
        call_id = f"update-{attempt}"
        messages.extend([
            _tool_call("update_trip_plan", call_id),
            ToolMessage(content="Error: invalid journey timing", tool_call_id=call_id),
        ])
    messages.extend(
        _tool_phases(MAX_TOOL_PHASES_PER_TURN - 1 - MAX_INITIAL_ITINERARY_UPDATES)
    )

    decision = resolve_completion_policy(
        messages=messages,
        active_trip={"destination": "Paris", "day_wise_itinerary": []},
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.tool_phases == MAX_TOOL_PHASES_PER_TURN
    assert decision.budget_exhausted
    assert decision.forced_tool is None
    assert decision.forced_reason == "tool_phase_budget"


def test_first_turn_continues_for_requested_budget_cost_evidence() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a one-day Paris stay under EUR 500"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Musee de l'Orangerie", "kind": "attraction"},
                    {"name": "Bouillon Chartier", "kind": "meal"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
            "budget": {"amount": 500, "currency": "EUR", "owner": "user"},
            "total_cost": 0,
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "update_trip_plan"
    assert "positive cost evidence" in (decision.requirement or "")


def test_first_turn_provider_failure_uses_hotel_fallback_after_phase_budget() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Create a separate new Paris trip"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            _tool_call("search_hotels", "hotel-1"),
            ToolMessage(content="No hotels found for Paris.", tool_call_id="hotel-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 2),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
            "selected_hotels": [],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "search_places_with_reviews"
    assert decision.forced_reason == "hotel_provider_fallback"


def test_first_turn_persists_six_day_hotel_fallback_after_phase_budget() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="Plan a six-day New York trip"),
        _tool_call("create_trip_plan", "create-1"),
        ToolMessage(content="Created", tool_call_id="create-1"),
        _tool_call("search_hotels", "hotel-1"),
        ToolMessage(content="No hotels found for New York.", tool_call_id="hotel-1"),
        *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 3),
        _tool_call("search_places_with_reviews", "places-1"),
        ToolMessage(content="The Wallace Hotel", tool_call_id="places-1"),
    ]
    decision = resolve_completion_policy(
        messages=messages,
        active_trip={
            "destination": "New York",
            "origin": "Delhi",
            "day_wise_itinerary": [
                {
                    "day": day,
                    "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
                }
                for day in range(1, 7)
            ],
            "selected_hotels": [],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.tool_phases == MAX_TOOL_PHASES_PER_TURN
    assert not decision.budget_exhausted
    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    assert "Research is complete but has not been persisted" in (decision.requirement or "")


def test_phase_budget_cannot_end_first_turn_with_generic_city_hotel() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a Kerala trip"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={
            "destination": "Kochi, Kerala",
            "origin": "Kochi",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel in Kochi", "kind": "hotel"},
                    {"name": "Fort Kochi", "kind": "attraction"},
                    {"name": "Kashi Art Cafe", "kind": "meal"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel in Kochi"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "search_hotels"
    assert decision.forced_reason == "missing_concrete_hotel"
    assert "no bookable property" in (decision.requirement or "")


def test_first_turn_researches_missing_restaurants_before_completion_repair() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a Paris stay"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Musee de l'Orangerie", "kind": "attraction"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "nearby_restaurants"
    assert decision.forced_reason == "missing_named_restaurant"
    assert "multiple activities but no named restaurant" in (decision.requirement or "")


def test_first_turn_researches_restaurants_when_meal_is_a_placeholder() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a Paris stay"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Dinner TBD", "kind": "meal"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "nearby_restaurants"
    assert decision.forced_reason == "missing_named_restaurant"
    assert "meal placeholder instead of a named restaurant" in (decision.requirement or "")


def test_first_turn_persists_named_restaurants_after_research() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a Paris stay"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
            _tool_call("nearby_restaurants", "restaurants-1"),
            ToolMessage(content="Bouillon Chartier", tool_call_id="restaurants-1"),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Musee de l'Orangerie", "kind": "attraction"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "update_trip_plan"
    assert decision.forced_reason == "persist_or_repair_plan"
    assert "Research is complete but has not been persisted" in (decision.requirement or "")


def test_restaurant_research_continues_past_the_first_turn_phase_budget() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a Paris stay"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 2),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Musee de l'Orangerie", "kind": "attraction"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "nearby_restaurants"
    assert decision.forced_reason == "missing_named_restaurant"


def test_planning_resume_cannot_end_without_arrival_journey() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Finish planning my Bali trip"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
        ],
        active_trip={
            "destination": "Bali",
            "origin": "Bangalore",
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                        {"name": "Sambal Shrimp", "kind": "meal"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                        {"name": "Seminyak Beach", "kind": "attraction"},
                    ],
                },
            ],
            "selected_hotels": [{"name": "Villa Kayu Raja"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.forced_tool == "update_trip_plan"
    assert "Bangalore to Bali" in (decision.requirement or "")


def test_phase_budget_cannot_end_planning_resume_without_departure_journey() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Finish planning my Bali trip"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={
            "destination": "Bali",
            "origin": "Bangalore",
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {
                            "name": "Flight Bangalore to Bali",
                            "kind": "flight",
                        },
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                        {"name": "Seminyak Beach", "kind": "attraction"},
                    ],
                },
            ],
            "selected_hotels": [{"name": "Villa Kayu Raja"}],
            "selected_flights": [{"airline": "Air India"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "update_trip_plan"
    assert "Bali back to Bangalore" in (decision.requirement or "")


def test_phase_budget_cannot_end_planning_resume_without_outbound_journey() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Finish planning my Bali trip"),
            _tool_call("update_trip_plan", "update-1"),
            ToolMessage(content="Trip plan updated.", tool_call_id="update-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={
            "destination": "Bali",
            "origin": "Bangalore",
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                        {"name": "Sambal Shrimp", "kind": "meal"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Villa Kayu Raja", "kind": "hotel"},
                        {
                            "name": "Flight Bali to Bangalore",
                            "kind": "flight",
                        },
                    ],
                },
            ],
            "selected_hotels": [{"name": "Villa Kayu Raja"}],
            "selected_flights": [{"airline": "Air India"}],
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert not decision.budget_exhausted
    assert decision.forced_tool == "update_trip_plan"
    assert "no matching outbound" in (decision.requirement or "")


def test_weather_can_remain_deferred_when_first_turn_core_plan_is_complete() -> None:
    decision = resolve_completion_policy(
        messages=[
            HumanMessage(content="Plan a one-day Paris stay"),
            _tool_call("create_trip_plan", "create-1"),
            ToolMessage(content="Created", tool_call_id="create-1"),
            *_tool_phases(MAX_TOOL_PHASES_PER_TURN - 1),
        ],
        active_trip={
            "destination": "Paris",
            "origin": "Paris",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel Le Six", "kind": "hotel"},
                    {"name": "Louvre Museum", "kind": "attraction"},
                    {"name": "Musee de l'Orangerie", "kind": "attraction"},
                    {"name": "Bouillon Chartier", "kind": "meal"},
                ],
            }],
            "selected_hotels": [{"name": "Hotel Le Six"}],
            "total_cost": 420,
            "weather": {},
        },
        proposal_only=False,
        has_planning_intent=True,
    )

    assert decision.budget_exhausted
    assert decision.forced_tool is None


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


def test_a_kickoff_asked_last_turn_is_recognised_this_turn() -> None:
    """Tool messages do not survive a turn, so the answer must read what was saved.

    In interactive mode the kickoff is asked in one turn and answered in the
    next. Without the saved marker the answer is never recognised and the agent
    asks again forever.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from tripplanner import graph_policy as gp

    asked = AIMessage(
        content="Does this look right?",
        additional_kwargs={gp.RAN_TOOLS_KEY: ["request_trip_input"]},
    )
    messages = [HumanMessage(content="Plan a 3 day Goa trip"), asked, HumanMessage(content="Yes")]

    assert gp.pending_trip_kickoff_answer(messages)


def test_a_conversation_that_never_asked_has_no_answer_pending() -> None:
    """Only a real kickoff counts, or any second turn would look like an answer."""
    from langchain_core.messages import AIMessage, HumanMessage

    from tripplanner import graph_policy as gp

    messages = [
        HumanMessage(content="Plan a 3 day Goa trip"),
        AIMessage(content="Sure, tell me more."),
        HumanMessage(content="Yes"),
    ]

    assert not gp.pending_trip_kickoff_answer(messages)


def test_a_saved_turn_carries_its_tools_back(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """chat_store is the only thing that can carry the marker across a turn."""
    from langchain_core.messages import AIMessage, HumanMessage

    from tripplanner.web import chat_store

    rows = chat_store._serialize(
        [
            HumanMessage(content="Plan a 3 day Goa trip"),
            AIMessage(
                content="Does this look right?",
                additional_kwargs={chat_store._RAN_TOOLS: ["request_trip_input"]},
            ),
        ]
    )
    restored = chat_store._deserialize(rows)

    assert rows[1][chat_store._RAN_TOOLS] == ["request_trip_input"]
    assert restored[1].additional_kwargs[chat_store._RAN_TOOLS] == ["request_trip_input"]
    # Never as tool_calls: the provider would demand results this history lacks.
    assert not getattr(restored[1], "tool_calls", None)
