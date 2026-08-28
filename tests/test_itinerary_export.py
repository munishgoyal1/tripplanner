"""Tests for print-ready itinerary exports."""

from __future__ import annotations

import base64

import pytest

from tripplanner.web import itinerary_export, itinerary_pdf


_PNG_DATA_URI = "data:image/png;base64," + base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
).decode("ascii")


def test_export_renders_complete_day_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        itinerary_export,
        "_static_map_data_uri",
        lambda _pin_ids, _pins: "data:image/png;base64,bWFw",
    )
    monkeypatch.setattr(
        itinerary_export.places_cache,
        "get_details",
        lambda _name, _destination: {"address": "1 Rue de Paris", "rating": 4.8},
    )
    monkeypatch.setattr(
        itinerary_export.places_cache,
        "get_photos",
        lambda _name, _destination, max_photos: ["https://images.example/louvre.jpg"],
    )
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
                    "stops": [{"name": "Louvre Cafe", "kind": "meal", "note": "Lunch"}],
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
        include_photos=True,
        include_map_circuit=True,
    )

    assert "Louvre -> Eiffel Tower" in html
    assert "4.2 km · 24 min · transit" in html
    assert "Open this day route in Google Maps" in html
    assert "Scan route" in html
    assert "data:image/png;base64,bWFw" in html
    assert "https://images.example/louvre.jpg" in html
    assert "1 Rue de Paris · Rating 4.8" in html
    assert "Lunch" in html
    assert "<svg" not in html


def test_pdf_embeds_map_place_photo_and_details(monkeypatch: pytest.MonkeyPatch) -> None:
    photo_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        itinerary_pdf.trip_view,
        "build_itinerary",
        lambda _trip: {
            "days": [
                {
                    "day": 1,
                    "title": "Paris food",
                    "google_maps_url": "https://maps.example/day-1",
                    "stops": [
                        {
                            "name": "Louvre Cafe",
                            "kind": "meal",
                            "note": "Lunch near the museum",
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        itinerary_pdf.trip_view,
        "build_map_view",
        lambda _trip: {
            "pins": [
                {"id": "a", "name": "Louvre Cafe", "lat": 48.8606, "lng": 2.3376},
                {"id": "b", "name": "Hotel", "lat": 48.8584, "lng": 2.2945},
            ],
            "days": [{"day": 1, "pin_ids": ["a", "b"], "route": {}}],
        },
    )
    monkeypatch.setattr(
        itinerary_pdf.itinerary_export,
        "_static_map_data_uri",
        lambda _pin_ids, _pins: _PNG_DATA_URI,
    )
    monkeypatch.setattr(
        itinerary_pdf.places_cache,
        "get_summary",
        lambda _name, _destination: {"address": "1 Rue de Paris", "rating": 4.7},
    )

    def photos(name: str, destination: str, max_photos: int) -> list[str]:
        photo_calls.append((name, destination))
        return [_PNG_DATA_URI]

    monkeypatch.setattr(itinerary_pdf.places_cache, "get_photos", photos)

    pdf = itinerary_pdf.build_itinerary_pdf_bytes(
        {"destination": "Paris"},
        include_photos=True,
        include_map_circuit=True,
    )

    assert pdf.startswith(b"%PDF")
    assert photo_calls == [("Louvre Cafe", "Paris")]
