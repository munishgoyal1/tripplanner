"""Pure-Python tests for the Lab 13 paged destination guide (``paged_places``).

No network: ``places_cache`` is unconfigured under test, so ``top_places`` /
``get_details`` return empty and the discovery pool is built entirely from the
trip's structured selections and itinerary evidence.
"""

from __future__ import annotations

from typing import Any

import pytest

from tripplanner.web import trip_view


@pytest.fixture(autouse=True)
def _no_places_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the discovery pool deterministic: no Places fallbacks or lookups."""
    from tripplanner.web import places_cache

    monkeypatch.setattr(places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(places_cache, "get_details", lambda *a, **k: None)
    monkeypatch.setattr(places_cache, "get_photos", lambda *a, **k: [])


def _trip() -> dict[str, Any]:
    return {
        "destination": "Rajasthan",
        "selected_hotels": [{"name": "Taj Lake Palace", "city": "Udaipur"}],
        "selected_activities": [
            {"name": "City Palace", "city": "Udaipur", "kind": "attraction"}
        ],
        "day_wise_itinerary": [
            {
                "day": 1,
                "city": "Jaipur",
                "stops": [
                    {"name": "Amber Fort", "kind": "attraction", "city": "Jaipur"},
                    {"name": "Hawa Mahal", "kind": "attraction", "city": "Jaipur"},
                    {"name": "Suvarna Mahal", "kind": "restaurant", "city": "Jaipur"},
                ],
            },
            {
                "day": 2,
                "city": "Jodhpur",
                "stops": [
                    {"name": "Mehrangarh Fort", "kind": "attraction"},
                    {"name": "Umaid Bhawan", "kind": "hotel"},
                ],
            },
        ],
    }


def _names(page: dict[str, Any]) -> list[str]:
    return [row["name"] for row in page["items"]]


def test_default_page_balances_cities_and_kinds() -> None:
    page = trip_view.paged_places(_trip())

    # 7 grounded places from selections + itinerary; first page is capped at 6.
    assert page["total_count"] == 7
    assert len(page["items"]) == 6
    assert page["cursor"] == "6"
    assert page["remaining_count"] == 1
    assert page["available_cities"] == ["Udaipur", "Jaipur", "Jodhpur"]
    assert page["available_kinds"] == ["hotel", "attraction", "restaurant"]
    # City comes from structured evidence, never the destination label.
    taj = next(row for row in page["items"] if row["name"] == "Taj Lake Palace")
    assert taj["city"] == "Udaipur"
    assert taj["selected"] is True


def test_cursor_pages_through_the_pool() -> None:
    trip = _trip()
    first = trip_view.paged_places(trip, limit=3)
    assert len(first["items"]) == 3
    assert first["cursor"] == "3"

    second = trip_view.paged_places(trip, limit=3, cursor=first["cursor"])
    assert len(second["items"]) == 3
    assert second["cursor"] == "6"

    third = trip_view.paged_places(trip, limit=3, cursor=second["cursor"])
    assert len(third["items"]) == 1
    assert third["cursor"] is None
    assert third["remaining_count"] == 0

    seen = _names(first) + _names(second) + _names(third)
    assert len(seen) == len(set(seen)) == 7


def test_city_and_kind_filters() -> None:
    trip = _trip()

    jaipur = trip_view.paged_places(trip, city="Jaipur")
    assert set(_names(jaipur)) == {"Amber Fort", "Hawa Mahal", "Suvarna Mahal"}

    hotels = trip_view.paged_places(trip, kind="hotel")
    assert set(_names(hotels)) == {"Taj Lake Palace", "Umaid Bhawan"}

    food = trip_view.paged_places(trip, kind="restaurant")
    assert _names(food) == ["Suvarna Mahal"]


def test_query_matches_name_or_city() -> None:
    forts = trip_view.paged_places(_trip(), query="fort")
    assert set(_names(forts)) == {"Amber Fort", "Mehrangarh Fort"}


def test_highlights_and_all_cities_are_treated_as_unfiltered() -> None:
    page = trip_view.paged_places(_trip(), city="all cities", kind="highlights")
    assert page["total_count"] == 7


def test_focus_returns_same_city_same_kind_alternatives() -> None:
    page = trip_view.paged_places(
        _trip(), focus_name="Amber Fort", focus_kind="attraction"
    )
    # Only other Jaipur attraction, excluding the focused place itself.
    assert _names(page) == ["Hawa Mahal"]


def test_focus_with_no_alternatives_is_empty() -> None:
    page = trip_view.paged_places(
        _trip(), focus_name="Suvarna Mahal", focus_kind="restaurant"
    )
    assert page["items"] == []
    assert page["total_count"] == 0


def test_route_cities_fallback_excludes_transport_legs() -> None:
    """Trips without structured city fields still yield per-city filters, and the
    transport legs used to infer them are not themselves listed as places."""
    trip = {
        "destination": "Madhya Pradesh",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {"name": "Flight: Bangalore to Indore", "kind": "flight"},
                    {"name": "Rajwada Palace", "kind": "attraction"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Drive: Indore to Ujjain", "kind": "transport"},
                    {"name": "Mahakaleshwar Temple", "kind": "attraction"},
                ],
            },
        ],
    }
    page = trip_view.paged_places(trip)
    assert page["available_cities"] == ["Indore", "Ujjain"]
    assert set(_names(page)) == {"Rajwada Palace", "Mahakaleshwar Temple"}
    rajwada = next(row for row in page["items"] if row["name"] == "Rajwada Palace")
    assert rajwada["city"] == "Indore"
    maha = next(row for row in page["items"] if row["name"] == "Mahakaleshwar Temple")
    assert maha["city"] == "Ujjain"


def test_discovery_items_rank_above_in_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh must-visit/popular places not yet in the trip sort to the top."""
    from tripplanner.web import places_cache

    monkeypatch.setattr(
        places_cache,
        "top_places",
        lambda city, kind, n=6: (
            ["Nahargarh Fort"] if kind == "attraction" and city == "Jaipur" else []
        ),
    )
    page = trip_view.paged_places(_trip(), city="Jaipur", kind="attraction")
    names = _names(page)
    assert names[0] == "Nahargarh Fort"  # not-in-trip discovery leads
    assert {"Amber Fort", "Hawa Mahal"}.issubset(set(names))
    fresh = next(row for row in page["items"] if row["name"] == "Nahargarh Fort")
    assert fresh["selected"] is False
