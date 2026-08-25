from __future__ import annotations

from typing import Any

import pytest

from tripplanner.web import trip_view
from tripplanner.web.map_pins import _provider_name_matches
from tripplanner.web.place_confidence import ANCHOR, LABEL, PLACE, stop_place_tier

SAMPLE_TRIP: dict[str, Any] = {
    "status": "planned",
    "destination": "Paris",
    "selected_hotels": [{"name": "Hotel Chambiges Elysees"}],
    "selected_activities": [],
}


class TestStopPlaceTier:
    def test_a_stay_or_terminal_is_an_anchor(self) -> None:
        assert stop_place_tier("Hotel Chambiges Elysees", "hotel") == ANCHOR
        assert stop_place_tier("Charles de Gaulle Airport", "airport") == ANCHOR

    def test_a_booked_stop_is_an_anchor_whatever_it_is_called(self) -> None:
        assert stop_place_tier("Dinner", "meal", booked=True) == ANCHOR

    def test_a_named_place_survives_a_generic_word(self) -> None:
        for name in ("Seine River Cruise", "Eiffel Tower", "Palace of Versailles"):
            assert stop_place_tier(name, "attraction") == PLACE

    def test_an_activity_label_names_no_place(self) -> None:
        for name in (
            "Dinner",
            "Free time",
            "Beach day",
            "Explore the old town",
            "Check in and relax",
            "Lunch near the hotel",
            "Shopping",
        ):
            assert stop_place_tier(name, "attraction") == LABEL

    def test_an_explicit_pick_is_a_place_even_when_named_generically(self) -> None:
        assert stop_place_tier("Shopping", "attraction", selected={"shopping"}) == PLACE


def test_map_pin_matching_accepts_a_strong_place_alias() -> None:
    assert _provider_name_matches("Treta Ke Thakur", "Tretanath Mandir")


def _details(coords: dict[str, tuple[float, float]], provider: dict[str, str]):
    def _get(name: str, city: str) -> dict[str, Any]:
        lat, lng = coords.get(name, (None, None))
        return {
            "place_id": f"pid-{name}",
            "name": provider.get(name, name),
            "lat": lat,
            "lng": lng,
        }

    return _get


@pytest.fixture
def _paris(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trip_view, "_maps_browser_key", lambda: "test-key")
    monkeypatch.setattr(trip_view, "_airport_pin", lambda destination: None)
    monkeypatch.setattr(trip_view.places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *a, **k: [])
    monkeypatch.setattr(trip_view.places_cache, "top_places", lambda *a, **k: [])


def _map_with(monkeypatch: pytest.MonkeyPatch, stops: list[dict[str, Any]], **extra: Any):
    coords = {
        "Hotel Chambiges Elysees": (48.8667, 2.3020),
        "Seine River Cruise": (48.8603, 2.2935),
        "Eiffel Tower": (48.8584, 2.2945),
        "Dinner": (48.8670, 2.3630),
    }
    provider = {"Seine River Cruise": "Bateaux Parisiens", "Dinner": "Bouillon Republique"}
    monkeypatch.setattr(trip_view.places_cache, "get_details", _details(coords, provider))
    trip = {
        **SAMPLE_TRIP,
        **extra,
        "day_wise_itinerary": [{"day": 1, "stops": stops}],
    }
    return trip_view.build_map_view(trip)


class TestUnmappedStops:
    def test_a_differently_named_place_is_reported_with_its_candidate(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _map_with(
            monkeypatch,
            [
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                {"name": "Seine River Cruise", "kind": "attraction"},
            ],
        )

        assert "Seine River Cruise" not in {pin["name"] for pin in view["pins"]}
        reported = {stop["name"]: stop for stop in view["unmapped_stops"]}
        assert reported["Seine River Cruise"]["reason"] == "no_match"
        assert reported["Seine River Cruise"]["tier"] == PLACE
        assert reported["Seine River Cruise"]["candidate"]["name"] == "Bateaux Parisiens"
        assert reported["Seine River Cruise"]["day"] == 1

    def test_an_activity_label_is_reported_rather_than_geocoded(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _map_with(
            monkeypatch,
            [
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                {"name": "Dinner", "kind": "meal"},
            ],
        )

        assert "Bouillon Republique" not in {pin["name"] for pin in view["pins"]}
        reported = {stop["name"]: stop for stop in view["unmapped_stops"]}
        assert reported["Dinner"]["reason"] == "not_a_place"
        assert reported["Dinner"]["tier"] == LABEL

    def test_a_stop_without_coordinates_is_reported(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _map_with(
            monkeypatch,
            [
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                {"name": "Musee Nowhere", "kind": "attraction"},
            ],
        )

        reported = {stop["name"]: stop for stop in view["unmapped_stops"]}
        assert reported["Musee Nowhere"]["reason"] == "no_location"

    def test_a_mapped_stop_is_not_reported(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _map_with(
            monkeypatch,
            [
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                {"name": "Eiffel Tower", "kind": "attraction"},
            ],
        )

        assert "Eiffel Tower" in {pin["name"] for pin in view["pins"]}
        assert "Eiffel Tower" not in {stop["name"] for stop in view["unmapped_stops"]}

    def test_a_day_trip_uses_its_locality_for_places_lookup(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        looked_up: list[tuple[str, str]] = []

        def details(name: str, city: str) -> dict[str, Any]:
            looked_up.append((name, city))
            if name == "Anand Bhavan" and city == "Prayagraj":
                return {
                    "place_id": "pid-anand",
                    "name": "Anand Bhawan Museum",
                    "lat": 25.4594,
                    "lng": 81.8601,
                }
            return {"name": name, "lat": 25.0, "lng": 81.0}

        monkeypatch.setattr(trip_view.places_cache, "get_details", details)
        trip = {
            **SAMPLE_TRIP,
            "destination": "Varanasi, Ayodhya, and nearby religious sites",
            "day_wise_itinerary": [{
                "day": 1,
                "title": "Prayagraj (Allahabad) Day Trip",
                "stops": [{"name": "Anand Bhavan", "kind": "attraction"}],
            }],
        }

        view = trip_view.build_map_view(trip)

        assert ("Anand Bhavan", "Prayagraj") in looked_up
        assert "Anand Bhavan" in {pin["name"] for pin in view["pins"]}
        assert not view["unmapped_stops"]

    def test_a_stop_retries_the_trip_destination_when_the_day_heading_has_no_location(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        looked_up: list[tuple[str, str]] = []

        def details(name: str, city: str) -> dict[str, Any] | None:
            looked_up.append((name, city))
            if name == "SeaShell Port Blair" and city == "Andaman (Port Blair & Havelock)":
                return {
                    "place_id": "pid-seashell",
                    "name": "SeaShell, Port Blair",
                    "lat": 11.6757343,
                    "lng": 92.739726,
                }
            return None

        monkeypatch.setattr(trip_view.places_cache, "get_details", details)
        trip = {
            **SAMPLE_TRIP,
            "destination": "Andaman (Port Blair & Havelock)",
            "selected_hotels": [{"name": "SeaShell Port Blair"}],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "title": "Arrival in Port Blair",
                    "stops": [{"name": "SeaShell Port Blair", "kind": "hotel"}],
                }
            ],
        }

        view = trip_view.build_map_view(trip)

        assert looked_up[:2] == [
            ("SeaShell Port Blair", "Arrival in Port Blair"),
            ("SeaShell Port Blair", "Andaman (Port Blair & Havelock)"),
        ]
        assert "SeaShell Port Blair" in {pin["name"] for pin in view["pins"]}
        assert not view["unmapped_stops"]

    def test_a_confirmed_binding_pins_the_stop_and_clears_the_report(
        self, _paris: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = _map_with(
            monkeypatch,
            [
                {"name": "Hotel Chambiges Elysees", "kind": "hotel"},
                {"name": "Seine River Cruise", "kind": "attraction"},
            ],
            place_bindings={
                "seine river cruise": {
                    "name": "Bateaux Parisiens",
                    "place_id": "pid-x",
                    "lat": 48.8603,
                    "lng": 2.2935,
                }
            },
        )

        assert "Seine River Cruise" in {pin["name"] for pin in view["pins"]}
        assert "Seine River Cruise" not in {stop["name"] for stop in view["unmapped_stops"]}


def test_a_day_heading_is_not_a_locality() -> None:
    """Searching "Musee d'Orsay Day 4 - Montmartre" matches nothing."""
    from tripplanner.web.map_pins import _day_place_context

    assert _day_place_context({"title": "Day 4 · Montmartre & Sacré-Cœur"}, "Paris") == "Montmartre"
    assert _day_place_context({"title": "Day 5 · Versailles Day Trip"}, "Paris") == "Versailles"
    assert _day_place_context({"title": "Day 6 · Departure"}, "Paris") == "Paris"
    assert _day_place_context({"title": "Day 1 · Arrival in Paris"}, "Paris") == "Paris"
    assert _day_place_context({"title": "Day 2 · Free time"}, "Rome") == "Rome"


def test_an_explicit_city_still_wins() -> None:
    from tripplanner.web.map_pins import _day_place_context

    assert _day_place_context({"city": "Lyon", "title": "Day 2 · Departure"}, "Paris") == "Lyon"
