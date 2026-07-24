"""Tests for print-ready itinerary exports."""

from __future__ import annotations

import pytest

from tripplanner.web import itinerary_export


def test_export_renders_complete_day_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_itinerary",
        lambda _trip: {
            "days": [
                {
                    "day": 1,
                    "title": "Paris icons",
                    "date": "2026-09-10",
                    "google_maps_url": "https://maps.example/day-1",
                    "stops": [{"name": "Louvre", "kind": "attraction"}],
                }
            ]
        },
    )
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_map_view",
        lambda _trip: {
            "pins": [
                {"id": "a", "name": "Louvre", "lat": 48.8606, "lng": 2.3376},
                {"id": "b", "name": "Eiffel Tower", "lat": 48.8584, "lng": 2.2945},
            ],
            "days": [
                {
                    "day": 1,
                    "pin_ids": ["a", "b"],
                    "route": {
                        "distance_display": "4.2 km",
                        "duration_display": "24 min",
                        "mode": "transit",
                    },
                }
            ],
        },
    )

    html = itinerary_export.build_export_html(
        {"destination": "Paris"},
        include_photos=False,
        include_map_circuit=True,
    )

    assert "Louvre -> Eiffel Tower" in html
    assert "4.2 km · 24 min · transit" in html
    assert "Open this day route in Google Maps" in html
    assert "Scan route" in html
    assert "<svg" in html
