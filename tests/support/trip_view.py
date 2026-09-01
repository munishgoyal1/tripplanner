"""Shared fixtures and helpers for trip-view ownership modules."""

from __future__ import annotations

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


@pytest.fixture
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


@pytest.fixture
def _map_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Geocoded place lookups for the map view (lat/lng per known name)."""
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)
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


_LONG_HAUL_COORDS = {
    "Kempegowda International Airport": (13.1986, 77.7066),
    "Bengaluru Airport": (13.1986, 77.7066),
    "Charles de Gaulle Airport": (49.0097, 2.5479),
    "Paris Airport": (49.0097, 2.5479),
    "Hotel Lutetia": (48.8515, 2.3266),
}


@pytest.fixture
def _long_haul_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trip_view.places_cache, "is_configured", lambda: True)

    def fake_summary(name: str, city: str) -> dict[str, Any] | None:
        lat, lng = _LONG_HAUL_COORDS.get(name, (None, None))
        return {"place_id": f"pid-{name}", "name": name, "lat": lat, "lng": lng}

    monkeypatch.setattr(trip_view.places_cache, "get_summary", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_details", fake_summary)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "browser-key")


def _long_haul_trip(stops: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "destination": "Paris",
        "origin": "Bengaluru",
        "selected_hotels": [{"name": "Hotel Lutetia"}],
        "day_wise_itinerary": [{"day": 1, "stops": stops}],
    }
