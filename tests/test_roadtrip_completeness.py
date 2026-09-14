import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tripplanner.graph_policy import resolve_completion_policy
from tripplanner.hotel_research import unresearched_hotel_cities
from tripplanner.tools import trip_rebalance
from tripplanner.tools.trip_validation import _ground_leg_distance_warnings
from tripplanner.web.day_journey import plan_day_journeys
from tripplanner.web.map_pins import _resolve_road_circuit_pin_ids


def test_hotel_search_must_cover_each_overnight_city():
    plan = {"day_wise_itinerary": [{"day": 1, "stops": [
        {"name": f"{city} hotel TBD", "kind": "hotel"}
        for city in ["Madurai", "Rameshwaram", "Kanyakumari"]
    ]}]}
    messages = [HumanMessage(content="Plan the road trip"), AIMessage(content="", tool_calls=[
        {"name": "search_hotels", "args": {"city": "Madurai"}, "id": "hotels"},
    ])]
    assert unresearched_hotel_cities(messages, plan) == ["Kanyakumari", "Rameshwaram"]


def test_property_candidates_force_selection_without_requiring_room_rates():
    messages = [HumanMessage(content="Finish this road trip"), AIMessage(content="", tool_calls=[
        {"name": "search_hotels", "args": {"city": "Madurai"}, "id": "hotels"},
    ]), ToolMessage(tool_call_id="hotels", content=json.dumps({
        "hotel_research": {"city": "Madurai", "reason": "rate_and_availability_unverified"},
        "candidates": [{"name": "Heritage Madurai", "place_id": "property"}],
    }))]
    decision = resolve_completion_policy(
        messages=messages, active_trip={"destination": "Madurai", "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Madurai hotel TBD", "kind": "hotel"}]},
        ]}, proposal_only=False, has_planning_intent=True,
    )
    assert decision.forced_tool == "update_trip_plan"
    assert "availability_status=unverified" in decision.requirement
    assert "selected_hotels" in decision.requirement


def test_long_explicit_drive_is_not_rejected_as_unsupported_local_transport():
    stop = {"kind": "transport", "name": "Drive: Bangalore to Madurai", "distance_km": 450}
    assert _ground_leg_distance_warnings({"day_wise_itinerary": [{"stops": [stop]}]}) == []
    stop["name"] = "Walk: Bangalore to Madurai"
    assert _ground_leg_distance_warnings({"day_wise_itinerary": [{"stops": [stop]}]})


def test_road_circuit_ends_at_city_when_hotel_is_unresolved():
    pins = {name: {"id": name, "name": name, "kind": "origin"} for name in [
        "Bangalore", "Madurai", "Temple",
    ]}
    rows = [
        {"name": "Drive: Bangalore to Madurai", "kind": "transport", "mode": "Drive"},
        {"name": "Madurai hotel TBD", "kind": "hotel", "mode": None},
        {"name": "Temple", "kind": "attraction", "mode": None},
    ]
    def resolve(name, kind=""):
        return pins.get(name)

    assert _resolve_road_circuit_pin_ids(rows, 0, resolve, []) == ["Bangalore", "Madurai"]


def test_outbound_and_return_drives_survive_unresolved_stays():
    pins = {name: {"id": name, "name": name, "kind": "origin"} for name in [
        "Bangalore", "Madurai",
    ]}
    entries = [{"day": 1, "stops": [
        {"name": "Drive: Bangalore to Madurai", "kind": "transport"},
        {"name": "Madurai hotel TBD", "kind": "hotel"},
    ]}, {"day": 8, "stops": [
        {"name": "Madurai hotel TBD", "kind": "hotel"},
        {"name": "Drive: Madurai to Bangalore", "kind": "transport"},
    ]}]
    journeys, _ = plan_day_journeys(entries, resolve_pin=lambda name, kind="": pins.get(name))
    assert journeys[1].intercity_edges == {("Bangalore", "Madurai"): "Drive"}
    assert journeys[8].intercity_edges == {("Madurai", "Bangalore"): "Drive"}


def test_rebalance_does_not_move_attractions_between_overnight_cities():
    plan = {"day_wise_itinerary": [
        {"day": 3, "city": "Rameshwaram", "stops": []},
        {"day": 6, "city": "Kanyakumari", "stops": []},
    ]}
    assert trip_rebalance._place(plan, {
        "name": "Vivekananda Rock Memorial", "kind": "attraction",
    }, 6, 3) is None
