"""Trip-view map assembly and focus tests."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.trip_view import SAMPLE_TRIP
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


def test_map_view_no_trip_disabled_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "")
    mv = trip_view.build_map_view(None)
    assert mv["enabled"] is False
    assert mv["pins"] == []
    assert mv["empty_message"]


def test_map_view_pins_have_coords_and_days(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "plan": "Check in to Taj Exotica Resort, relax on the beach"},
            {"day": 2, "plan": "Full-day Dudhsagar Falls Trek with packed lunch"},
        ],
    }
    mv = trip_view.build_map_view(trip)
    assert mv["enabled"] is True
    assert mv["available_days"] == [1, 2]
    assert mv["center"] is not None
    by_name = {p["name"]: p for p in mv["pins"]}
    # every pin carries coordinates
    assert all(p["lat"] is not None and p["lng"] is not None for p in mv["pins"])
    # prose day-matching assigns the right days
    assert by_name["Taj Exotica Resort"]["day"] == 1
    assert by_name["Taj Exotica Resort"]["selected"] is True


def test_map_view_day_bands_and_airport(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "plan": "Taj Exotica Resort arrival"},
            {"day": 2, "plan": "Dudhsagar Falls Trek"},
        ],
    }
    mv = trip_view.build_map_view(trip)
    days = {d["day"]: d for d in mv["days"]}
    assert set(days) == {1, 2}
    assert days[1]["color"] != days[2]["color"]
    assert days[1]["label"] == "Day 1"
    # each day includes route metrics (distance/time/mode)
    assert "route" in days[1]
    assert set(days[1]["route"]) == {
        "distance_km",
        "duration_min",
        "mode",
        "distance_display",
        "duration_display",
    }
    # the selected hotel/activity land in their day bands
    pin_ids = {p["name"]: p["id"] for p in mv["pins"]}
    assert pin_ids["Taj Exotica Resort"] in days[1]["pin_ids"]
    assert pin_ids["Dudhsagar Falls Trek"] in days[2]["pin_ids"]
    assert mv["airport"] is not None
    assert mv["airport"]["kind"] == "airport"


def test_map_view_route_stats_for_multi_stop_day(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Taj Exotica Resort"},
                    {"name": "Dudhsagar Falls Trek"},
                ],
            },
        ],
    }
    mv = trip_view.build_map_view(trip)
    day1 = next(d for d in mv["days"] if d["day"] == 1)
    assert day1["route"]["distance_km"] > 0
    assert day1["route"]["duration_min"] > 0
    assert set(day1["route"]["mode"].split(" + ")) <= {"Walk", "Taxi"}


def test_map_view_structured_stops_take_precedence(_map_geo: None) -> None:
    # No prose mention, but a structured stops list assigns the day.
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "plan": "free day", "stops": [{"name": "Dudhsagar Falls Trek"}]},
        ],
    }
    mv = trip_view.build_map_view(trip)
    by_name = {p["name"]: p for p in mv["pins"]}
    assert by_name["Dudhsagar Falls Trek"]["day"] == 1


def test_map_view_ignores_other_city_hotel_mentioned_in_structured_day_plan(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Trident Udaipur": (24.577, 73.683),
        "City Palace Udaipur": (24.576, 73.683),
        "Taj Hari Mahal Jodhpur": (26.269, 73.010),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": name,
            "lat": coords.get(name, (None, None))[0],
            "lng": coords.get(name, (None, None))[1],
        },
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Taj Hari Mahal Jodhpur"},
        ],
        "day_wise_itinerary": [{
            "day": 1,
            "plan": "Explore Udaipur before the later Jodhpur stay.",
            "stops": [
                {"name": "Trident Udaipur", "kind": "hotel"},
                {"name": "City Palace Udaipur", "kind": "attraction"},
                {"name": "Trident Udaipur", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    day = view["days"][0]
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Trident Udaipur",
        "City Palace Udaipur",
        "Trident Udaipur",
    ]
    jodhpur = next(pin for pin in view["pins"] if pin["name"] == "Taj Hari Mahal Jodhpur")
    assert jodhpur["day"] is None
    assert all(jodhpur["id"] not in (leg["from_pin_id"], leg["to_pin_id"]) for leg in day["legs"])


def test_map_view_selected_stay_anchors_route_when_no_match(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [{"day": 1, "plan": "nothing relevant here"}],
    }
    mv = trip_view.build_map_view(trip)
    sel = next(p for p in mv["pins"] if p["name"] == "Taj Exotica Resort")
    assert sel["day"] is None
    day1 = next(day for day in mv["days"] if day["day"] == 1)
    assert day1["pin_ids"][0] == day1["pin_ids"][-1] == sel["id"]
    assert sel["id"] not in mv["unscheduled_pin_ids"]


def test_map_view_selected_attraction_gets_fallback_day(_map_geo: None) -> None:
    # The itinerary doesn't mention the activity, but a SELECTED attraction
    # should still be clustered into a day (so it shows a bold numbered pin and
    # joins a route) rather than left as a quiet, dayless suggestion.
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "plan": "arrive"},
            {"day": 2, "plan": "relax"},
        ],
    }
    mv = trip_view.build_map_view(trip)
    by_name = {p["name"]: p for p in mv["pins"]}
    activity = by_name["Dudhsagar Falls Trek"]
    assert activity["selected"] is True
    assert activity["day"] in {1, 2}
    assert activity["id"] not in mv["unscheduled_pin_ids"]
    # Un-selected suggestions stay dayless (quiet dots).
    assert by_name["Fort Aguada"]["selected"] is False
    assert by_name["Fort Aguada"]["day"] is None


def test_map_view_includes_all_structured_day_stops_in_order(_map_geo: None) -> None:
    # Regression: map used to show only selected/suggested places, dropping
    # extra itinerary stops and producing an incomplete day circuit.
    trip = {
        **SAMPLE_TRIP,
        "destination": "Mumbai",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Gateway of India", "kind": "attraction"},
                    {"name": "Colaba Causeway", "kind": "attraction"},
                    {"name": "Marine Drive", "kind": "attraction"},
                ],
            }
        ],
    }
    mv = trip_view.build_map_view(trip)
    by_name = {p["name"]: p for p in mv["pins"]}

    # Every structured stop appears as a pin on the right day.
    for name in ("Gateway of India", "Colaba Causeway", "Marine Drive"):
        assert name in by_name
        assert by_name[name]["day"] == 1

    # The day route includes all three stops in itinerary order and returns
    # to the selected hotel for a complete daily circuit.
    day1 = next(d for d in mv["days"] if d["day"] == 1)
    id_by_name = {p["name"]: p["id"] for p in mv["pins"]}
    assert day1["pin_ids"][1:4] == [
        id_by_name["Gateway of India"],
        id_by_name["Colaba Causeway"],
        id_by_name["Marine Drive"],
    ]
    assert day1["pin_ids"][0] == id_by_name["Taj Exotica Resort"]
    assert day1["pin_ids"][-1] == id_by_name["Taj Exotica Resort"]


def test_map_view_preserves_itinerary_identity_for_provider_expanded_names(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_names = {
        "Taj Exotica Resort": "Taj Exotica Resort",
        "Mapusa Market": "Mapusa Municipal Market",
        "Fontainhas Latin Quarter": "Bairro das Fontainhas old quarter",
        "The Fisherman's Wharf Panjim": "The Fisherman's Wharf Panjim",
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": provider_names.get(name, name),
            "rating": 4.4,
            "address": f"{name}, {city}",
            "lat": 15.0 + len(name) / 100,
            "lng": 73.9 + len(name) / 100,
        },
    )
    trip = {
        "destination": "Goa",
        "selected_hotels": [{"name": "Taj Exotica Resort"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Taj Exotica Resort", "kind": "hotel"},
                {"name": "Mapusa Market", "kind": "attraction", "time": "10:00"},
                {"name": "Fontainhas Latin Quarter", "kind": "attraction", "time": "13:00"},
                {"name": "The Fisherman's Wharf Panjim", "kind": "meal", "time": "17:30"},
                {"name": "Taj Exotica Resort", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    route_names = [names_by_id[pin_id] for pin_id in view["days"][0]["pin_ids"]]

    assert route_names[1:4] == [
        "Mapusa Market",
        "Fontainhas Latin Quarter",
        "The Fisherman's Wharf Panjim",
    ]
    assert next(pin for pin in view["pins"] if pin["name"] == "Mapusa Market")[
        "provider_name"
    ] == "Mapusa Municipal Market"


def test_map_view_reuses_places_across_complete_day_circuits(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            {
                "day": 2,
                "stops": [
                    {"name": "Fort Aguada", "kind": "attraction"},
                    {"name": "Dudhsagar Falls Trek", "kind": "attraction"},
                ],
            },
        ],
    }

    mv = trip_view.build_map_view(trip)
    id_by_name = {p["name"]: p["id"] for p in mv["pins"]}
    days = {day["day"]: day for day in mv["days"]}
    hotel_id = id_by_name["Taj Exotica Resort"]

    assert id_by_name["Fort Aguada"] in days[1]["pin_ids"]
    assert id_by_name["Fort Aguada"] in days[2]["pin_ids"]
    assert days[1]["pin_ids"][0] == days[1]["pin_ids"][-1] == hotel_id
    assert days[2]["pin_ids"][0] == days[2]["pin_ids"][-1] == hotel_id
    assert days[2]["route"]["distance_km"] > 0
    assert len(days[2]["legs"]) == len(days[2]["pin_ids"]) - 1
    assert days[2]["legs"][0]["distance_km"] > 0
    assert days[2]["route"]["duration_min"] == sum(
        leg["duration_min"] for leg in days[2]["legs"]
    )
    if days[2]["route"]["duration_min"] >= 60:
        assert "hr" in days[2]["route"]["duration_display"]


def test_map_view_carries_forward_hotel_after_transition(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Trident Udaipur": (24.577, 73.683),
        "Taj Hari Mahal Jodhpur": (26.269, 73.010),
        "Suryagarh Jaisalmer": (26.916, 70.921),
        "Camel Safari at Sam Sand Dunes": (26.835, 70.528),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": name,
            "lat": coords.get(name, (None, None))[0],
            "lng": coords.get(name, (None, None))[1],
        },
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "place_coords",
        lambda name, city: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Taj Hari Mahal Jodhpur"},
            {"name": "Suryagarh Jaisalmer"},
        ],
        "day_wise_itinerary": [
            {
                "day": 5,
                "stops": [
                    {"name": "Taj Hari Mahal Jodhpur", "kind": "hotel"},
                    {"name": "Drive: Jodhpur to Jaisalmer", "kind": "transport"},
                    {"name": "Suryagarh Jaisalmer", "kind": "hotel"},
                ],
            },
            {
                "day": 6,
                "stops": [
                    {"name": "Camel Safari at Sam Sand Dunes", "kind": "attraction"},
                ],
            },
        ],
    }

    view = trip_view.build_map_view(trip)

    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    day6 = next(day for day in view["days"] if day["day"] == 6)
    route_names = [names_by_id[pin_id] for pin_id in day6["pin_ids"]]
    assert route_names == [
        "Suryagarh Jaisalmer",
        "Camel Safari at Sam Sand Dunes",
        "Suryagarh Jaisalmer",
    ]


def test_map_view_uses_rendered_stay_over_prose_hotel_alternatives(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Hyatt Place Rameswaram": (9.2833, 79.3129),
        "Daiwik Hotels Rameswaram": (9.2868, 79.3120),
        "The Residency Towers Rameswaram": (9.2890, 79.3105),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": name,
            "lat": coords.get(name, (None, None))[0],
            "lng": coords.get(name, (None, None))[1],
        },
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "place_coords",
        lambda name, city: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rameswaram",
        "selected_hotels": [
            {"name": "Hyatt Place Rameswaram"},
            {"name": "Daiwik Hotels Rameswaram"},
            {"name": "The Residency Towers Rameswaram"},
        ],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [{"name": "Hyatt Place Rameswaram", "kind": "hotel"}],
            },
            {
                "day": 2,
                "plan": (
                    "Continue from Hyatt; Daiwik Hotels Rameswaram and The Residency "
                    "Towers Rameswaram are nearby alternatives."
                ),
            },
        ],
    }

    itinerary = trip_view.build_itinerary(trip)
    view = trip_view.build_map_view(trip)

    itinerary_day2 = next(day for day in itinerary["days"] if day["day"] == 2)
    assert {
        stop["name"] for stop in itinerary_day2["stops"] if stop["kind"] == "hotel"
    } == {"Hyatt Place Rameswaram"}
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    day2 = next(day for day in view["days"] if day["day"] == 2)
    hotel_names = {
        pins_by_id[pin_id]["name"]
        for pin_id in day2["pin_ids"]
        if pins_by_id[pin_id]["kind"] == "hotel"
    }
    assert hotel_names == {"Hyatt Place Rameswaram"}


def test_map_view_includes_restaurant_in_day_circuit(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Taj Exotica Resort", "kind": "hotel"},
                    {"name": "Dudhsagar Falls Trek", "kind": "attraction"},
                    {"name": "Fort Aguada", "kind": "meal"},
                ],
            }
        ],
    }
    mv = trip_view.build_map_view(trip)
    by_name = {pin["name"]: pin for pin in mv["pins"]}
    restaurant = by_name["Fort Aguada"]
    assert restaurant["kind"] == "meal"
    day1 = next(day for day in mv["days"] if day["day"] == 1)
    assert restaurant["id"] in day1["pin_ids"]


def test_map_view_connects_flight_airports_to_destination_stay(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
        "Jaisalmer Airport": (26.8887, 70.8649),
        "Suryagarh": (26.9949, 70.8484),
    }
    canonical_names = {
        "Bangalore Airport": "Kempegowda International Airport Bengaluru",
        "Udaipur Airport": "Maharana Pratap Airport",
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": f"pid-{name}",
            "name": canonical_names.get(name, name),
            "lat": coords.get(name, (None, None))[0],
            "lng": coords.get(name, (None, None))[1],
        },
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Flight: Bangalore to Udaipur",
                        "kind": "flight",
                        "time": "08:00",
                    },
                    {"name": "Trident Udaipur", "kind": "hotel", "time": "10:30"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Suryagarh", "kind": "hotel", "time": "07:20"},
                    {
                        "name": "Flight: Jaisalmer to Bangalore",
                        "kind": "flight",
                        "time": "10:00",
                    },
                ],
            },
        ],
    }

    view = trip_view.build_map_view(trip)

    pins = {pin.get("source_name", pin["name"]): pin for pin in view["pins"]}
    assert pins["Bangalore Airport"]["kind"] == "airport"
    assert pins["Udaipur Airport"]["kind"] == "airport"
    assert pins["Bangalore Airport"]["name"] == "Bangalore Airport"
    assert pins["Bangalore Airport"]["provider_name"] == (
        "Kempegowda International Airport Bengaluru"
    )
    assert pins["Udaipur Airport"]["name"] == "Udaipur Airport"
    assert pins["Udaipur Airport"]["provider_name"] == "Maharana Pratap Airport"
    assert pins["Bangalore Airport"]["occurrences"] == [
        {"day": 1, "stop": 1, "time": "06:00"},
        {"day": 2, "stop": 4, "time": "11:30"},
    ]
    assert pins["Udaipur Airport"]["occurrences"] == [
        {"day": 1, "stop": 3, "time": "09:30"},
    ]
    assert pins["Trident Udaipur"]["occurrences"] == [
        {"day": 1, "stop": 4, "time": "10:30"},
    ]
    assert view["airport"] is None
    day = view["days"][0]
    assert day["pin_ids"][0] != day["pin_ids"][-1]
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    route_names = [pins_by_id[pin_id]["name"] for pin_id in day["pin_ids"]]
    assert route_names == [
        "Bangalore Airport",
        "Udaipur Airport",
        "Trident Udaipur",
    ]
    assert [pins_by_id[pin_id]["name"] for pin_id in day["circuit_pin_ids"]] == [
        "Udaipur Airport",
        "Trident Udaipur",
    ]
    assert day["route"]["distance_km"] > 0
    assert day["route"]["duration_min"] < 240
    assert day["route"]["mode"] == "Flight + local"
    assert day["legs"][0]["mode"] == "Flight"
    assert day["legs"][0]["intercity"] is True
    assert "intercity" not in day["legs"][1]
    departure_day = view["days"][1]
    departure_route_names = [
        pins_by_id[pin_id]["name"] for pin_id in departure_day["pin_ids"]
    ]
    assert departure_route_names == [
        "Suryagarh",
        "Jaisalmer Airport",
        "Bangalore Airport",
    ]
    assert [
        pins_by_id[pin_id]["name"] for pin_id in departure_day["circuit_pin_ids"]
    ] == ["Suryagarh", "Jaisalmer Airport"]
    assert departure_day["legs"][-1]["mode"] == "Flight"
    assert departure_day["legs"][-1]["intercity"] is True


def test_map_view_brings_an_excursion_day_home_to_its_stay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A day that drives out and back must end at the stay, not at the last sight."""
    coords = {
        "Express Inn Nashik": (19.9526, 73.7553),
        "Bhatsa River Valley": (19.5254, 73.3783),
        "Ghatandevi Temple": (19.6994, 73.5245),
    }

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
        lat, lng = coords.get(name, (None, None))
        return {"place_id": f"pid-{name}", "name": name, "lat": lat, "lng": lng}

    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")

    trip = {
        "destination": "Nashik",
        "origin": "Bangalore",
        "selected_hotels": [{"name": "Express Inn Nashik"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Drive: Nashik to Igatpuri", "kind": "transport", "time": "08:00"},
                    {"name": "Bhatsa River Valley", "kind": "attraction", "time": "10:00"},
                    {"name": "Ghatandevi Temple", "kind": "attraction", "time": "14:00"},
                    {"name": "Drive: Igatpuri to Nashik", "kind": "transport", "time": "15:00"},
                    {"name": "Express Inn Nashik", "kind": "hotel", "time": "17:00"},
                ],
            }
        ],
    }

    view = trip_view.build_map_view(trip)
    pins = {pin["id"]: pin for pin in view["pins"]}
    route = [pins[pin_id]["name"] for pin_id in view["days"][0]["pin_ids"]]

    assert route[0] == "Express Inn Nashik"
    assert route[-1] == "Express Inn Nashik"
    assert "Ghatandevi Temple" in route
