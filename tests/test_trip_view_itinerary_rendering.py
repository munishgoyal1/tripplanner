"""Trip-view itinerary rendering and schedule tests."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.trip_view import SAMPLE_TRIP
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


def test_build_itinerary_route_uses_all_stop_names(monkeypatch: pytest.MonkeyPatch) -> None:
    coords = {
        "kaali maa pujo pandal": (22.58, 88.36),
        "victoria memorial": (22.5448, 88.3426),
        "peter cat": (22.5532, 88.3525),
    }

    def fake_summary(name: str, city: str, **_kw: Any) -> dict[str, Any] | None:
        c = coords.get(str(name).strip().lower())
        if not c:
            return {"name": name}
        return {"name": name, "lat": c[0], "lng": c[1]}

    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)

    trip = {
        "destination": "Kolkata",
        "selected_hotels": [],
        "selected_activities": [],
        "day_wise_itinerary": [
            {
                "day": 2,
                "title": "Day 2",
                "stops": [
                    {"name": "Kaali Maa Pujo Pandal", "kind": "attraction", "time": "09:30"},
                    {"name": "Victoria Memorial", "kind": "attraction", "time": "14:00"},
                    {"name": "Peter Cat", "kind": "meal", "time": "19:00"},
                ],
            }
        ],
    }

    it = trip_view.build_itinerary(trip)
    day = it["days"][0]
    assert day["route"]["distance_km"] > 0
    assert day["route"]["duration_min"] > 0


def test_itinerary_schedule_estimates_complete_hotel_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "hotel": (51.5098, -0.1222),
        "riverside walk": (51.4830, -0.1350),
        "dinner": (51.5130, -0.1364),
    }

    def fake_details(name: str, _city: str) -> dict[str, Any]:
        lat, lng = coords[name.lower()]
        return {
            "name": name,
            "lat": lat,
            "lng": lng,
            "rating": 4.7,
            "review_count": 12500,
        }

    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *args, **kwargs: None)
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_details)
    itinerary = trip_view.build_itinerary({
        "destination": "London",
        "selected_hotels": [{"name": "Hotel"}],
        "selected_activities": [],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Hotel", "kind": "hotel"},
                {
                    "name": "Riverside Walk",
                    "kind": "attraction",
                    "time": "16:00",
                    "duration_min": 90,
                },
                {"name": "Dinner", "kind": "meal", "time": "19:00", "duration_min": 60},
                {"name": "Hotel", "kind": "hotel"},
            ],
        }],
    })

    day = itinerary["days"][0]
    assert day["stops"][0]["duration_min"] is None
    assert day["stops"][-1]["duration_min"] is None
    assert day["stops"][0]["time"] == day["schedule"]["start"]
    assert day["stops"][0]["time_estimated"] is True
    assert day["stops"][1]["departure_time"] == "17:30"
    assert day["stops"][2]["expected_arrival_time"] != "19:00"
    assert day["stops"][2]["buffer_before_min"] > 0
    assert day["stops"][1]["rating"] == 4.7
    assert day["stops"][1]["review_count"] == 12500
    assert day["stops"][1]["popularity_score"] >= 80
    assert "Hotel" in day["stops"][1]["travel_from_previous"]["detail"]
    assert "Riverside Walk" in day["stops"][1]["travel_from_previous"]["detail"]
    assert day["schedule"]["start"]
    assert day["schedule"]["end"]
    assert day["schedule"]["duration_min"] > 240
    assert day["schedule"]["travel_duration_min"] == day["route"]["duration_min"]
    assert day["schedule"]["estimated"] is True


def test_itinerary_exposes_timing_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    coords = {
        "museum": (51.5098, -0.1222),
        "dinner": (51.5130, -0.1364),
    }

    def fake_details(name: str, _city: str) -> dict[str, Any]:
        lat, lng = coords[name.lower()]
        return {"name": name, "lat": lat, "lng": lng}

    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *args, **kwargs: None)
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_details)
    itinerary = trip_view.build_itinerary({
        "destination": "London",
        "selected_hotels": [],
        "selected_activities": [],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Museum", "kind": "attraction", "time": "10:00", "duration_min": 120},
                {"name": "Dinner", "kind": "meal", "time": "11:00", "duration_min": 60},
            ],
        }],
    })

    dinner = itinerary["days"][0]["stops"][1]
    assert dinner["expected_arrival_time"] > "12:00"
    assert dinner["timing_conflict_min"] > 60
    assert dinner["timing_conflict_display"]


def test_build_itinerary_prefetches_stop_details_without_reviews(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[set[str], str, int, bool]] = []

    def fake_prefetch(
        names: list[str], city: str, *, max_photos: int, with_reviews: bool
    ) -> None:
        calls.append((set(names), city, max_photos, with_reviews))

    monkeypatch.setattr(trip_view.places_cache, "prefetch", fake_prefetch)
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {"name": name, "lat": 1.0, "lng": 2.0},
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_summary",
        lambda *args, **kwargs: pytest.fail("itinerary should not fetch reviews"),
    )

    result = trip_view.build_itinerary(
        {
            "destination": "Goa",
            "selected_hotels": [{"name": "Hotel A"}],
            "selected_activities": [],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Hotel A", "kind": "hotel"},
                        {"name": "Fort Aguada", "kind": "attraction"},
                    ],
                }
            ],
        }
    )

    assert result["stats"]["stops"] == 3
    assert calls == [({"Hotel A", "Fort Aguada"}, "Goa", 0, False)]


def test_itinerary_empty_when_no_days() -> None:
    it = trip_view.build_itinerary(
        {
            **SAMPLE_TRIP,
            "day_wise_itinerary": [],
            "selected_hotels": [],
            "selected_activities": [],
        }
    )
    assert it["has_itinerary"] is False
    assert it["days"] == []
    assert it["stats"] == {"days": 0, "stops": 0, "booked": 0}


def test_itinerary_falls_back_to_selections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    # No structured day_wise_itinerary, but the trip has selections — the panel
    # should still render an intelligent first-draft itinerary from selections.
    it = trip_view.build_itinerary({**SAMPLE_TRIP, "day_wise_itinerary": []})
    assert it["has_itinerary"] is True
    # 1 attraction over a 5-night trip → a single day (we never emit empty days).
    assert it["stats"]["days"] == 1
    day = it["days"][0]
    names = [s["name"] for s in day["stops"]]
    assert "Taj Exotica Resort" in names
    assert "Dudhsagar Falls Trek" in names
    # hotel listed before attraction; both marked selected
    assert day["stops"][0]["kind"] == "hotel"
    assert all(s["selected"] for s in day["stops"])
    attraction = next(stop for stop in day["stops"] if stop["kind"] == "attraction")
    assert attraction["rating"] == 4.5
    assert attraction["review_count"] == 1234
    assert attraction["popularity_score"] >= 80
    assert attraction["travel_from_previous"]["mode"] in {"Walk", "Taxi"}
    assert "Taj Exotica Resort" in attraction["travel_from_previous"]["detail"]
    assert "Dudhsagar Falls Trek" in attraction["travel_from_previous"]["detail"]
    assert it["stats"]["stops"] == len(day["stops"])
    assert "google.com/maps" in day["google_maps_url"]


def test_itinerary_synthesizes_multiple_days() -> None:
    # Several selected attractions over a multi-night trip should be spread
    # across multiple day clusters (not dumped into one flat day).
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [],
        "selected_activities": [
            {"name": "Aguada Fort"},
            {"name": "Calangute Beach"},
            {"name": "Basilica of Bom Jesus"},
            {"name": "Dudhsagar Falls Trek"},
        ],
    }
    it = trip_view.build_itinerary(trip)
    assert it["has_itinerary"] is True
    assert it["stats"]["days"] >= 2
    # every selected attraction appears exactly once across the days
    placed = [
        s["name"]
        for d in it["days"]
        for s in d["stops"]
        if s["kind"] == "attraction"
    ]
    assert sorted(placed) == [
        "Aguada Fort",
        "Basilica of Bom Jesus",
        "Calangute Beach",
        "Dudhsagar Falls Trek",
    ]
    # Every ordinary day starts and returns to the selected stay.
    assert all(d["stops"][0]["kind"] == "hotel" for d in it["days"])
    assert all(d["stops"][-1]["kind"] == "hotel" for d in it["days"])


def test_structured_itinerary_adds_selected_hotel_as_daily_circuit_anchor() -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Aguada Fort", "kind": "attraction"}]},
            {"day": 2, "stops": [{"name": "Calangute Beach", "kind": "attraction"}]},
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    for day in itinerary["days"]:
        assert [stop["name"] for stop in day["stops"]] == [
            "Taj Exotica Resort",
            day["stops"][1]["name"],
            "Taj Exotica Resort",
        ]
        assert day["stops"][0]["note"] == "Start from your stay"
        assert day["stops"][-1]["note"] == "Return to your stay"


def test_structured_hotel_only_day_does_not_add_return_endpoint() -> None:
    trip = {
        **SAMPLE_TRIP,
        "destination": "Mysore",
        "selected_hotels": [{"name": "Radisson Blu Plaza Hotel Mysore"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Radisson Blu Plaza Hotel Mysore",
                        "kind": "hotel",
                    }
                ],
            }
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    assert [stop["name"] for stop in itinerary["days"][0]["stops"]] == [
        "Radisson Blu Plaza Hotel Mysore"
    ]


def test_structured_itinerary_preserves_same_hotel_return_metadata() -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Taj Exotica Resort", "kind": "hotel", "note": "Leave bags"},
                    {"name": "Aguada Fort", "kind": "attraction"},
                    {
                        "name": "Taj Exotica Resort",
                        "kind": "hotel",
                        "note": "Collect bags at reception",
                        "concern": "Confirm late front-desk access",
                    },
                ],
            }
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    hotel_return = itinerary["days"][0]["stops"][-1]
    assert hotel_return["note"] == "Collect bags at reception"
    assert hotel_return["concern"] == "Confirm late front-desk access"


def test_structured_itinerary_preserves_overnight_travel_without_hotel_anchor() -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "title": "Overnight train to Goa",
                "stops": [{"name": "Konkan sleeper", "kind": "transport"}],
            }
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    assert [stop["kind"] for stop in itinerary["days"][0]["stops"]] == ["transport"]


def test_itinerary_structured_stops(_map_geo: None) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2026-01-10",
                "title": "Arrival",
                "summary": "land and relax",
                "stops": [
                    {"name": "Taj Exotica Resort", "kind": "hotel", "booked": True},
                    {
                        "name": "Dudhsagar Falls Trek",
                        "kind": "attraction",
                        "time": "14:00",
                        "duration_min": 120,
                        "note": "carry water",
                    },
                ],
            },
            {"day": 2, "plan": "beach day", "stops": ["Dudhsagar Falls Trek"]},
        ],
    }
    it = trip_view.build_itinerary(trip)
    assert it["has_itinerary"] is True
    assert it["stats"] == {"days": 2, "stops": 6, "booked": 1}

    d1 = it["days"][0]
    assert d1["title"] == "Arrival"
    assert d1["date"] == "2026-01-10"
    assert d1["summary"] == "land and relax"
    hotel = d1["stops"][0]
    assert hotel["kind"] == "hotel"
    assert hotel["booked"] is True
    assert hotel["selected"] is True  # cross-referenced with selected_hotels
    act = d1["stops"][1]
    assert act["time"] == "14:00"
    assert act["duration_min"] == 120
    assert act["note"] == "carry water"
    assert act["selected"] is True
    assert d1["route"] is not None
    assert d1["route"]["distance_display"]
    assert d1["stops"][1]["travel_from_previous"]["distance_display"]
    assert d1["stops"][1]["travel_from_previous"]["duration_display"]
    assert "google.com/maps" in d1["google_maps_url"]
    # day colors differ
    assert it["days"][0]["color"] != it["days"][1]["color"]


def test_itinerary_string_stops_normalize() -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [{"day": 1, "stops": ["Some Random Cafe", ""]}],
    }
    it = trip_view.build_itinerary(trip)
    stops = it["days"][0]["stops"]
    assert len(stops) == 3  # blank dropped; hotel anchors the daily circuit
    s = stops[1]
    assert s["name"] == "Some Random Cafe"
    assert s["kind"] == "attraction"
    assert s["booked"] is False
    assert s["selected"] is False


def test_itinerary_title_falls_back_to_day_number() -> None:
    trip = {**SAMPLE_TRIP, "day_wise_itinerary": [{"day": 3, "plan": "x"}]}
    it = trip_view.build_itinerary(trip)
    assert it["days"][0]["title"] == "Day 3"
    assert it["days"][0]["day"] == 3
