from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from tripplanner.graph_policy import trip_request_text
from tripplanner.tools.request_asks import unmet_asks
from tripplanner.tools.trip_validation import (
    core_planning_completion_gaps,
    implausible_drive_warnings,
    summary_drift_warnings,
)

_PLAN = {
    "destination": "Uttarakhand",
    "day_wise_itinerary": [
        {"day": 1, "title": "Haridwar", "summary": "Ganga Aarti at Har Ki Pauri.",
         "stops": [{"name": "Har Ki Pauri", "kind": "attraction"}]},
        {"day": 2, "title": "Yamunotri and Gangotri", "summary": "Temples.",
         "stops": [{"name": "Yamunotri Temple", "kind": "attraction"},
                   {"name": "Gangotri Temple", "kind": "attraction"}]},
    ],
}


def test_explicit_asks_must_be_met_or_dropped_with_a_reason() -> None:
    request = (
        "Plan a trip to Haridwar and the Char Dham route from Delhi. Include the flights. "
        "Verify current official entry requirements before booking."
    )

    gaps = unmet_asks(request, _PLAN)

    assert len(gaps) == 3
    assert "include the flights" in gaps[0]
    assert "entry requirements" in gaps[1]
    assert gaps[2].startswith("The request named Kedarnath, Badrinath,")

    dropped = {
        **_PLAN,
        "visa": {"status": "visa_free"},
        "selected_flights": [{"airline": "IndiGo"}],
        "dropped_requests": [
            {"ask": "Kedarnath and Badrinath", "reason": "not reachable in two days"}
        ],
    }
    assert unmet_asks(request, dropped) == []


def test_regions_and_trip_wording_are_not_treated_as_missing_places() -> None:
    plan = {"day_wise_itinerary": [{"day": 1, "stops": [{"name": "Milan Cathedral"}]}]}

    assert unmet_asks("Plan a trip to Milan and northern Italy from Mumbai.", plan) == []
    assert unmet_asks("Plan a 3 day Italy covering Milan trip from Delhi.", plan) == []


def test_request_text_starts_at_the_turn_that_created_the_trip() -> None:
    messages = [
        HumanMessage("Plan Goa for us"),
        AIMessage("", tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "old"}]),
        HumanMessage("New trip: Paris, include the flights"),
        AIMessage("", tool_calls=[{"name": "create_trip_plan", "args": {}, "id": "new"}]),
        HumanMessage("Make it 2 adults"),
    ]
    assert trip_request_text(messages) == "New trip: Paris, include the flights\nMake it 2 adults"

    fresh = [HumanMessage("Paris, include the flights"), HumanMessage("2 adults")]
    assert trip_request_text(fresh) == "Paris, include the flights\n2 adults"


def test_impossible_drives_and_drifting_summaries_block_completion() -> None:
    plan = {
        "destination": "Rajasthan",
        "day_wise_itinerary": [
            {"day": 1, "date": "2027-02-02", "summary": "Drive, then Hawa Mahal.", "stops": [
                {"name": "Drive: Mumbai to Jaipur", "kind": "transport",
                 "distance_km": 1160, "duration_min": 660},
            ]},
            {"day": 2, "date": "2027-02-03", "summary": "Pink City.", "stops": [
                {"name": "Hawa Mahal", "kind": "attraction"},
                {"name": "Drive: Jaipur to Ajmer", "kind": "transport",
                 "distance_km": 130, "duration_min": 150},
            ]},
        ],
    }

    drives = implausible_drive_warnings(plan)
    summaries = summary_drift_warnings(plan)

    assert drives == [
        "Day 1 schedules Drive: Mumbai to Jaipur (1160 km) in 660 minutes, 105 km/h door to "
        "door; replace it with a train or flight, or split it with an overnight stop."
    ]
    assert summaries == [
        "Day 1's summary names Hawa Mahal, which is planned on Day 2. Rewrite the summary "
        "from that day's own stops."
    ]
    gaps = core_planning_completion_gaps(plan)
    assert drives[0] in gaps and summaries[0] in gaps


def test_a_choice_between_places_is_met_by_either() -> None:
    plan = {"day_wise_itinerary": [{"day": 1, "stops": [{"name": "Railay Beach, Krabi"}]}]}

    assert unmet_asks("Plan a trip to Bangkok and Phuket or Krabi from Delhi.", {
        "day_wise_itinerary": plan["day_wise_itinerary"] + [
            {"day": 2, "stops": [{"name": "Grand Palace, Bangkok"}]}
        ]
    }) == []
