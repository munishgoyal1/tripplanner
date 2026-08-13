"""Tests for the pure-Python trip view-model (``tripplanner.web.trip_view``).

These run with NO UI context — proving the view-model is fully
decoupled from the frontend. Places lookups are monkeypatched so we never
touch the network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tripplanner.web import trip_view

SAMPLE_TRIP: dict[str, Any] = {
    "status": "draft",
    "destination": "Goa",
    "origin": "Bengaluru",
    "departure_date": "2026-01-10",
    "return_date": "2026-01-15",
    "travelers": "2 adults",
    "notes": "Beach holiday",
    "selected_flights": [{"airline": "IndiGo", "price": 8500}],
    "selected_hotels": [{"name": "Taj Exotica Resort", "price": 12000}],
    "selected_activities": [{"name": "Dudhsagar Falls Trek"}],
    "day_wise_itinerary": [{"day": 1}, {"day": 2}],
    "total_cost": 82000,
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    coords = {
        "taj exotica resort": (15.04, 73.92),
        "dudhsagar falls trek": (15.31, 74.31),
        "aguada fort": (15.498, 73.773),
        "calangute beach": (15.5439, 73.7553),
        "basilica of bom jesus": (15.5009, 73.9110),
    }

    def fake_photos(name: str, city: str, max_photos: int = 3, **_kw: Any) -> list[str]:
        return [f"https://example.test/{name}/{i}.jpg" for i in range(min(max_photos, 2))]

    def fake_summary(name: str, city: str, **_kw: Any) -> dict[str, Any] | None:
        return {
            "place_id": f"pid-{name}",
            "name": name,
            "rating": 4.5,
            "review_count": 1234,
            "editorial_summary": f"{name} in {city} is great.",
            "website": "https://example.test/",
            "reviews": [{"rating": 5, "text": "Loved it!", "author": "Asha"}],
        }

    def fake_top(destination: str, kind: str, n: int = 4) -> list[str]:
        base = {"hotel": ["Grand Hyatt", "ITC Grand"], "attraction": ["Fort Aguada", "Dudhsagar"]}
        return base.get(kind, [])[:n]

    def fake_coords(name: str, city: str = "") -> tuple[float, float] | None:
        return coords.get(str(name).strip().lower())

    monkeypatch.setattr(trip_view.places_cache, "get_photos", fake_photos)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "place_coords", fake_coords)
    monkeypatch.setattr(trip_view.places_cache, "top_places", fake_top)
    monkeypatch.setattr(trip_view.user_preferences, "load_preferences", lambda: {})


def test_no_trip_returns_empty_state() -> None:
    view = trip_view.build_view(None, None)
    assert view["has_trip"] is False
    assert view["items"] == []
    assert view["empty_message"]


def test_build_view_overview_and_items() -> None:
    view = trip_view.build_view(SAMPLE_TRIP, None)
    assert view["has_trip"] is True
    assert view["destination"] == "Goa"
    assert view["is_fallback"] is False
    assert view["available_days"] == [1, 2]
    o = view["overview"]
    assert o["counts"] == {"flights": 1, "hotels": 1, "activities": 1, "days": 2}
    assert o["total_cost_display"] == "\u20b982,000"
    names = {i["name"] for i in view["items"]}
    assert "Taj Exotica Resort" in names
    assert "Dudhsagar Falls Trek" in names
    hotel = next(i for i in view["items"] if i["name"] == "Taj Exotica Resort")
    assert hotel["selected"] is True
    assert hotel["photos"]
    assert hotel["reviews"]


def test_build_weather_normalizes_forecast_and_packing() -> None:
    weather = trip_view.build_weather(
        {
            "weather": {
                "source": "forecast",
                "days": [
                    {
                        "date": "2026-07-14",
                        "summary": "Heavy rain",
                        "high_c": 30,
                        "low_c": 24,
                        "precip_mm": 18,
                        "precip_probability_pct": 85,
                    }
                ],
            }
        }
    )

    assert weather is not None
    assert weather["source_label"] == "Live forecast"
    assert weather["days"][0]["condition"] == "rain"
    assert weather["days"][0]["high_c"] == 30
    assert any("breathable" in item for item in weather["packing_advice"])
    assert any("umbrella" in item for item in weather["packing_advice"])


def test_build_weather_labels_agent_fallback_honestly() -> None:
    weather = trip_view.build_weather(
        {
            "weather": {
                "source": "agent_climate_estimate",
                "note": "Open-Meteo was unavailable.",
                "days": [
                    {"date": "2026-12-02", "summary": "Typically cool", "high_c": 17, "low_c": 8}
                ],
            }
        }
    )

    assert weather is not None
    assert weather["source_label"] == "Typical monthly pattern"
    assert weather["note"] == "Open-Meteo was unavailable."
    assert any("jacket" in item for item in weather["packing_advice"])


def test_itinerary_matches_weather_to_day_date() -> None:
    trip = {
        **SAMPLE_TRIP,
        "weather": {
            "source": "seasonal_estimate",
            "days": [
                {"date": "2026-01-10", "summary": "Clear", "high_c": 27, "low_c": 18},
                {"date": "2026-01-11", "summary": "Rain", "high_c": 25, "low_c": 17},
            ],
        },
        "day_wise_itinerary": [
            {"day": 1, "date": "2026-01-10", "stops": []},
            {"day": 2, "date": "2026-01-11", "stops": []},
        ],
    }

    itinerary = trip_view.build_itinerary(trip)

    assert itinerary["days"][0]["weather"]["condition"] == "clear"
    assert itinerary["days"][1]["weather"]["condition"] == "rain"


def test_overview_counts_unique_itinerary_places() -> None:
    trip = {
        "selected_flights": [],
        "selected_hotels": [{"name": "Hotel A"}],
        "selected_activities": [{"name": "Fort Aguada"}],
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Hotel A", "kind": "hotel"},
                    {"name": "Fort Aguada", "kind": "attraction"},
                    {"name": "Britto's", "kind": "meal"},
                    {"name": "Taxi", "kind": "transport"},
                    {"name": "Hotel A", "kind": "hotel"},
                ],
            },
            {"day": 2, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
        ],
    }

    assert trip_view._build_overview(trip)["counts"] == {
        "flights": 0,
        "hotels": 1,
        "activities": 2,
        "days": 2,
    }


def test_itinerary_only_place_reads_as_in_trip() -> None:
    """A place woven into the day-by-day itinerary but absent from the selected
    buckets should still surface as ``selected`` so the panel shows Remove."""
    trip = {
        "status": "draft",
        "destination": "Goa",
        "selected_hotels": [],
        "selected_activities": [],
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]}
        ],
    }
    view = trip_view.build_view(trip, None)
    fort = next(i for i in view["items"] if i["name"] == "Fort Aguada")
    assert fort["selected"] is True


def test_fallback_uses_destination_highlights() -> None:
    trip = {"status": "draft", "destination": "Goa", "selected_hotels": [], "selected_activities": []}
    view = trip_view.build_view(trip, None)
    assert view["is_fallback"] is True
    names = {i["name"] for i in view["items"]}
    assert "Grand Hyatt" in names
    assert "Fort Aguada" in names
    for item in view["items"]:
        assert item["selected"] is False


def test_focus_zooms_single_item() -> None:
    view = trip_view.build_view(SAMPLE_TRIP, {"kind": "hotel", "name": "Taj Exotica Resort"})
    assert view["is_fallback"] is False
    assert len(view["items"]) >= 1
    assert view["items"][0]["name"] == "Taj Exotica Resort"
    assert any(i["name"] != "Taj Exotica Resort" for i in view["items"])  # keeps alternatives visible
    assert view["title"].endswith("Taj Exotica Resort")


def test_airport_focus_exposes_place_details_and_terminal_occurrence() -> None:
    trip = {
        "destination": "Rajasthan",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Flight: Bengaluru Airport to Udaipur Airport",
                        "kind": "flight",
                        "time": "08:00",
                    }
                ],
            }
        ],
    }

    view = trip_view.build_view(
        trip,
        {"kind": "airport", "name": "Udaipur Airport", "day": 1, "stop": 1},
    )

    airport = view["items"][0]
    assert airport["kind"] == "airport"
    assert airport["name"] == "Udaipur Airport"
    assert airport["rating"] == 4.5
    assert airport["photos"]
    assert airport["reviews"] == [{"rating": 5, "text": "Loved it!", "author": "Asha"}]
    assert airport["occurrences"] == [{"day": 1, "stop": 1, "time": "08:00"}]


def test_fmt_money_default_rupee() -> None:
    assert trip_view.fmt_money(82000) == "\u20b982,000"
    assert trip_view.fmt_money(0) == "\u2014"
    assert trip_view.fmt_money(None) == "\u2014"


# ---- budget meter ---------------------------------------------------------


def test_build_budget_none_when_no_spend_or_target() -> None:
    assert trip_view.build_budget(None) is None
    assert trip_view.build_budget({"destination": "Goa"}) is None


def test_build_budget_spent_without_target() -> None:
    b = trip_view.build_budget(SAMPLE_TRIP)
    assert b is not None
    assert b["spent"] == 82000
    assert b["currency"] == "\u20b9"
    assert b["travelers"] == 2
    assert b["per_traveler"] == 41000
    assert b["target"] is None
    assert b["pct_used"] is None
    assert b["over_budget"] is False
    # breakdown sums per-item prices for the categories that have them
    assert b["breakdown"]["flights"] == 8500
    assert b["breakdown"]["hotels"] == 12000
    assert "activities" not in b["breakdown"]


def test_build_budget_with_target_under() -> None:
    trip = {**SAMPLE_TRIP, "budget": 100000, "total_cost": 80000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["target"] == 100000
    assert b["remaining"] == 20000
    assert b["pct_used"] == 80
    assert b["over_budget"] is False


def test_build_budget_accepts_structured_user_owned_target() -> None:
    trip = {
        **SAMPLE_TRIP,
        "currency": "USD",
        "total_cost": 8000,
        "budget": {
            "amount": 10000,
            "currency": "USD",
            "owner": "user",
            "updated_at": "2026-08-10T17:55:00Z",
        },
    }

    budget = trip_view.build_budget(trip)

    assert budget is not None
    assert budget["target"] == 10000
    assert budget["target_currency"] == "USD"
    assert budget["target_owner"] == "user"
    assert budget["target_updated_at"] == "2026-08-10T17:55:00Z"
    assert budget["remaining"] == 2000


def test_build_budget_over_target() -> None:
    trip = {**SAMPLE_TRIP, "budget": 60000, "total_cost": 82000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["over_budget"] is True
    assert b["remaining"] == -22000
    assert b["remaining_display"] == "\u20b922,000"  # absolute value for display


def test_build_budget_respects_currency() -> None:
    trip = {**SAMPLE_TRIP, "currency": "USD", "total_cost": 3000}
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["currency"] == "$"
    assert b["spent_display"] == "$3,000"


def test_build_budget_falls_back_to_item_sum() -> None:
    trip = {
        "destination": "Goa",
        "travelers": "2 adults, 1 child (ages 5)",
        "selected_flights": [{"price": "\u20b910,000"}],
        "selected_hotels": [{"name": "X", "price": 5000}],
        "selected_activities": [],
        "total_cost": 0,
    }
    b = trip_view.build_budget(trip)
    assert b is not None
    assert b["spent"] == 15000
    assert b["travelers"] == 3  # ages 5 not counted as a head


def test_traveler_count_parsing() -> None:
    assert trip_view.traveler_count("2 adults") == 2
    assert trip_view.traveler_count("2 adults, 1 child (ages 5)") == 3
    assert trip_view.traveler_count("") == 1
    assert trip_view.traveler_count(4) == 4


def test_overview_includes_budget() -> None:
    view = trip_view.build_view({**SAMPLE_TRIP, "budget": 100000}, None)
    assert view["overview"]["budget"]["target"] == 100000
    assert view["overview"]["budget"]["estimated"] is True
    assert view["overview"]["budget"]["evidence_coverage_pct"] == 0


def test_budget_headroom_is_verified_only_with_complete_live_evidence() -> None:
    evidence = {"complete": True, "coverage_pct": 100, "priced_total": 8000}
    budget = trip_view.build_budget(
        {"currency": "USD", "total_cost": 8000, "budget": 10000},
        cost_evidence=evidence,
    )

    assert budget is not None
    assert budget["estimated"] is False
    assert budget["evidence_coverage_pct"] == 100
    assert budget["verified_spent"] == 8000


def test_structured_target_uses_published_fx_provenance(monkeypatch) -> None:
    from datetime import UTC, datetime

    from tripplanner.providers import fx

    # Seeded relative to now: a fixed timestamp ages past the rate TTL and the
    # test then silently reaches the live rate service.
    fetched_at = datetime.now(UTC)
    monkeypatch.setitem(
        fx._cache,
        "EUR",
        fx.RateTable(
            base="EUR",
            rates={"USD": 1.2},
            fetched_at=fetched_at,
            rate_date="2026-08-10",
        ),
    )
    budget = trip_view.build_budget(
        {
            "currency": "USD",
            "total_cost": 6000,
            "budget": {"amount": 10000, "currency": "EUR", "owner": "user"},
        }
    )

    assert budget is not None
    assert budget["target"] == 12000
    assert budget["target_fx"]["rate"] == 1.2
    assert budget["target_fx"]["rate_date"] == "2026-08-10"


# ---- family_pills ---------------------------------------------------------


def test_family_pills_empty_when_no_prefs() -> None:
    assert trip_view.family_pills(None) == []
    assert trip_view.family_pills({}) == []


def test_family_pills_kids_seniors_pets_diet_accessibility() -> None:
    prefs = {
        "family_members": [
            {"relationship": "spouse", "name": "A", "age": 38, "dietary": "vegetarian"},
            {"relationship": "daughter", "name": "R", "age": 6},
            {"relationship": "son", "name": "K", "age": 10},
            {"relationship": "father", "name": "P", "age": 72, "mobility": "uses walking stick"},
            {"relationship": "dog", "name": "Bruno"},
        ],
        "food_preferences": {"dietary": ["jain"]},
        "accessibility_needs": ["wheelchair access"],
    }
    pills = trip_view.family_pills(prefs)
    joined = " | ".join(pills)
    assert "Kid-friendly (ages 6,10)" in joined
    assert "Senior-friendly" in joined and "uses walking stick" in joined
    assert "Pet-friendly" in joined
    assert "Vegetarian" in joined and "Jain" in joined
    assert "Wheelchair Access" in joined


def test_family_pills_teen_bucket() -> None:
    prefs = {"family_members": [{"relationship": "son", "name": "T", "age": 15}]}
    pills = trip_view.family_pills(prefs)
    assert any("Teen-friendly" in p for p in pills)
    assert not any("Kid-friendly" in p for p in pills)


def test_family_pills_surfaced_in_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        trip_view.user_preferences,
        "load_preferences",
        lambda: {"family_members": [{"relationship": "daughter", "name": "R", "age": 7}]},
    )
    view = trip_view.build_view(SAMPLE_TRIP, None)
    pills = view["overview"]["family_pills"]
    assert any("Kid-friendly" in p for p in pills)


# ---- build_map_view -------------------------------------------------------


@pytest.fixture
def _map_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Geocoded place lookups for the map view (lat/lng per known name)."""
    coords = {
        "Taj Exotica Resort": (15.04, 73.92),
        "Dudhsagar Falls Trek": (15.31, 74.31),
        "Gateway of India": (18.9218, 72.8347),
        "Colaba Causeway": (18.9228, 72.8315),
        "Marine Drive": (18.9440, 72.8238),
        "Grand Hyatt": (15.46, 73.83),
        "ITC Grand": (15.50, 73.82),
        "Fort Aguada": (15.49, 73.77),
        "Dudhsagar": (15.31, 74.31),
        "Goa International Airport": (15.38, 73.83),
    }

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
        lat, lng = coords.get(name, (None, None))
        return {"place_id": f"pid-{name}", "name": name, "rating": 4.4,
                "address": f"{name}, {city}", "lat": lat, "lng": lng}

    def fake_top(destination: str, kind: str, n: int = 4) -> list[str]:
        base = {"hotel": ["Grand Hyatt", "ITC Grand"], "attraction": ["Fort Aguada", "Dudhsagar"]}
        return base.get(kind, [])[:n]

    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", fake_top)
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")


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
                {"name": "Riverside Walk", "kind": "attraction", "time": "16:00", "duration_min": 90},
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


def test_map_view_rejects_coordinates_from_a_mismatched_provider_place(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, city: {
            "place_id": "padmanabhapuram-palace",
            "name": "Padmanabhapuram Palace",
            "address": "Thuckalay, Tamil Nadu",
            "lat": 8.2507,
            "lng": 77.3260,
        },
    )
    trip = {
        "destination": "Kanyakumari",
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [{"name": "Kanyakumari Beach", "kind": "attraction"}],
        }],
    }

    view = trip_view.build_map_view(trip)

    assert view["pins"] == []


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


def test_map_view_falls_back_to_stays_when_one_flight_terminal_is_unmapped(
    _map_geo: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coords = {
        "Origin Hotel": (13.05, 77.59),
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
        "selected_hotels": [{"name": "Origin Hotel"}, {"name": "Destination Hotel"}],
        "day_wise_itinerary": [{
            "day": 1,
            "stops": [
                {"name": "Origin Hotel", "kind": "hotel"},
                {"name": "Flight: Bangalore to Udaipur", "kind": "flight"},
                {"name": "Destination Hotel", "kind": "hotel"},
            ],
        }],
    }

    view = trip_view.build_map_view(trip)

    day = view["days"][0]
    names_by_id = {pin["id"]: pin["name"] for pin in view["pins"]}
    assert [names_by_id[pin_id] for pin_id in day["pin_ids"]] == [
        "Origin Hotel",
        "Destination Hotel",
    ]
    assert day["legs"][0]["mode"] == "Flight"
    assert day["legs"][0]["intercity"] is True


def test_map_view_uses_origin_terminal_when_partial_flight_is_first_stop(
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
    assert day["route"]["mode"] == "Flight"
    assert day["legs"][0]["mode"] == "Flight"
    assert day["legs"][0]["intercity"] is True


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


# ---------------------------------------------------------------------------
# build_itinerary (pure, no network)
# ---------------------------------------------------------------------------
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


def test_itinerary_falls_back_to_selections() -> None:
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


def test_northeast_drives_keep_waypoints_and_hotels_in_map_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_local_route_does_not_invent_unverified_metro_service() -> None:
    route = trip_view._route_stats_for_distance(
        10.0,
        from_name="Trident Udaipur",
        to_name="City Palace Udaipur",
    )

    assert route["mode"] == "Taxi"
    assert route["detail"] == "Take a taxi from Trident Udaipur to City Palace Udaipur."


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


def test_arrival_hotel_time_requires_airport_transfer_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trip_view, "_place_coords", lambda name, destination: None)
    trip = {
        **SAMPLE_TRIP,
        "selected_hotels": [{"name": "Trident Udaipur"}],
        "day_wise_itinerary": [{
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
        }],
    }

    itinerary = trip_view.build_itinerary(trip)

    hotel = itinerary["days"][0]["stops"][-1]
    assert hotel["time"] == ""
    assert "time_estimated" not in hotel


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


def test_place_views_expose_each_itinerary_occurrence(monkeypatch) -> None:
    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Dudhsagar Falls Trek", "time": "09:00"}]},
            {"day": 3, "stops": [{"name": "Dudhsagar Falls Trek", "time": "14:00"}]},
        ],
    }
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *args, **kwargs: None)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *args, **kwargs: [])

    view = trip_view.build_view(
        trip, {"kind": "attraction", "name": "Dudhsagar Falls Trek"}
    )

    assert view["items"][0]["occurrences"] == [
        {"day": 1, "stop": 1, "time": "09:00"},
        {"day": 3, "stop": 1, "time": "14:00"},
    ]


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


def test_itinerary_enriches_stop_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_summary(name: str, city: str, **_kw: Any) -> dict[str, Any] | None:
        lower = str(name).strip().lower()
        if lower == "taj exotica resort":
            return {
                "name": name,
                "editorial_summary": "Beachfront luxury stay with easy access to South Goa.",
                "price_level": "PRICE_LEVEL_EXPENSIVE",
                "open_now": True,
                "weekday_descriptions": ["Monday: Open 24 hours"],
            }
        if lower == "dudhsagar falls trek":
            return {
                "name": name,
                "editorial_summary": "Iconic waterfall trail with scenic viewpoints.",
                "price_level": "PRICE_LEVEL_MODERATE",
                "open_now": False,
                "weekday_descriptions": ["Monday: Closed", "Tuesday: 8:00 AM-5:00 PM"],
            }
        return {"name": name}

    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)

    trip = {
        **SAMPLE_TRIP,
        "day_wise_itinerary": [
            {
                "day": 1,
                "date": "2026-01-12",  # Monday
                "stops": [
                    {"name": "Taj Exotica Resort", "kind": "hotel", "booked": True},
                    {"name": "Dudhsagar Falls Trek", "kind": "attraction", "time": "14:00"},
                ],
            }
        ],
    }

    it = trip_view.build_itinerary(trip)
    hotel = it["days"][0]["stops"][0]
    trek = it["days"][0]["stops"][1]

    assert hotel["cost_display"] == "\u20b912,000"
    assert hotel["opening_hours"].startswith("Monday:")
    assert hotel["insight"]
    assert hotel["duration_min"] is None

    assert trek["cost_display"] == "Mid-range"
    assert trek["opening_hours"].startswith("Monday:")
    assert "Likely closed" in trek["concern"]
    assert trek["insight"]

    assert it["days"][0]["reachability"]


def test_itinerary_title_falls_back_to_day_number() -> None:
    trip = {**SAMPLE_TRIP, "day_wise_itinerary": [{"day": 3, "plan": "x"}]}
    it = trip_view.build_itinerary(trip)
    assert it["days"][0]["title"] == "Day 3"
    assert it["days"][0]["day"] == 3



