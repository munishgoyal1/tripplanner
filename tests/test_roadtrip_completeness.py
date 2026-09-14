import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tripplanner.graph_policy import resolve_completion_policy, saved_itinerary_reply
from tripplanner.hotel_research import unresearched_hotel_cities
from tripplanner.tools import trip_rebalance
from tripplanner.tools.hotel_search import _city_in_address
from tripplanner.tools.itinerary_edit import _restore_undeclared_legs, _settle_plan_legs
from tripplanner.tools.trip_guard import validate_plan
from tripplanner.tools.trip_validation import _ground_leg_distance_warnings
from tripplanner.web.day_journey import plan_day_journeys
from tripplanner.web.map_pins import (
    _hotel_address_matches_context,
    _provider_name_matches,
    _resolve_road_circuit_pin_ids,
)


def test_hotel_search_must_cover_each_overnight_city():
    plan = {"day_wise_itinerary": [{"day": 1, "stops": [
        {"name": f"{city} hotel TBD", "kind": "hotel"}
        for city in ["Madurai", "Rameshwaram", "Kanyakumari"]
    ]}]}
    messages = [HumanMessage(content="Plan the road trip"), AIMessage(content="", tool_calls=[
        {"name": "search_hotels", "args": {"city": "Madurai"}, "id": "hotels"},
    ])]
    assert unresearched_hotel_cities(messages, plan) == ["Kanyakumari", "Rameshwaram"]


def test_hotel_city_matching_accepts_known_spellings_but_not_other_cities():
    assert _city_in_address("Rameshwaram", "Temple Road, Rameswaram, Tamil Nadu")
    assert _city_in_address("Bangalore", "MG Road, Bengaluru, Karnataka")
    assert _city_in_address("Kanyakumari", "Beach Road, Kanniyakumari, Tamil Nadu")
    assert not _city_in_address("Rameshwaram", "Beach Road, Kanniyakumari, Tamil Nadu")
    assert not _city_in_address("Goa", "Hotel in Goalpara, Assam")


def test_map_accepts_bangalore_and_hotel_address_city_aliases():
    assert _provider_name_matches("Bangalore", "Bengaluru")
    assert _hotel_address_matches_context(
        {"address": "Railway Feeder Rd, Rameswaram, Tamil Nadu"}, "Rameshwaram", "Madurai",
    )
    assert _hotel_address_matches_context(
        {"address": "E Car St, Kanniyakumari, Tamil Nadu"}, "Kanyakumari", "Madurai",
    )
    assert not _hotel_address_matches_context(
        {"address": "E Car St, Kanniyakumari, Tamil Nadu"}, "Rameshwaram", "Madurai",
    )


def test_home_arrival_reuses_city_map_anchor_without_geocoding_home_label(monkeypatch):
    from tripplanner.web import map_pins

    lookups = []
    def details(name, context, **kwargs):
        lookups.append(name)
        return {"name": "Bengaluru", "lat": 12.97, "lng": 77.59} if name == "Bangalore" else {}

    monkeypatch.setattr(map_pins.places_cache, "get_details", details)
    monkeypatch.setattr(map_pins.places_cache, "get_photos", lambda *args, **kwargs: [])
    unmapped = []
    pins = map_pins._map_pins({"origin": "Bangalore", "destination": "Madurai",
        "day_wise_itinerary": [{"day": 8, "stops": [{
            "name": "Bangalore home", "kind": "other", "time": "17:30",
        }]}]}, "Madurai", unmapped)
    assert any(pin["name"] == "Bangalore" for pin in pins)
    assert "Bangalore home" not in lookups
    assert not any(row["name"] == "Bangalore home" for row in unmapped)


def test_hotel_alias_search_retires_the_same_city_gate():
    messages = [HumanMessage(content="Repair this road trip"), AIMessage(content="", tool_calls=[
        {"name": "search_hotels", "args": {"city": "Rameswaram"}, "id": "hotels"},
    ]), ToolMessage(tool_call_id="hotels", content=json.dumps({
        "hotel_research": {"city": "Rameswaram", "reason": "rate_and_availability_unverified"},
        "candidates": [{"name": "Hotel Rameswaram Grand", "place_id": "property"}],
    }))]
    plan = {"destination": "Rameshwaram", "day_wise_itinerary": [
        {"day": 1, "stops": [{"name": "Rameshwaram hotel TBD", "kind": "hotel"}]},
    ]}
    assert unresearched_hotel_cities(messages, plan) == []
    decision = resolve_completion_policy(messages=messages, active_trip=plan,
                                         proposal_only=False, has_planning_intent=True)
    assert decision.forced_tool == "update_trip_plan"


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


def test_rejected_itinerary_keeps_retry_instructions_ahead_of_hotel_selection():
    messages = [HumanMessage(content="Finish this road trip")]
    for name, args, result in [
        ("search_hotels", {"city": "Madurai"}, json.dumps({
            "hotel_research": {"city": "Madurai", "reason": "rate_and_availability_unverified"},
            "candidates": [{"name": "Heritage Madurai", "place_id": "property"}],
        })),
        ("update_trip_plan", {}, "Error: Day 2 lunch must start at 13:15 or later"),
    ]:
        messages.extend([
            AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}]),
            ToolMessage(tool_call_id=name, content=result),
        ])
    decision = resolve_completion_policy(
        messages=messages, active_trip={"destination": "Madurai", "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Madurai hotel TBD", "kind": "hotel"}]},
        ]}, proposal_only=False, has_planning_intent=True,
    )
    assert decision.forced_tool == "update_trip_plan"
    assert "13:15" in decision.requirement
    assert "full itinerary" in decision.requirement


def test_stopped_reply_contains_all_saved_days_and_missing_coverage():
    reply = saved_itinerary_reply({
        "departure_date": "2026-10-12", "return_date": "2026-10-19",
        "day_wise_itinerary": [
            {"day": day, "stops": [{"name": f"Saved stay {day}", "kind": "hotel"}]}
            for day in [7, 3]
        ],
    }, ["Room availability unverified"])
    assert reply.index("Day 3") < reply.index("Day 7")
    assert "Saved stay 3" in reply and "Saved stay 7" in reply
    assert "6 days missing" in reply
    assert "Room availability unverified" in reply
    assert "no itinerary work is continuing" in reply


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


def test_timing_settlement_keeps_departure_hotel_before_drive():
    stops = [
        {"name": "Madurai Hotel", "kind": "hotel", "time": "07:30"},
        {"name": "Drive: Madurai to Rameshwaram", "kind": "transport", "time": "08:15", "duration_min": 240},
        {"name": "Rameshwaram Hotel", "kind": "hotel", "time": "12:45"},
    ]
    plan = {"day_wise_itinerary": [{"day": 3, "stops": stops}]}
    assert _settle_plan_legs(plan) == []
    assert plan["day_wise_itinerary"][0]["stops"][0]["name"] == "Madurai Hotel"


def test_return_drive_keeps_home_arrival_after_journey():
    stops = [
        {"name": "Madurai Hotel", "kind": "hotel", "time": "06:00"},
        {"name": "Drive: Madurai to Bangalore", "kind": "transport", "time": "07:00", "duration_min": 540},
        {"name": "Home arrival in Bangalore", "kind": "other", "time": "16:30"},
    ]
    plan = {"origin": "Bangalore", "destination": "Madurai",
            "day_wise_itinerary": [{"day": 1, "stops": [{
                "name": "Drive: Bangalore to Madurai", "kind": "transport", "time": "07:00",
            }]}, {"day": 8, "stops": stops}]}
    assert _settle_plan_legs(plan) == []
    assert plan["day_wise_itinerary"][-1]["stops"][-1]["name"] == "Home arrival in Bangalore"
    assert not [v for v in validate_plan(plan) if v.code in {"I1", "I2", "I5"}]


def test_obsolete_alternative_leg_is_not_restored_over_chosen_route():
    before = {"day_wise_itinerary": [{"day": 1, "stops": [{
        "name": "Drive: Madurai or Kodaikanal to Bangalore", "kind": "transport",
    }]}]}
    after = {"day_wise_itinerary": [{"day": 1, "stops": [{
        "name": "Home arrival in Bangalore", "kind": "other",
    }]}]}
    assert _restore_undeclared_legs(before, after, set()) == []
    assert len(after["day_wise_itinerary"][0]["stops"]) == 1
