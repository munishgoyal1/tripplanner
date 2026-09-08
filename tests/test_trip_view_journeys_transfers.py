"""Trip-view journey, terminal, and transfer tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tests.support.trip_view import (
    SAMPLE_TRIP,
    _long_haul_trip,
)
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


def test_intercity_mode_reads_a_flight_filed_as_a_generic_transfer() -> None:
    mode = trip_view._intercity_transfer_mode
    assert mode("Flight: Bengaluru to Paris", "transport") == "Flight"
    assert mode("Fly Bengaluru → Paris", "transport") == "Flight"
    # A flight mentioned without a route is not itself a journey between places.
    assert mode("Airport lounge before the flight", "transport") is None


def test_map_view_flies_a_transfer_the_plan_filed_as_generic_transport(
    _long_haul_geo: None,
) -> None:
    trip = _long_haul_trip(
        [
            {"name": "Flight: Bengaluru to Paris", "kind": "transport", "time": "08:00"},
            {"name": "Hotel Lutetia", "kind": "hotel", "time": "16:00"},
        ]
    )

    day = trip_view.build_map_view(trip)["days"][0]

    assert day["legs"][0]["mode"] == "Flight"
    assert day["legs"][0]["intercity"] is True


def test_map_view_flies_between_terminals_the_plan_never_connected(
    _long_haul_geo: None,
) -> None:
    """Two distant airports back to back are a flight, not a drive."""
    trip = _long_haul_trip(
        [
            {"name": "Kempegowda International Airport", "kind": "airport", "time": "05:00"},
            {"name": "Charles de Gaulle Airport", "kind": "airport", "time": "14:00"},
            {"name": "Hotel Lutetia", "kind": "hotel", "time": "16:00"},
        ]
    )

    view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    day = view["days"][0]

    assert [pins_by_id[pin_id]["name"] for pin_id in day["pin_ids"]] == [
        "Kempegowda International Airport",
        "Charles de Gaulle Airport",
        "Hotel Lutetia",
    ]
    assert day["legs"][0]["mode"] == "Flight"
    assert day["legs"][0]["intercity"] is True


def test_map_view_does_not_draw_ground_legs_across_unresolved_flights(
    _long_haul_geo: None,
) -> None:
    trip = {
        **_long_haul_trip([]),
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Flight: Bengaluru to Bali", "kind": "flight"},
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                    {"name": "Flight: Bali to Bengaluru", "kind": "flight"},
                ],
            },
            {
                "day": 3,
                "stops": [
                    {"name": "Flight: Bali to Bengaluru", "kind": "flight"},
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                ],
            },
            {
                "day": 4,
                "stops": [
                    {"name": "Flight: Paris to Bengaluru", "kind": "flight"},
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                ],
            },
            {
                "day": 5,
                "stops": [
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                    {"name": "Flight: Bengaluru to Paris", "kind": "flight"},
                ],
            },
        ],
    }

    view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    days = view["days"]

    assert [
        [pins_by_id[pin_id]["name"] for pin_id in day["pin_ids"]]
        for day in days
    ] == [
        ["Bengaluru Airport", "Hotel Lutetia"],
        ["Hotel Lutetia", "Bengaluru Airport"],
        ["Bengaluru Airport", "Hotel Lutetia"],
        ["Paris Airport", "Bengaluru Airport", "Hotel Lutetia"],
        ["Hotel Lutetia", "Bengaluru Airport", "Paris Airport"],
    ]
    assert [day["legs"] for day in days[:3]] == [[], [], []]
    assert [leg["mode"] for leg in days[3]["legs"]] == ["Taxi", "Flight"]
    assert [leg["mode"] for leg in days[4]["legs"]] == ["Flight"]


def test_map_view_does_not_taxi_from_paro_walk_to_delhi_airport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Hotel in Paro": (27.4305, 89.4134),
        "Paro Town Walk": (27.4298, 89.4147),
        "Delhi Airport": (28.5562, 77.1000),
    }
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)

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
        "destination": "Bhutan",
        "origin": "Delhi",
        "selected_hotels": [{"name": "Hotel in Paro"}],
        "day_wise_itinerary": [
            {
                "day": 5,
                "stops": [
                    {"name": "Hotel in Paro", "kind": "hotel"},
                    {"name": "Paro Town Walk", "kind": "attraction"},
                    {"name": "Flight: Paro to Delhi", "kind": "flight"},
                ],
            }
        ],
    }

    view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    day = view["days"][0]

    assert "Delhi Airport" in {pin["name"] for pin in view["pins"]}
    assert all(
        not (
            pins_by_id[leg["from_pin_id"]]["name"] == "Paro Town Walk"
            and pins_by_id[leg["to_pin_id"]]["name"] == "Delhi Airport"
        )
        for leg in day["legs"]
    )


def test_unresolved_flight_origin_does_not_become_following_drive_origin(
    _long_haul_geo: None,
) -> None:
    trip = _long_haul_trip(
        [
            {"name": "Flight: Bengaluru to Bali", "kind": "flight"},
            {"name": "Drive: Bali to Paris", "kind": "transport"},
            {"name": "Hotel Lutetia", "kind": "hotel"},
        ]
    )

    day = trip_view.build_map_view(trip)["days"][0]

    assert day["legs"] == []


def test_itinerary_does_not_bookend_a_long_haul_day_with_the_destination_stay(
    _long_haul_geo: None,
) -> None:
    trip = _long_haul_trip(
        [
            {"name": "Kempegowda International Airport", "kind": "airport", "time": "05:00"},
            {"name": "Charles de Gaulle Airport", "kind": "airport", "time": "14:00"},
            {"name": "Hotel Lutetia", "kind": "hotel", "time": "16:00"},
        ]
    )

    day = trip_view.build_itinerary(trip)["days"][0]

    assert [stop["name"] for stop in day["stops"]] == [
        "Kempegowda International Airport",
        "Charles de Gaulle Airport",
        "Hotel Lutetia",
    ]


def test_map_view_keeps_a_same_city_terminal_pair_local(_long_haul_geo: None) -> None:
    trip = _long_haul_trip(
        [
            {"name": "Charles de Gaulle Airport", "kind": "airport", "time": "09:00"},
            {"name": "Paris Airport", "kind": "airport", "time": "10:00"},
            {"name": "Hotel Lutetia", "kind": "hotel", "time": "12:00"},
        ]
    )

    day = trip_view.build_map_view(trip)["days"][0]

    assert all(not leg.get("intercity") for leg in day["legs"])


def test_connecting_terminals_filed_as_transport_fly_on_both_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shape a real long-haul replan writes: terminals as ``transport`` stops.

    The airports are named one per stop with no leg between them, so nothing in
    the plan says "flight" — the journey is only implied by the terminals.
    """
    coords = {
        "Kempegowda International Airport Bengaluru": (13.1986, 77.7066),
        "Zayed International Airport (AUH)": (24.4330, 54.6511),
        "Paris Charles de Gaulle Airport (CDG)": (49.0097, 2.5479),
        "Hotel Chambiges Elysees": (48.8672, 2.3020),
    }

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
        lat, lng = coords.get(name, (None, None))
        return {"place_id": f"pid-{name}", "name": name, "lat": lat, "lng": lng}

    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")

    trip = {
        "destination": "Paris",
        "origin": "Bangalore",
        "selected_hotels": [{"name": "Hotel Chambiges Elysees"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Kempegowda International Airport Bengaluru",
                        "kind": "transport",
                        "time": "04:35",
                    },
                    {
                        "name": "Zayed International Airport (AUH)",
                        "kind": "transport",
                        "time": "07:00",
                    },
                    {
                        "name": "Paris Charles de Gaulle Airport (CDG)",
                        "kind": "transport",
                        "time": "19:20",
                    },
                    {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                ],
            }
        ],
    }

    day = trip_view.build_map_view(trip)["days"][0]
    assert [leg["mode"] for leg in day["legs"]] == ["Flight", "Flight", "Taxi"]
    assert [leg.get("intercity") for leg in day["legs"]] == [True, True, None]

    # The traveller has not reached the Paris stay yet, so the day must not open there.
    stops = trip_view.build_itinerary(trip)["days"][0]["stops"]
    assert [stop["name"] for stop in stops] == [
        "Kempegowda International Airport Bengaluru",
        "Zayed International Airport (AUH)",
        "Paris Charles de Gaulle Airport (CDG)",
        "Hotel Chambiges Elysees",
    ]


def test_map_view_connects_origin_and_destination_segments_after_road_transfer(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Trident Udaipur": (24.577, 73.683),
        "Hotel Hillock Mount Abu": (24.592, 72.708),
        "Dilwara Temples": (24.609, 72.723),
        "Nakki Lake": (24.593, 72.704),
    }
    canonical_names = {
        "Hotel Hillock Mount Abu": "Hotel Hillock",
        "Dilwara Temples": "Delwara Jain Temple",
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
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Hotel Hillock Mount Abu"},
        ],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {"name": "Trident Udaipur", "kind": "hotel"},
                {"name": "Drive: Udaipur to Mount Abu", "kind": "transport"},
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
                {"name": "Dilwara Temples", "kind": "attraction"},
                {"name": "Nakki Lake", "kind": "attraction"},
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    day = view["days"][0]
    route_names = [names_by_id[pin_id] for pin_id in day["pin_ids"]]
    assert route_names == [
        "Trident Udaipur",
        "Hotel Hillock Mount Abu",
        "Dilwara Temples",
        "Nakki Lake",
        "Hotel Hillock Mount Abu",
    ]
    assert len(day["legs"]) == 4
    assert day["route"]["distance_km"] > 90
    assert day["route"]["mode"] == "Drive + local"
    assert day["legs"][0]["mode"] == "Drive"
    assert day["legs"][0]["intercity"] is True
    assert all("intercity" not in leg for leg in day["legs"][1:])


def test_map_view_closes_a_drive_at_the_following_flight_terminal(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Hotel in Gangtok": (27.3314, 88.6138),
        "Gangtok": (27.3314, 88.6138),
        "Bagdogra Airport": (26.6812, 88.3286),
        "Kolkata Airport": (22.6547, 88.4467),
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
        "destination": "Gangtok and North Sikkim",
        "selected_hotels": [{"name": "Hotel in Gangtok"}],
        "day_wise_itinerary": [{
            "day": 6,
            "stops": [
                {"name": "Hotel in Gangtok", "kind": "hotel"},
                {
                    "name": "Drive: Gangtok to Bagdogra",
                    "kind": "transport",
                    "distance_km": 125,
                    "duration_min": 300,
                },
                {
                    "name": "Flight: Bagdogra to Kolkata",
                    "kind": "flight",
                    "duration_min": 75,
                },
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    day = view["days"][0]
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Hotel in Gangtok",
        "Bagdogra Airport",
        "Kolkata Airport",
    ]
    assert [leg["mode"] for leg in day["legs"]] == ["Drive", "Flight"]
    assert day["legs"][0]["distance_km"] == 125
    assert all(leg["intercity"] is True for leg in day["legs"])


def test_map_view_connects_city_origin_to_hotel_for_road_trip(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore": (12.9716, 77.5946),
        "Coorg Wilderness Resort": (12.3375, 75.8069),
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
        "origin": "Bangalore",
        "destination": "Coorg",
        "selected_hotels": [{"name": "Coorg Wilderness Resort"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Drive: Bangalore to Coorg", "kind": "transport"},
                {"name": "Coorg Wilderness Resort", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    day = view["days"][0]
    route_names = [pins_by_id[pin_id]["name"] for pin_id in day["pin_ids"]]
    assert route_names == ["Bangalore", "Coorg Wilderness Resort"]
    assert day["circuit_pin_ids"] == day["pin_ids"]
    assert len(day["legs"]) == 1
    assert day["legs"][0]["mode"] == "Drive"
    assert day["legs"][0]["intercity"] is True


def test_map_view_connects_train_stations_between_stays(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Rambagh Palace Jaipur": (26.898, 75.808),
        "Jaipur Railway Station": (26.9196, 75.7878),
        "Udaipur Railway Station": (24.5683, 73.6991),
        "Trident Udaipur": (24.577, 73.683),
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
            {"name": "Rambagh Palace Jaipur"},
            {"name": "Trident Udaipur"},
        ],
        "day_wise_itinerary": [{
            "day": 4,
            "stops": [
                {"name": "Rambagh Palace Jaipur", "kind": "hotel"},
                {"name": "Train: Jaipur to Udaipur", "kind": "transport"},
                {"name": "Trident Udaipur", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    day = view["days"][0]
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Rambagh Palace Jaipur",
        "Jaipur Railway Station",
        "Udaipur Railway Station",
        "Trident Udaipur",
    ]
    assert [names_by_id[pin_id] for pin_id in day["circuit_pin_ids"]] == [
        "Udaipur Railway Station",
        "Trident Udaipur",
    ]
    pins_by_name = {pin["name"]: pin for pin in view["pins"]}
    assert pins_by_name["Jaipur Railway Station"]["occurrences"] == [
        {"day": 4, "stop": 2, "time": ""}
    ]
    assert day["route"]["mode"] == "Train + local"
    assert day["legs"][1]["mode"] == "Train"
    assert day["legs"][1]["intercity"] is True


def test_map_view_renders_shinkansen_between_tokyo_and_kyoto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Tokyo Railway Station": (35.6812, 139.7671),
        "Kyoto Railway Station": (34.9858, 135.7588),
        "Sunroute Plaza Shinjuku": (35.6877, 139.7004),
        "Hotel Granvia Kyoto": (34.9859, 135.7585),
        "Gion District": (35.0037, 135.7788),
    }
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
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
    monkeypatch.setattr(trip_view.places_cache, "get_summary", trip_view.places_cache.get_details)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")
    trip = {
        **SAMPLE_TRIP,
        "destination": "Japan (Tokyo & Kyoto)",
        "selected_hotels": [
            {"name": "Sunroute Plaza Shinjuku"},
            {"name": "Hotel Granvia Kyoto"},
        ],
        "day_wise_itinerary": [
            {
                "day": 4,
                "stops": [
                    {"name": "Shinkansen: Tokyo to Kyoto", "kind": "transport"},
                    {"name": "Sunroute Plaza Shinjuku", "kind": "hotel"},
                    {"name": "Hotel Granvia Kyoto", "kind": "hotel"},
                    {"name": "Gion District", "kind": "attraction"},
                ],
            }
        ],
    }

    day = trip_view.build_map_view(trip)["days"][0]

    assert any(leg["mode"] == "Train" and leg["intercity"] for leg in day["legs"])
    assert all(
        leg["distance_km"] <= 300 or leg["mode"] not in {"Walk", "Taxi"}
        for leg in day["legs"]
    )


def test_map_view_omits_implausibly_long_ground_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Tokyo Hotel": (35.6764, 139.6500),
        "Kyoto Hotel": (35.0116, 135.7681),
    }
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
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
    monkeypatch.setattr(trip_view.places_cache, "get_summary", trip_view.places_cache.get_details)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "Tokyo Hotel"}, {"name": "Kyoto Hotel"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Tokyo Hotel", "kind": "hotel"},
                    {"name": "Kyoto Hotel", "kind": "hotel"},
                ],
            }
        ],
    }

    assert trip_view.build_map_view(trip)["days"][0]["legs"] == []


def test_map_view_connects_bus_stands_between_stays(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Origin Hotel": (26.9, 75.8),
        "Jaipur Bus Stand": (26.92, 75.79),
        "Udaipur Bus Stand": (24.58, 73.7),
        "Destination Hotel": (24.577, 73.683),
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
        "selected_hotels": [{"name": "Origin Hotel"}, {"name": "Destination Hotel"}],
        "day_wise_itinerary": [{
            "day": 2,
            "stops": [
                {"name": "Origin Hotel", "kind": "hotel"},
                {"name": "Bus: Jaipur to Udaipur", "kind": "transport"},
                {"name": "Destination Hotel", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Origin Hotel",
        "Jaipur Bus Stand",
        "Udaipur Bus Stand",
        "Destination Hotel",
    ]
    assert [names_by_id[pin_id] for pin_id in day["circuit_pin_ids"]] == [
        "Udaipur Bus Stand",
        "Destination Hotel",
    ]
    pins_by_name = {pin["name"]: pin for pin in view["pins"]}
    assert pins_by_name["Udaipur Bus Stand"]["occurrences"] == [
        {"day": 2, "stop": 4, "time": ""}
    ]
    assert day["route"]["mode"] == "Bus + local"
    assert day["legs"][1]["mode"] == "Bus"
    assert day["legs"][1]["intercity"] is True


def test_map_view_keeps_local_taxi_day_as_closed_hotel_circuit(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "selected_activities": [],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Taj Exotica Resort", "kind": "hotel"},
                {"name": "Taxi: Taj Exotica Resort to Fort Aguada", "kind": "transport"},
                {"name": "Fort Aguada", "kind": "attraction"},
                {"name": "Taj Exotica Resort", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    route_names = [names_by_id[pin_id] for pin_id in day["pin_ids"]]
    assert route_names == ["Taj Exotica Resort", "Fort Aguada", "Taj Exotica Resort"]
    assert all("intercity" not in leg for leg in day["legs"])


def test_map_view_does_not_bind_partial_flight_to_destination_hotel(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Destination Hotel": (24.577, 73.683),
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
        "selected_hotels": [{"name": "Destination Hotel"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Flight: Bangalore to Udaipur", "kind": "flight"},
                {"name": "Destination Hotel", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Bangalore Airport",
        "Destination Hotel",
    ]
    assert day["legs"] == []


def test_map_view_pins_flight_stops_named_as_single_airports(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The agent may write one stop per terminal instead of "Flight: A to B"; the
    # itinerary shows those, so the map has to show them too.
    coords = {
        "Kempegowda International Airport, Bangalore (BLR)": (13.1986, 77.7066),
        "Indira Gandhi International Airport, Delhi (DEL)": (28.5562, 77.1000),
        "Charles de Gaulle Airport, Paris (CDG)": (49.0097, 2.5479),
        "Hotel Chambiges Elysees": (48.8667, 2.3020),
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
        "destination": "Paris",
        "selected_hotels": [{"name": "Hotel Chambiges Elysees"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Kempegowda International Airport, Bangalore (BLR)", "kind": "flight"},
                {"name": "Indira Gandhi International Airport, Delhi (DEL)", "kind": "flight"},
                {"name": "Charles de Gaulle Airport, Paris (CDG)", "kind": "flight"},
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    pinned = {pin["name"] for pin in view["pins"]}
    assert "Kempegowda International Airport, Bangalore (BLR)" in pinned
    assert "Indira Gandhi International Airport, Delhi (DEL)" in pinned
    assert "Charles de Gaulle Airport, Paris (CDG)" in pinned


def test_map_view_does_not_mark_hotel_to_unmatched_airport_as_flight(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Udaipur Hotel": (24.577, 73.683),
        "Jodhpur Airport": (26.251, 73.049),
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
        "selected_hotels": [{"name": "Udaipur Hotel"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Udaipur Hotel", "kind": "hotel"},
                {"name": "Flight: Udaipur to Jodhpur", "kind": "flight"},
                {"name": "Jodhpur Airport", "kind": "airport"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    pins_by_id = {pin["id"]: pin for pin in view["pins"]}
    mixed_terminal_legs = [
        leg
        for leg in day["legs"]
        if {
            pins_by_id[leg["from_pin_id"]]["kind"],
            pins_by_id[leg["to_pin_id"]]["kind"],
        }
        != {"airport"}
    ]
    assert mixed_terminal_legs
    assert all(leg.get("intercity") is not True for leg in mixed_terminal_legs)
    assert all(leg["mode"] != "Flight" for leg in mixed_terminal_legs)


def test_structured_itinerary_preserves_arrival_and_departure_flights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
        "Suryagarh": (26.9949, 70.8484),
        "Jaisalmer Airport": (26.8887, 70.8649),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
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
                        "arrival_time": "11:10",
                        "duration_min": 70,
                    },
                    {"name": "Trident Udaipur", "kind": "hotel"},
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
                        "arrival_time": "12:05",
                        "duration_min": 125,
                    },
                ],
            },
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    arrival, departure = itinerary["days"]
    assert [stop["kind"] for stop in arrival["stops"]] == [
        "airport", "flight", "airport", "hotel"
    ]
    assert [stop["kind"] for stop in departure["stops"]] == [
        "hotel", "airport", "flight", "airport"
    ]
    assert arrival["stops"][0]["name"] == "Bangalore Airport"
    assert arrival["stops"][0]["time"] == "06:00"
    assert arrival["stops"][0]["operational_time_display"] == (
        "2 hr check-in and security"
    )
    assert arrival["stops"][2]["name"] == "Udaipur Airport"
    assert arrival["stops"][1]["departure_time"] == "11:10"
    assert arrival["stops"][2]["time"] == "11:10"
    assert arrival["stops"][3]["time"]
    assert arrival["stops"][3]["time_estimated"] is True
    assert departure["stops"][-2]["name"] == (
        "Flight: Jaisalmer Airport to Bangalore Airport"
    )
    for flight in (arrival["stops"][1], departure["stops"][-2]):
        assert flight["rating"] is None
        assert flight["review_count"] is None
        assert flight["popularity_score"] is None
        assert flight["opening_hours"] == ""
        assert flight["duration_min"] > 0
    assert itinerary["stats"]["stops"] == 4


def test_mode_tagged_gangtok_flights_expand_with_both_airports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trip = {
        "destination": "Gangtok",
        "origin": "Bangalore",
        "start_date": "2026-10-10",
        "end_date": "2026-10-16",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Bangalore to Bagdogra",
                        "kind": "transport",
                        "mode": "flight",
                        "departure_airport": "Bangalore Airport",
                        "arrival_airport": "Bagdogra Airport",
                        "departure_time": "06:30",
                        "arrival_time": "09:20",
                    },
                    {"name": "Drive from Bagdogra Airport to Gangtok", "kind": "transport"},
                    {"name": "Gangtok Hotel", "kind": "hotel"},
                ],
            },
            {
                "day": 7,
                "stops": [
                    {"name": "Gangtok Hotel", "kind": "hotel"},
                    {"name": "Drive from Gangtok to Bagdogra Airport", "kind": "transport"},
                    {
                        "name": "Bagdogra to Bangalore",
                        "kind": "transport",
                        "mode": "Flight",
                        "departure_airport": "Bagdogra Airport",
                        "arrival_airport": "Bangalore Airport",
                        "departure_time": "18:10",
                        "arrival_time": "21:00",
                    },
                ],
            },
        ],
    }
    monkeypatch.setattr(trip_view, "_place_coords", lambda *args: None)

    itinerary = trip_view.build_itinerary(trip)

    assert [(stop["kind"], stop["name"]) for stop in itinerary["days"][0]["stops"][:4]] == [
        ("airport", "Bangalore Airport"),
        ("flight", "Flight: Bangalore Airport to Bagdogra Airport"),
        ("airport", "Bagdogra Airport"),
        ("transport", "Drive from Bagdogra Airport to Gangtok"),
    ]
    assert [
        (stop["kind"], stop["name"]) for stop in itinerary["days"][1]["stops"][1:]
    ] == [
        ("transport", "Drive from Gangtok to Bagdogra Airport"),
        ("airport", "Bagdogra Airport"),
        ("flight", "Flight: Bagdogra Airport to Bangalore Airport"),
        ("airport", "Bangalore Airport"),
    ]


@pytest.mark.parametrize(
    ("name", "terminal_kind", "departure_terminal", "arrival_terminal", "buffer_min"),
    [
        (
            "Train: Madurai to Kanyakumari",
            "station",
            "Madurai Railway Station",
            "Kanyakumari Railway Station",
            45,
        ),
        (
            "Bus: Madurai to Kanyakumari",
            "bus_station",
            "Madurai Bus Stand",
            "Kanyakumari Bus Stand",
            30,
        ),
    ],
)
def test_timed_surface_transport_adds_terminal_buffer_stops(
    name: str,
    terminal_kind: str,
    departure_terminal: str,
    arrival_terminal: str,
    buffer_min: int,
) -> None:
    trip = {
        **SAMPLE_TRIP,
        "destination": "Tamil Nadu",
        "selected_hotels": [],
        "day_wise_itinerary": [{
            "day": 2,
            "stops": [{
                "name": name,
                "kind": "transport",
                "time": "08:00",
                "arrival_time": "12:00",
                "duration_min": 240,
            }],
        }],
    }

    stops = trip_view.build_itinerary(trip)["days"][0]["stops"]

    assert [stop["kind"] for stop in stops] == [
        terminal_kind,
        "transport",
        terminal_kind,
    ]
    assert stops[0]["name"] == departure_terminal
    assert stops[0]["time"] == trip_view._clock_display(8 * 60 - buffer_min)
    assert stops[0]["terminal_role"] == "departure"
    assert "baggage and boarding" in stops[0]["operational_time_display"]
    assert stops[1]["departure_time"] == "12:00"
    assert stops[2]["name"] == arrival_terminal
    assert stops[2]["time"] == "12:00"
    assert stops[2]["terminal_role"] == "arrival"
    assert "disembark and baggage" in stops[2]["operational_time_display"]


def test_transfer_day_starts_from_prior_rameswaram_hotel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Hyatt Place Rameswaram": (9.2833, 79.3129),
        "Rameswaram": (9.2876, 79.3129),
        "Sparsa Kanyakumari": (8.0864, 77.5510),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city, **_kwargs: {
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
        "destination": "Tamil Nadu",
        "selected_hotels": [
            {"name": "Hyatt Place Rameswaram"},
            {"name": "Sparsa Kanyakumari"},
        ],
        "day_wise_itinerary": [
            {
                "day": 2,
                "stops": [
                    {"name": "Hyatt Place Rameswaram", "kind": "hotel"},
                    {"name": "Ramanathaswamy Temple", "kind": "attraction"},
                ],
            },
            {
                "day": 3,
                "stops": [
                    {
                        "name": "Rameswaram to Kanyakumari",
                        "kind": "other",
                        "mode": "car",
                    },
                    {"name": "Sparsa Kanyakumari", "kind": "hotel"},
                ],
            },
        ],
    }

    itinerary = trip_view.build_itinerary(trip)
    day3_stops = itinerary["days"][1]["stops"]
    assert [(stop["name"], stop["kind"]) for stop in day3_stops] == [
        ("Hyatt Place Rameswaram", "hotel"),
        ("Drive: Rameswaram to Kanyakumari", "transport"),
        ("Sparsa Kanyakumari", "hotel"),
    ]

    map_view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in map_view["pins"]}
    day3 = next(day for day in map_view["days"] if day["day"] == 3)
    assert [pins_by_id[pin_id]["name"] for pin_id in day3["pin_ids"]] == [
        "Hyatt Place Rameswaram",
        "Sparsa Kanyakumari",
    ]
    assert day3["legs"][0]["mode"] == "Drive"
    assert day3["legs"][0]["intercity"] is True


@pytest.mark.parametrize(
    ("name", "origin", "destination"),
    [
        ("Drive: Bagdogra to Gangtok", "Bagdogra", "Gangtok"),
        ("Drive from Gangtok to Lachung", "Gangtok", "Lachung"),
        ("Bagdogra to Gangtok drive", "Bagdogra", "Gangtok"),
        ("Car ride from Bagdogra to Gangtok", "Bagdogra", "Gangtok"),
        ("Private car: Lachung to Gangtok", "Lachung", "Gangtok"),
        ("Road transfer from Gangtok to Darjeeling", "Gangtok", "Darjeeling"),
        ("Transfer from Pelling to Darjeeling by car", "Pelling", "Darjeeling"),
    ],
)
def test_drive_labels_share_transport_normalization_and_route_endpoints(
    name: str,
    origin: str,
    destination: str,
) -> None:
    assert trip_view._normalized_stop_kind(name, "other") == "transport"
    assert trip_view._transport_route_endpoints(name) == (origin, destination)
    assert trip_view._transport_terminal_refs(name, "transport") == [("origin", origin)]


def test_destination_only_drive_remains_transport_without_inventing_an_origin() -> None:
    name = "Drive to Darjeeling"
    assert trip_view._normalized_stop_kind(name, "other") == "transport"
    assert trip_view._transport_route_endpoints(name) is None
    assert trip_view._transport_terminal_refs(name, "transport") == []


@pytest.mark.parametrize(
    ("name", "waypoints"),
    [
        ("Flight Bengaluru to London via Doha", ["Bengaluru", "Doha", "London"]),
        ("Flight Bengaluru → Doha → London", ["Bengaluru", "Doha", "London"]),
        ("Flight Bengaluru to Indore", ["Bengaluru", "Indore"]),
        ("Flight Delhi to Lima via Doha and Madrid", ["Delhi", "Doha", "Madrid", "Lima"]),
    ],
)
def test_a_connecting_leg_keeps_every_place_it_passes_through(
    name: str, waypoints: list[str]
) -> None:
    from tripplanner.web.transport import _transport_route_waypoints

    assert _transport_route_waypoints(name) == waypoints
    # The endpoints view stays the outer pair so existing callers are unaffected.
    assert trip_view._transport_route_endpoints(name) == (waypoints[0], waypoints[-1])


def test_a_connecting_flight_pins_the_airport_it_stops_at() -> None:
    assert trip_view._transport_terminal_refs("Flight Bengaluru to London via Doha", "flight") == [
        ("airport", "Bengaluru Airport"),
        ("airport", "Doha Airport"),
        ("airport", "London Airport"),
    ]


def test_connecting_round_trip_keeps_itinerary_and_map_terminals_in_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Delhi Airport": (28.5562, 77.1000),
        "Paris Airport": (49.0097, 2.5479),
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
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")
    trip = {
        **SAMPLE_TRIP,
        "destination": "Paris",
        "selected_hotels": [],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [{
                    "name": "Flight: Bangalore to Paris via Delhi",
                    "kind": "flight",
                    "time": "10:00",
                    "arrival_time": "19:30",
                    "duration_min": 570,
                }],
            },
            {
                "day": 4,
                "stops": [{
                    "name": "Flight: Paris to Bangalore via Delhi",
                    "kind": "flight",
                    "time": "12:00",
                    "arrival_time": "23:00",
                    "duration_min": 660,
                }],
            },
        ],
    }

    days = trip_view.build_itinerary(trip)["days"]
    terminal_rows = [
        [
            (stop["name"], stop.get("terminal_role"))
            for stop in day["stops"]
            if stop.get("terminal_role")
        ]
        for day in days
    ]

    assert terminal_rows == [
        [
            ("Bangalore Airport", "departure"),
            ("Delhi Airport", "connection"),
            ("Paris Airport", "arrival"),
        ],
        [
            ("Paris Airport", "departure"),
            ("Delhi Airport", "connection"),
            ("Bangalore Airport", "arrival"),
        ],
    ]

    map_view = trip_view.build_map_view(trip)
    names_by_id = {pin["id"]: pin["name"] for pin in map_view["pins"]}
    map_terminals = [
        [
            names_by_id[pin_id]
            for pin_id in day["pin_ids"]
            if names_by_id[pin_id].endswith(" Airport")
        ]
        for day in map_view["days"]
    ]
    assert map_terminals == [
        ["Bangalore Airport", "Delhi Airport", "Paris Airport"],
        ["Paris Airport", "Delhi Airport", "Bangalore Airport"],
    ]


def test_northeast_drives_keep_waypoints_and_hotels_in_map_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    coords = {
        "Bagdogra": (26.699, 88.311),
        "Gangtok Hotel": (27.331, 88.613),
        "Seven Sisters Falls": (27.536, 88.653),
        "Singhik View Point": (27.529, 88.556),
        "Lachung Hotel": (27.689, 88.744),
        "Lachung Hotel & Resort": (25.000, 80.000),
        "Zero Point": (27.977, 88.702),
        "Darjeeling": (27.041, 88.266),
        "Darjeeling Hotel": (27.047, 88.263),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city, **_kwargs: {
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
        "destination": "Northeast India",
        "selected_hotels": [
            {"name": "Gangtok Hotel"},
            {"name": "Lachung Hotel"},
            {"name": "Darjeeling Hotel"},
        ],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Bagdogra to Gangtok drive",
                        "kind": "other",
                        "duration_min": 300,
                    },
                    {"name": "Gangtok Hotel", "kind": "hotel"},
                ],
            },
            {
                "day": 4,
                "stops": [
                    {
                        "name": "Drive from Gangtok to Lachung",
                        "kind": "other",
                        "distance_km": 121,
                        "duration_min": 360,
                    },
                    {"name": "Seven Sisters Falls", "kind": "attraction"},
                    {"name": "Singhik View Point", "kind": "attraction"},
                    {"name": "Lachung Hotel", "kind": "hotel"},
                ],
            },
            {
                "day": 5,
                "stops": [
                    {"name": "Lachung Hotel & Resort", "kind": "hotel"},
                ],
            },
            {
                "day": 7,
                "stops": [
                    {"name": "Lachung Hotel & Resort", "kind": "hotel"},
                    {"name": "Zero Point", "kind": "attraction"},
                    {"name": "Lachung Hotel & Resort", "kind": "hotel"},
                ],
            },
            {
                "day": 8,
                "stops": [
                    {"name": "Toy train ride", "kind": "other"},
                    {"name": "Drive to Darjeeling", "kind": "other"},
                    {"name": "Darjeeling Hotel", "kind": "hotel"},
                ],
            },
        ],
    }

    itinerary = trip_view.build_itinerary(trip)
    day1_drive = itinerary["days"][0]["stops"][1]
    assert day1_drive["kind"] == "transport"
    assert "lunch or substantial snack stop" in day1_drive["insight"]
    day4_drive = next(
        stop for stop in itinerary["days"][1]["stops"] if stop["kind"] == "transport"
    )
    assert "same taxi or self-drive vehicle" in day4_drive["insight"]
    assert "Seven Sisters Falls, Singhik View Point" in day4_drive["insight"]
    day4_stops = itinerary["days"][1]["stops"]
    assert day4_drive["distance_km"] == 121
    assert day4_drive["duration_min"] == 360
    assert "duration_estimated" not in day4_drive
    assert all(
        stop["travel_from_previous"]["mode"] == "Drive"
        and "same vehicle" in stop["travel_from_previous"]["detail"]
        for stop in day4_stops[2:]
    )
    day4_travel_legs = [
        stop["travel_from_previous"]
        for stop in day4_stops
        if stop.get("travel_from_previous", {}).get("mode") == "Drive"
    ]
    assert sum(leg["distance_km"] for leg in day4_travel_legs) == 121
    assert sum(leg["duration_min"] for leg in day4_travel_legs) == 360
    assert all(leg["metrics_source"] == "saved" for leg in day4_travel_legs)
    day8_itinerary = next(day for day in itinerary["days"] if day["day"] == 8)
    assert [
        stop["kind"]
        for stop in day8_itinerary["stops"]
        if "train" in stop["name"].lower()
    ] == ["transport"]

    map_view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in map_view["pins"]}
    day4 = next(day for day in map_view["days"] if day["day"] == 4)
    assert [pins_by_id[pin_id]["name"] for pin_id in day4["pin_ids"]] == [
        "Gangtok Hotel",
        "Seven Sisters Falls",
        "Singhik View Point",
        "Lachung Hotel",
    ]
    assert day4["legs"] and all(
        leg.get("intercity") and leg["mode"] == "Drive" for leg in day4["legs"]
    ), day4
    assert day4["route"]["distance_km"] == 121
    assert day4["route"]["duration_min"] == 360
    assert all(leg["metrics_source"] == "saved" for leg in day4["legs"])
    drive_circuit = next(
        circuit for circuit in map_view["drive_circuits"] if circuit["day"] == 4
    )
    assert drive_circuit["id"] == day4_drive["route_circuit_id"]
    assert [pins_by_id[pin_id]["name"] for pin_id in drive_circuit["pin_ids"]] == [
        "Gangtok Hotel",
        "Seven Sisters Falls",
        "Singhik View Point",
        "Lachung Hotel",
    ]
    assert drive_circuit["route"]["distance_km"] == 121
    assert drive_circuit["route"]["duration_min"] == 360
    assert all(
        leg["route_circuit_id"] == drive_circuit["id"]
        for leg in drive_circuit["legs"]
    )
    lachung_pins = [pin for pin in map_view["pins"] if "Lachung" in pin["name"]]
    assert len(lachung_pins) == 1
    assert (lachung_pins[0]["lat"], lachung_pins[0]["lng"]) == coords["Lachung Hotel"]
    assert [(item["day"], item["stop"]) for item in lachung_pins[0]["occurrences"]] == [
        (4, 5),
        (5, 1),
        (7, 1),
        (7, 3),
        (8, 1),
    ]
    day5 = next(day for day in map_view["days"] if day["day"] == 5)
    assert day5["pin_ids"] == [lachung_pins[0]["id"]]
    day7 = next(day for day in map_view["days"] if day["day"] == 7)
    assert [pins_by_id[pin_id]["name"] for pin_id in day7["pin_ids"]] == [
        "Lachung Hotel",
        "Zero Point",
        "Lachung Hotel",
    ]
    for day_number in (1, 8):
        day = next(candidate for candidate in map_view["days"] if candidate["day"] == day_number)
        assert day["legs"] and all(leg["intercity"] for leg in day["legs"])


def test_bus_transfer_builds_separate_road_circuit_with_route_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Boston Hotel": (42.3601, -71.0589),
        "Boston Bus Stand": (42.3472, -71.0756),
        "Scenic Hudson Overlook": (41.7004, -73.9290),
        "Roadside Kitchen": (41.3083, -72.9279),
        "New York Bus Stand": (40.7569, -73.9903),
        "New York Hotel": (40.7580, -73.9855),
        "Central Park": (40.7812, -73.9665),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city, **_kwargs: {
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
        "destination": "New York",
        "selected_hotels": [
            {"name": "Boston Hotel"},
            {"name": "New York Hotel"},
        ],
        "day_wise_itinerary": [
            {
                "day": 2,
                "title": "Boston to New York by road",
                "stops": [
                    {"name": "Boston Hotel", "kind": "hotel"},
                    {
                        "name": "Bus: Boston to New York",
                        "kind": "transport",
                        "distance_km": 350,
                        "duration_min": 300,
                    },
                    {
                        "name": "Scenic Hudson Overlook",
                        "kind": "attraction",
                        "note": "On-route scenic stop",
                    },
                    {
                        "name": "Roadside Kitchen",
                        "kind": "meal",
                        "note": "On-route meal break",
                    },
                    {"name": "New York Hotel", "kind": "hotel"},
                    {"name": "Central Park", "kind": "attraction"},
                    {"name": "New York Hotel", "kind": "hotel"},
                ],
            },
        ],
    }

    itinerary = trip_view.build_itinerary(trip)
    bus_stop = next(
        stop for stop in itinerary["days"][0]["stops"]
        if stop["kind"] == "transport" and stop["name"].startswith("Bus:")
    )
    assert bus_stop["route_circuit_id"] == "day-2-stop-2-bus"
    assert [stop["name"] for stop in itinerary["days"][0]["stops"][:7]] == [
        "Boston Hotel",
        "Boston Bus Stand",
        "Bus: Boston Bus Stand to New York Bus Stand",
        "Scenic Hudson Overlook",
        "Roadside Kitchen",
        "New York Bus Stand",
        "New York Hotel",
    ]

    map_view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in map_view["pins"]}
    circuit = map_view["road_circuits"][0]
    assert circuit["id"] == bus_stop["route_circuit_id"]
    assert circuit["mode"] == "Bus"
    assert [pins_by_id[pin_id]["name"] for pin_id in circuit["pin_ids"]] == [
        "Boston Bus Stand",
        "Scenic Hudson Overlook",
        "Roadside Kitchen",
        "New York Bus Stand",
    ]
    assert [waypoint["role"] for waypoint in circuit["waypoints"]] == [
        "origin",
        "scenic",
        "meal",
        "destination",
    ]
    assert circuit["route"]["distance_km"] == 350
    assert circuit["route"]["duration_min"] == 300
    assert all(leg["mode"] == "Bus" and leg["intercity"] for leg in circuit["legs"])
    assert "Central Park" not in {
        pins_by_id[pin_id]["name"] for pin_id in circuit["pin_ids"]
    }
    map_day = map_view["days"][0]
    map_day_names = [pins_by_id[pin_id]["name"] for pin_id in map_day["pin_ids"]]
    assert map_day_names.index("Boston Bus Stand") < map_day_names.index(
        "Scenic Hudson Overlook"
    ) < map_day_names.index("Roadside Kitchen") < map_day_names.index(
        "New York Bus Stand"
    )
    circuit_legs = [
        leg for leg in map_day["legs"] if leg.get("route_circuit_id") == circuit["id"]
    ]
    assert [(leg["from_pin_id"], leg["to_pin_id"]) for leg in circuit_legs] == [
        (start_id, end_id)
        for start_id, end_id in zip(circuit["pin_ids"], circuit["pin_ids"][1:])
    ]
    assert sum(leg["distance_km"] for leg in circuit_legs) == 350
    assert sum(leg["duration_min"] for leg in circuit_legs) == 300


def test_departure_drive_to_airport_builds_zoomable_drive_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hotel->airport departure drive must map even though the next stop is a
    flight (its terminal never tags a following place pin)."""
    coords = {
        "Darjeeling Hotel": (27.047, 88.263),
        "Bagdogra Airport": (26.699, 88.311),
        "Bangalore Airport": (13.199, 77.707),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city, **_kwargs: {
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
        "destination": "Northeast India",
        "selected_hotels": [{"name": "Darjeeling Hotel"}],
        "day_wise_itinerary": [
            {
                "day": 6,
                "stops": [
                    {"name": "Darjeeling Hotel", "kind": "hotel"},
                    {
                        "name": "Darjeeling to Bagdogra",
                        "kind": "other",
                        "mode": "car",
                        "distance_km": 92,
                        "duration_min": 150,
                    },
                    {
                        "name": "Flight: Bagdogra to Bangalore",
                        "kind": "flight",
                        "time": "14:00",
                        "arrival_time": "16:30",
                        "duration_min": 150,
                    },
                ],
            }
        ],
    }

    itinerary = trip_view.build_itinerary(trip)
    drive_row = next(
        stop
        for stop in itinerary["days"][0]["stops"]
        if stop["kind"] == "transport"
    )
    assert drive_row["route_circuit_id"]

    map_view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in map_view["pins"]}
    drive_circuit = next(
        circuit for circuit in map_view["drive_circuits"] if circuit["day"] == 6
    )
    assert drive_circuit["id"] == drive_row["route_circuit_id"]
    assert [pins_by_id[pin_id]["name"] for pin_id in drive_circuit["pin_ids"]] == [
        "Darjeeling Hotel",
        "Bagdogra Airport",
    ]
    assert len(drive_circuit["pin_ids"]) == 2
    assert drive_circuit["route"]["duration_min"] == 150
    assert drive_circuit["route"]["distance_km"] == 92
    assert all(
        leg["route_circuit_id"] == drive_circuit["id"] for leg in drive_circuit["legs"]
    )


def test_chained_drives_build_one_circuit_per_leg_through_waypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A day with two car drives around a mid-way palace must yield two
    independently focusable drive circuits (Rameshwaram -> Padmanabhapuram ->
    Kanyakumari), not a single merged or missing route."""
    coords = {
        "Hyatt Place Rameswaram": (9.2833, 79.3129),
        "Rameshwaram": (9.2876, 79.3129),
        "Padmanabhapuram Palace": (8.2445, 77.3269),
        "Sparsa Kanyakumari": (8.0864, 77.5510),
    }
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city, **_kwargs: {
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
        "destination": "Tamil Nadu",
        "selected_hotels": [
            {"name": "Hyatt Place Rameswaram"},
            {"name": "Sparsa Kanyakumari"},
        ],
        "day_wise_itinerary": [
            {
                "day": 2,
                "stops": [
                    {"name": "Hyatt Place Rameswaram", "kind": "hotel"},
                    {"name": "Ramanathaswamy Temple", "kind": "attraction"},
                ],
            },
            {
                "day": 3,
                "stops": [
                    {
                        "name": "Rameshwaram to Padmanabhapuram",
                        "kind": "other",
                        "mode": "car",
                    },
                    {"name": "Padmanabhapuram Palace", "kind": "attraction"},
                    {
                        "name": "Padmanabhapuram to Kanyakumari",
                        "kind": "other",
                        "mode": "car",
                    },
                    {"name": "Sparsa Kanyakumari", "kind": "hotel"},
                ],
            },
        ],
    }

    map_view = trip_view.build_map_view(trip)
    pins_by_id = {pin["id"]: pin for pin in map_view["pins"]}
    day3_circuits = [
        circuit for circuit in map_view["drive_circuits"] if circuit["day"] == 3
    ]
    circuit_names = [
        [pins_by_id[pin_id]["name"] for pin_id in circuit["pin_ids"]]
        for circuit in day3_circuits
    ]
    assert circuit_names == [
        ["Hyatt Place Rameswaram", "Padmanabhapuram Palace"],
        ["Padmanabhapuram Palace", "Sparsa Kanyakumari"],
    ]
    itinerary = trip_view.build_itinerary(trip)
    drive_ids = [
        stop["route_circuit_id"]
        for stop in itinerary["days"][1]["stops"]
        if stop.get("route_circuit_id")
    ]
    assert [circuit["id"] for circuit in day3_circuits] == drive_ids
    for circuit in day3_circuits:
        assert len(circuit["pin_ids"]) >= 2
        assert all(
            leg["route_circuit_id"] == circuit["id"] for leg in circuit["legs"]
        )


def test_arrival_day_local_outing_returns_to_destination_hotel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
        "Lake Pichola": (24.572, 73.679),
        "City Palace": (24.576, 73.683),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "09:30",
                    "duration_min": 90,
                },
                {
                    "name": "Trident Udaipur",
                    "kind": "hotel",
                    "time": "10:55",
                    "note": "Check-in",
                },
                {
                    "name": "Lake Pichola",
                    "kind": "attraction",
                    "time": "15:00",
                    "duration_min": 90,
                },
                {
                    "name": "City Palace",
                    "kind": "attraction",
                    "time": "17:00",
                    "duration_min": 90,
                },
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    day = itinerary["days"][0]
    hotel_return = day["stops"][-1]
    assert hotel_return["name"] == "Trident Udaipur"
    assert hotel_return["note"] == "Return to your stay"
    assert hotel_return["time"] == day["schedule"]["end"]
    assert hotel_return["time"] > "18:30"
    assert hotel_return["time_estimated"] is True
    assert hotel_return["travel_from_previous"]["duration_min"] > 0


def test_arrival_day_local_transport_does_not_suppress_hotel_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
        "City Palace": (24.576, 73.683),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "09:30",
                    "duration_min": 90,
                },
                {
                    "name": "Trident Udaipur",
                    "kind": "hotel",
                    "time": "10:55",
                    "concern": "Confirm early check-in",
                },
                {"name": "Taxi to City Palace", "kind": "transport"},
                {
                    "name": "City Palace",
                    "kind": "attraction",
                    "time": "17:00",
                    "duration_min": 90,
                },
            ],
        }],
    }

    day = trip_view.build_itinerary(trip)["days"][0]
    stops = day["stops"]

    assert stops[-1]["name"] == "Trident Udaipur"
    assert stops[-1]["note"] == "Return to your stay"
    assert stops[-1]["time"] == day["schedule"]["end"]
    assert stops[-1]["time"] > "18:30"
    assert stops[-1]["travel_from_previous"]["duration_min"] > 0
    assert not stops[-1].get("concern")


def test_arrival_day_local_transport_alone_does_not_add_hotel_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "09:30",
                    "duration_min": 90,
                },
                {"name": "Trident Udaipur", "kind": "hotel", "time": "10:55"},
                {"name": "Taxi to dinner", "kind": "transport"},
            ],
        }],
    }

    stops = trip_view.build_itinerary(trip)["days"][0]["stops"]

    assert [stop["kind"] for stop in stops] == [
        "airport", "flight", "airport", "hotel", "transport"
    ]


def test_arrival_day_does_not_invent_return_without_route_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_view, "_place_coords", lambda name, destination: None)
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "09:30",
                    "duration_min": 90,
                },
                {"name": "Trident Udaipur", "kind": "hotel", "time": "10:55"},
                {
                    "name": "City Palace",
                    "kind": "attraction",
                    "time": "17:00",
                    "duration_min": 90,
                },
            ],
        }],
    }

    stops = trip_view.build_itinerary(trip)["days"][0]["stops"]

    assert stops[-1]["name"] == "City Palace"


def test_arrival_day_return_includes_untimed_local_activity_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
        "Lake Pichola": (24.572, 73.679),
        "City Palace": (24.576, 73.683),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Flight: Bangalore to Udaipur",
                    "kind": "flight",
                    "time": "08:00",
                    "arrival_time": "09:30",
                    "duration_min": 90,
                },
                {"name": "Trident Udaipur", "kind": "hotel", "time": "10:55"},
                {
                    "name": "Lake Pichola",
                    "kind": "attraction",
                    "time": "15:00",
                    "duration_min": 90,
                },
                {"name": "City Palace", "kind": "attraction", "duration_min": 90},
            ],
        }],
    }

    day = trip_view.build_itinerary(trip)["days"][0]
    lake, city, hotel_return = day["stops"][-3:]
    expected_return = (
        trip_view._clock_minutes(lake["time"])
        + lake["duration_min"]
        + city["travel_from_previous"]["duration_min"]
        + city["duration_min"]
        + hotel_return["travel_from_previous"]["duration_min"]
    )

    assert hotel_return["time"] == trip_view._clock_display(expected_return)


def test_local_route_uses_taxi_for_three_kilometres() -> None:
    route = trip_view._route_stats_for_distance(
        3.0,
        from_name="Hotel Hillock Mount Abu",
        to_name="Dilwara Temples",
    )

    assert route["mode"] == "Taxi"


def test_local_route_keeps_short_walks_walkable() -> None:
    route = trip_view._route_stats_for_distance(
        1.0,
        from_name="Hotel Hillock Mount Abu",
        to_name="Nakki Lake",
    )

    assert route["mode"] == "Walk"


def test_flight_arrival_and_airport_buffers_use_configured_estimates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bangalore Airport": (13.1986, 77.7066),
        "Udaipur Airport": (24.6177, 73.8961),
        "Trident Udaipur": (24.577, 73.683),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    monkeypatch.setattr(
        trip_view,
        "get_settings",
        lambda: SimpleNamespace(
            airport_departure_buffer_min=150,
            airport_arrival_buffer_min=35,
            flight_duration_default_min=90,
        ),
    )
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [{
                "name": "Flight: Bangalore to Udaipur",
                "kind": "flight",
                "time": "08:00",
                "duration_min": 70,
            }, {"name": "Trident Udaipur", "kind": "hotel"}],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    departure_airport, flight, arrival_airport, hotel = itinerary["days"][0]["stops"]
    assert departure_airport["time"] == "05:30"
    assert departure_airport["duration_min"] == 150
    assert departure_airport["operational_time_display"] == "2 hr 30 min check-in and security"
    assert flight["time"] == "08:00"
    assert flight["departure_time"] == "09:10"
    assert flight["duration_min"] == 70
    assert arrival_airport["time"] == "09:10"
    assert arrival_airport["time_estimated"] is True
    assert arrival_airport["duration_min"] == 35
    assert arrival_airport["operational_time_display"] == "35 min baggage and airport exit"
    assert hotel["time"] > "09:45"


def test_train_arrival_estimates_destination_hotel_check_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Bhopal Railway Station": (23.2683, 77.4045),
        "Jehan Numa Palace Hotel": (23.2455, 77.3937),
        "Upper Lake": (23.2469, 77.3606),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "Jehan Numa Palace Hotel"}],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {
                    "name": "Train: Delhi to Bhopal",
                    "kind": "transport",
                    "time": "06:00",
                    "arrival_time": "14:00",
                },
                {"name": "Jehan Numa Palace Hotel", "kind": "hotel"},
                {"name": "Upper Lake", "kind": "attraction"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    stops = itinerary["days"][0]["stops"]
    arrival_station = next(stop for stop in stops if stop.get("terminal_role") == "arrival")
    hotel = next(stop for stop in stops if stop["kind"] == "hotel")
    assert arrival_station["kind"] == "station"
    assert arrival_station["time"] == "14:00"
    expected_check_in = (
        trip_view._clock_minutes("14:00")
        + int(arrival_station["duration_min"])
        + int(hotel["travel_from_previous"]["duration_min"])
    )
    assert hotel["time"] == trip_view._clock_display(expected_check_in)
    assert hotel["time_estimated"] is True


def test_train_without_duration_keeps_arrival_unknown() -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [{
                "name": "Train: Delhi to Amritsar",
                "kind": "transport",
                "time": "09:00",
            }],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    stops = itinerary["days"][0]["stops"]
    train = next(stop for stop in stops if stop["kind"] == "transport")
    arrival_station = next(stop for stop in stops if stop.get("terminal_role") == "arrival")
    assert train["arrival_time"] == ""
    assert "arrival_time_estimated" not in train
    assert arrival_station["time"] == ""
    assert arrival_station["time_estimated"] is False


def test_timed_road_transfer_estimates_destination_hotel_check_in() -> None:
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Hotel Hillock Mount Abu"},
        ],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {"name": "Trident Udaipur", "kind": "hotel"},
                {
                    "name": "Drive: Udaipur to Mount Abu",
                    "kind": "transport",
                    "time": "09:00",
                    "duration_min": 180,
                },
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    hotel = itinerary["days"][0]["stops"][-1]
    assert hotel["time"] == "12:00"
    assert hotel["time_estimated"] is True


def test_city_origin_drive_includes_origin_and_rest_break() -> None:
    trip = {
        **SAMPLE_TRIP,
        "origin": "Bangalore",
        "destination": "Coorg",
        "preferences_snapshot": {
            "transport_preferences": {
                "max_continuous_drive_min": 180,
                "road_break_duration_min": 30,
                "road_break_preferences": ["snack", "restroom"],
            },
        },
        "selected_hotels": [{"name": "Coorg Wilderness Resort"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {
                    "name": "Drive: Bangalore to Coorg",
                    "kind": "transport",
                    "time": "08:00",
                    "duration_min": 300,
                },
                {"name": "Coorg Wilderness Resort", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    origin, drive, hotel = itinerary["days"][0]["stops"]
    assert (origin["name"], origin["kind"]) == ("Bangalore", "origin")
    assert drive["duration_min"] == 300
    assert drive["operational_time_display"] == (
        "5 hrs drive incl. one 30 min snack/restroom break"
    )
    assert hotel["time"] == "13:00"


def test_road_transfer_estimates_duration_arrival_and_hotel_check_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Trident Udaipur": (24.577, 73.683),
        "Hotel Hillock Mount Abu": (24.592, 72.708),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Hotel Hillock Mount Abu"},
        ],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {
                    "name": "Trident Udaipur",
                    "kind": "hotel",
                    "time": "09:00",
                },
                {"name": "Drive: Udaipur to Mount Abu", "kind": "transport"},
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    _, drive, hotel = itinerary["days"][0]["stops"]
    assert drive["time"] == "09:00"
    assert drive["time_estimated"] is True
    assert drive["duration_min"] > 0
    assert drive["duration_estimated"] is True
    assert drive["departure_time"]
    assert hotel["time"] == drive["departure_time"]
    assert hotel["time_estimated"] is True


def test_road_transfer_without_checkout_estimates_duration_but_not_check_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Trident Udaipur": (24.577, 73.683),
        "Hotel Hillock Mount Abu": (24.592, 72.708),
    }
    monkeypatch.setattr(
        trip_view,
        "_place_coords",
        lambda name, destination: coords.get(name),
    )
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Hotel Hillock Mount Abu"},
        ],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {"name": "Trident Udaipur", "kind": "hotel"},
                {"name": "Drive: Udaipur to Mount Abu", "kind": "transport"},
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    _, drive, hotel = itinerary["days"][0]["stops"]
    assert drive["duration_min"] > 0
    assert drive["duration_estimated"] is True
    assert drive["time"] == ""
    assert hotel["time"] == ""
    assert "time_estimated" not in hotel


def test_untimed_road_transfer_does_not_invent_hotel_check_in() -> None:
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [
            {"name": "Trident Udaipur"},
            {"name": "Hotel Hillock Mount Abu"},
        ],
        "day_wise_itinerary": [{
            "day": 3,
            "stops": [
                {"name": "Trident Udaipur", "kind": "hotel"},
                {"name": "Drive: Udaipur to Mount Abu", "kind": "transport"},
                {"name": "Hotel Hillock Mount Abu", "kind": "hotel"},
            ],
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    hotel = itinerary["days"][0]["stops"][-1]
    assert hotel["time"] == ""
    assert "time_estimated" not in hotel


def test_structured_itinerary_preserves_explicit_hotel_transition() -> None:
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "North Goa Stay"}, {"name": "South Goa Stay"}],
        "day_wise_itinerary": [
            {
                "day": 2,
                "stops": [
                    {"name": "North Goa Stay", "kind": "hotel"},
                    {"name": "Old Goa", "kind": "attraction"},
                    {"name": "South Goa Stay", "kind": "hotel"},
                ],
            }
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    assert [stop["name"] for stop in itinerary["days"][0]["stops"]] == [
        "North Goa Stay",
        "Old Goa",
        "South Goa Stay",
    ]
