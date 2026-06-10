"""Tests for the pure-Python trip view-model (``multiagent.web.trip_view``).

These run with NO UI context — proving the view-model is fully
decoupled from the frontend. Places lookups are monkeypatched so we never
touch the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from multiagent.web import trip_view

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
    def fake_photos(name: str, city: str, max_photos: int = 3) -> list[str]:
        return [f"https://example.test/{name}/{i}.jpg" for i in range(min(max_photos, 2))]

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
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

    monkeypatch.setattr(trip_view.places_cache, "get_photos", fake_photos)
    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
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
    assert len(view["items"]) == 1
    assert view["items"][0]["name"] == "Taj Exotica Resort"
    assert view["title"].endswith("Taj Exotica Resort")


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
