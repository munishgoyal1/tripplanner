"""Tests for the pure-Python trip view-model (``multiagent.web.trip_view``).

These run with NO Chainlit context — proving the view-model is fully
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
