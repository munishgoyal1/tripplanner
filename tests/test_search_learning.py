"""Tests for search-behavior preference inference (search_learning)."""

import shutil
from pathlib import Path

import pytest

from tripplanner.tools import search_learning, user_preferences
from tripplanner.tools.user_preferences import load_preferences

_TEST_DIR = Path.home() / ".tripplanner_searchlearn_test"
_TEST_FILE = _TEST_DIR / "user_preferences.json"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)
    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


class TestExtractSignals:
    def test_flight_cabin(self):
        sig = search_learning._extract_signals(
            "search_flights_duffel", {"cabin_class": "Business"}
        )
        assert sig == [("flight_class", "business")]

    def test_hotel_high_floor_only(self):
        assert search_learning._extract_signals("search_hotels", {"ratings": "4,5"}) == [
            ("hotel_rating_floor", "4")
        ]
        # default 3,4,5 floor is not a signal
        assert search_learning._extract_signals("search_hotels", {"ratings": "3,4,5"}) == []

    def test_activity_categories(self):
        sig = search_learning._extract_signals(
            "search_activities", {"categories": "beaches, hiking"}
        )
        assert ("activity_interest", "beaches") in sig
        assert ("activity_interest", "hiking") in sig

    def test_non_search_tool(self):
        assert search_learning._extract_signals("get_weather_forecast", {"city": "Goa"}) == []


class TestObservePromotion:
    def test_counts_accumulate_without_premature_promotion(self):
        for _ in range(2):
            assert search_learning.observe("search_flights_duffel", {"cabin_class": "business"}) == []
        prefs = load_preferences()
        assert prefs["behavior_signals"]["flight_class"]["business"] == 2
        # not yet promoted
        assert prefs["transport_preferences"]["flight_class"] == "economy"

    def test_promotes_flight_class_at_threshold(self):
        promoted = []
        for _ in range(3):
            promoted = search_learning.observe(
                "search_flights_duffel", {"cabin_class": "business"}
            )
        assert "flight_class:business" in promoted
        prefs = load_preferences()
        assert prefs["transport_preferences"]["flight_class"] == "business"
        notes = [n["note"] for n in prefs["learned_notes"]]
        assert any("business class flights" in n for n in notes)

    def test_promotes_only_once(self):
        for _ in range(5):
            search_learning.observe("search_flights_duffel", {"cabin_class": "business"})
        prefs = load_preferences()
        notes = [n["note"] for n in prefs["learned_notes"] if "business class" in n["note"]]
        assert len(notes) == 1

    def test_does_not_override_explicit_choice(self):
        user_preferences.update_preferences(
            {"transport_preferences": {"flight_class": "first"}}
        )
        for _ in range(3):
            search_learning.observe("search_flights_duffel", {"cabin_class": "business"})
        prefs = load_preferences()
        # explicit "first" stays; only a learned note is added
        assert prefs["transport_preferences"]["flight_class"] == "first"

    def test_does_not_override_explicit_default_choice(self):
        prefs = load_preferences()
        user_preferences.mark_explicit_fields(
            prefs,
            {
                "transport_preferences.flight_class",
                "hotel_preferences.star_rating_min",
            },
        )
        user_preferences.save_preferences(prefs)

        for _ in range(3):
            search_learning.observe(
                "search_flights_duffel", {"cabin_class": "business"}
            )
            search_learning.observe("search_hotels", {"ratings": "5"})

        updated = load_preferences()
        assert updated["transport_preferences"]["flight_class"] == "economy"
        assert updated["hotel_preferences"]["star_rating_min"] == 3

    def test_promotes_hotel_rating_floor(self):
        for _ in range(3):
            search_learning.observe("search_hotels", {"ratings": "5"})
        prefs = load_preferences()
        assert prefs["hotel_preferences"]["star_rating_min"] == 5

    def test_activity_interest_added_after_threshold(self):
        for _ in range(3):
            search_learning.observe("search_activities", {"categories": "beaches"})
        prefs = load_preferences()
        assert "beaches" in [i.lower() for i in prefs["interests"]]

    def test_swallows_errors(self, monkeypatch):
        def _boom(*_a, **_k):
            raise RuntimeError("disk gone")

        monkeypatch.setattr(search_learning, "mutate_preferences", _boom)
        # Must not raise.
        assert search_learning.observe("search_hotels", {"ratings": "5"}) == []
