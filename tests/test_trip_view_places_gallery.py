"""Trip-view place details, gallery, and occurrence tests."""

from __future__ import annotations

import pytest

from tests.support.trip_view import SAMPLE_TRIP
from tripplanner.web import trip_view

pytestmark = pytest.mark.usefixtures("_no_network")


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


def test_unfocused_view_skips_reviews_and_limits_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    review_calls: list[str] = []
    photo_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_summary",
        lambda name, _city: review_calls.append(name) or {"name": name},
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, _city: {"name": name, "rating": 4.5},
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_photos",
        lambda name, _city, max_photos: photo_calls.append((name, max_photos)) or [],
    )

    trip_view.build_view(SAMPLE_TRIP, None)

    assert review_calls == []
    assert len(photo_calls) <= 3
    assert all(max_photos == 1 for _, max_photos in photo_calls)


def test_focused_view_fetches_reviews_once(monkeypatch: pytest.MonkeyPatch) -> None:
    review_calls: list[str] = []
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_summary",
        lambda name, _city: review_calls.append(name) or {"name": name},
    )
    monkeypatch.setattr(
        trip_view.places_cache,
        "get_details",
        lambda name, _city: {"name": name},
    )

    trip_view.build_view(
        SAMPLE_TRIP,
        {"kind": "attraction", "name": "Dudhsagar Falls Trek"},
    )

    assert review_calls == ["Dudhsagar Falls Trek"]


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
    trip = {
        "status": "draft",
        "destination": "Goa",
        "selected_hotels": [],
        "selected_activities": [],
    }
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
    # Keeps alternatives visible.
    assert any(i["name"] != "Taj Exotica Resort" for i in view["items"])
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
