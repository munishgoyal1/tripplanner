"""Tests for print-ready itinerary exports."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from tripplanner.places_budget import places_budget_scope
from tripplanner.web import itinerary_export, itinerary_pdf

_PNG_DATA_URI = "data:image/png;base64," + base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
).decode("ascii")


def test_static_maps_key_does_not_bypass_disabled_maps_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        itinerary_export,
        "get_settings",
        lambda: SimpleNamespace(enable_google_maps=False, google_places_api_key="copied-key"),
    )
    monkeypatch.setattr(
        itinerary_export.http_client,
        "get",
        lambda *args, **kwargs: pytest.fail("Static Maps must not be called"),
    )

    assert itinerary_export._static_map_data_uri(
        ["a", "b"],
        {"a": {"lat": 1.0, "lng": 2.0}, "b": {"lat": 3.0, "lng": 4.0}},
    ) == ""


def test_static_maps_denies_unscoped_provider_call(monkeypatch) -> None:
    monkeypatch.setattr(
        itinerary_export,
        "get_settings",
        lambda: SimpleNamespace(enable_google_maps=True, google_places_api_key="test-key"),
    )
    monkeypatch.setattr(
        itinerary_export.http_client,
        "get",
        lambda *args, **kwargs: pytest.fail("unscoped provider call"),
    )

    assert itinerary_export._static_map_data_uri(
        ["a", "b"],
        {"a": {"lat": 1.0, "lng": 2.0}, "b": {"lat": 3.0, "lng": 4.0}},
    ) == ""


def test_static_maps_reuse_cached_image(monkeypatch) -> None:
    itinerary_export._STATIC_MAP_CACHE.clear()
    calls = []
    monkeypatch.setattr(
        itinerary_export,
        "get_settings",
        lambda: SimpleNamespace(enable_google_maps=True, google_places_api_key="test-key"),
    )

    class Response:
        content = b"map"
        headers = {"content-type": "image/png"}

        def raise_for_status(self) -> None:
            return None

    def fake_get(*args, **kwargs):
        calls.append(args[0])
        return Response()

    monkeypatch.setattr(itinerary_export.http_client, "get", fake_get)
    pins = {"a": {"lat": 1.0, "lng": 2.0}, "b": {"lat": 3.0, "lng": 4.0}}

    with places_budget_scope("user_interaction"):
        first = itinerary_export._static_map_data_uri(["a", "b"], pins)
        second = itinerary_export._static_map_data_uri(["a", "b"], pins)

    assert first == second
    assert len(calls) == 1


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
    monkeypatch.setattr(itinerary_pdf, "html_to_pdf_bytes", lambda _html: None)
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_itinerary",
        lambda _trip: {
            "days": [
                {
                    "day": 1,
                    "title": "Paris food",
                    "date": "2026-08-24",
                    "google_maps_url": "https://maps.example/day-1",
                    "stops": [
                        {
                            "name": "Louvre Cafe",
                            "kind": "meal",
                            "time": "12:30",
                            "duration_min": 75,
                            "opening_hours": "11:00–22:00",
                            "note": "Lunch near the museum",
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_map_view",
        lambda _trip: {
            "pins": [
                {"id": "a", "name": "Louvre Cafe", "kind": "meal", "lat": 48.8606, "lng": 2.3376},
                {"id": "b", "name": "Hotel", "kind": "hotel", "lat": 48.8584, "lng": 2.2945},
            ],
            "days": [{"day": 1, "pin_ids": ["a", "b"], "route": {}}],
        },
    )
    monkeypatch.setattr(
        itinerary_export,
        "_static_map_data_uri",
        lambda _pin_ids, _pins: _PNG_DATA_URI,
    )
    monkeypatch.setattr(
        itinerary_export.places_cache,
        "get_details",
        lambda _name, _destination: {"address": "1 Rue de Paris", "rating": 4.7},
    )

    def photos(name: str, destination: str, max_photos: int = 1) -> list[str]:
        photo_calls.append((name, destination))
        return [_PNG_DATA_URI]

    monkeypatch.setattr(itinerary_export.places_cache, "get_photos", photos)

    pdf = itinerary_pdf.build_itinerary_pdf_bytes(
        {"destination": "Paris"},
        include_photos=True,
        include_map_circuit=True,
        template="standard",
    )

    assert pdf.startswith(b"%PDF")
    assert photo_calls == [("Louvre Cafe", "Paris")]
    html = itinerary_export.build_export_html(
        {"destination": "Paris"},
        include_photos=True,
        include_map_circuit=True,
        template="standard",
    )
    assert "Monday" in html
    assert "24 August 2026" in html
    assert "1 hr 15 min visit" in html
    assert "11:00–22:00" in html
    assert "Lunch near the museum" in html
    assert "Daily map circuit" in html


def test_layered_trip_book_orders_control_then_days_then_appendices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tripplanner.web import itinerary_trip_book

    monkeypatch.setattr(
        itinerary_trip_book,
        "trip_book_readiness",
        lambda _trip: {
            "blockers": 0,
            "warnings": 1,
            "badge": "1 document to check",
            "checks": [
                {
                    "severity": "warning",
                    "title": "UK ETA · Munish",
                    "detail": "Application reference required",
                }
            ],
            "reason": "",
        },
    )
    monkeypatch.setattr(
        itinerary_export,
        "_documents_wallet_section",
        lambda _trip: "",
    )
    monkeypatch.setattr(
        itinerary_export,
        "_static_map_data_uri",
        lambda _pin_ids, _pins: "",
    )
    monkeypatch.setattr(
        itinerary_export.places_cache,
        "get_details",
        lambda name, _destination: (
            {"address": "St Katharine's EC3N 4AB", "rating": 4.6}
            if name == "Tower of London"
            else {"address": "Aldgate", "phone": "+44 20 3319 7460"}
        ),
    )
    monkeypatch.setattr(
        itinerary_export.places_cache,
        "get_photos",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        itinerary_trip_book.places_cache,
        "get_details",
        itinerary_export.places_cache.get_details,
    )
    monkeypatch.setattr(
        itinerary_trip_book.places_cache,
        "get_photos",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_itinerary",
        lambda _trip: {
            "days": [
                {
                    "day": 1,
                    "title": "Tower and skyline",
                    "date": "2026-08-26",
                    "google_maps_url": "https://maps.example/day-1",
                    "summary": "City through time",
                    "schedule": {
                        "start": "09:10",
                        "end": "18:30",
                        "travel_duration_display": "1 hr 29",
                    },
                    "route": {"distance_display": "16.8 km", "mode": "Metro"},
                    "weather": {"high_c": 23, "low_c": 17, "summary": "light rain"},
                    "stops": [
                        {"name": "Wilde Aldgate", "kind": "hotel", "time": "07:40"},
                        {
                            "name": "Tower of London",
                            "kind": "attraction",
                            "time": "09:10",
                            "booked": True,
                            "booking_ref": "HRP-8842014",
                            "travel_from_previous": {
                                "mode": "Taxi",
                                "duration_display": "18 min",
                            },
                            "insight": "The fortress still runs a family trail on the walls.",
                        },
                        {"name": "Wilde Aldgate", "kind": "hotel", "time": "19:20"},
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_map_view",
        lambda _trip: {
            "pins": [
                {
                    "id": "h",
                    "name": "Wilde Aldgate",
                    "kind": "hotel",
                    "lat": 51.51,
                    "lng": -0.07,
                },
                {
                    "id": "t",
                    "name": "Tower of London",
                    "kind": "attraction",
                    "lat": 51.508,
                    "lng": -0.076,
                },
            ],
            "days": [
                {
                    "day": 1,
                    "pin_ids": ["h", "t", "h"],
                    "route": {
                        "distance_display": "16.8 km",
                        "duration_display": "1 hr 29",
                        "mode": "Metro",
                    },
                }
            ],
        },
    )

    html = itinerary_export.build_export_html(
        {
            "destination": "London",
            "origin": "Delhi",
            "departure_date": "2026-08-24",
            "return_date": "2026-08-31",
            "travelers": "Munish · Ritu · Aarav · Sana",
            "selected_hotels": [{"name": "Wilde Aldgate"}],
            "selected_flights": [{"airline": "British Airways", "flight_number": "BA142"}],
            "preferences_snapshot": {
                "trip_style": "leisure",
                "food_preferences": {"dietary": ["vegetarian"]},
            },
        },
        include_photos=False,
        include_map_circuit=True,
        template="trip_book",
    )

    contents_at = html.find("id='contents'")
    brief_at = html.find("id='trip-brief'")
    days_at = html.find("id='daily-plan'")
    essentials_at = html.find("id='essentials'")
    documents_at = html.find("id='documents'")
    guide_at = html.find("id='place-guide'")
    assert 0 < contents_at < brief_at < days_at < essentials_at < documents_at < guide_at
    assert "Layered Trip Book" in html
    assert "Trip overview" not in html
    assert "Day circuit inset" in html
    assert ">H<" in html
    assert "HRP-8842014" in html
    assert "Taxi · 18 min" in html
    assert "1 document to check" in html
    assert "UK ETA · Munish" in html
    assert "British Airways" in html
    assert "Saved trip style: leisure" in html
    assert "Place facts on file" in html
    assert "Emergency (UK)" not in html
    assert "+91 124 415 0000" not in html
    assert html.find("Your complete travel book") < html.find("Day 1:")
    assert html.find("Day 1:") < html.find("Confirmations and entry")


def test_detailed_export_does_not_gain_trip_book_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(itinerary_export.trip_view, "build_itinerary", lambda _trip: {"days": []})
    monkeypatch.setattr(
        itinerary_export.trip_view,
        "build_map_view",
        lambda _trip: {"days": [], "pins": []},
    )
    html = itinerary_export.build_export_html(
        {"destination": "Paris"},
        include_photos=False,
        include_map_circuit=False,
        template="detailed",
    )
    assert "id='contents'" not in html
    assert "Layered Trip Book" not in html
    assert "Standard" in html
