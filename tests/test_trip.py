"""Tests for user preferences store and trip agent tools."""

import json
import shutil
from pathlib import Path

import pytest

from multiagent.tools import user_preferences
from multiagent.tools.user_preferences import (
    _deep_merge,
    add_past_trip,
    load_preferences,
    save_preferences,
    update_preferences,
)

_TEST_DIR = Path.home() / ".multiagent_test"
_TEST_FILE = _TEST_DIR / "user_preferences.json"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    """Redirect preference storage to a temp dir for each test."""
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)
    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# user_preferences module tests
# ---------------------------------------------------------------------------
class TestDeepMerge:
    def test_flat(self):
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_override(self):
        assert _deep_merge({"a": 1}, {"a": 99}) == {"a": 99}

    def test_nested(self):
        base = {"x": {"y": 1, "z": 2}}
        result = _deep_merge(base, {"x": {"z": 99}})
        assert result == {"x": {"y": 1, "z": 99}}


class TestLoadSave:
    def test_defaults_when_no_file(self):
        prefs = load_preferences()
        assert prefs["family"]["adults"] == 1
        assert prefs["trip_style"] == "balanced"
        assert prefs["budget_level"] == "moderate"

    def test_roundtrip(self):
        prefs = load_preferences()
        prefs["family"]["adults"] = 3
        save_preferences(prefs)
        reloaded = load_preferences()
        assert reloaded["family"]["adults"] == 3

    def test_update_merges(self):
        update_preferences({"trip_style": "leisure", "family": {"children": 2, "child_ages": [4, 8]}})
        prefs = load_preferences()
        assert prefs["trip_style"] == "leisure"
        assert prefs["family"]["children"] == 2
        assert prefs["family"]["adults"] == 1  # untouched

    def test_add_past_trip(self):
        add_past_trip("Goa", "2025-12-20 to 2025-12-27", 5, "Amazing beaches")
        add_past_trip("Shimla", "2025-01-10 to 2025-01-15", 3, "Too crowded")
        prefs = load_preferences()
        assert len(prefs["past_trips"]) == 2
        assert prefs["past_trips"][0]["destination"] == "Goa"
        assert prefs["past_trips"][1]["rating"] == 3


# ---------------------------------------------------------------------------
# Trip agent tool tests (invoke via langchain .invoke)
# ---------------------------------------------------------------------------
from multiagent.agents.trip_agent import (
    get_travel_preferences,
    record_past_trip,
    save_travel_preferences,
    suggest_hotels,
    suggest_itinerary,
    suggest_transport,
)


class TestTripTools:
    def test_get_travel_preferences(self):
        result = get_travel_preferences.invoke({})
        parsed = json.loads(result)
        assert "family" in parsed
        assert "trip_style" in parsed

    def test_save_travel_preferences(self):
        payload = json.dumps({
            "family": {"adults": 2, "children": 1, "child_ages": [5]},
            "trip_style": "leisure",
            "budget_level": "premium",
        })
        result = save_travel_preferences.invoke({"updates_json": payload})
        assert "Preferences updated" in result

        prefs = load_preferences()
        assert prefs["family"]["adults"] == 2
        assert prefs["family"]["children"] == 1
        assert prefs["trip_style"] == "leisure"

    def test_save_invalid_json(self):
        result = save_travel_preferences.invoke({"updates_json": "not json"})
        assert "Error" in result

    def test_record_past_trip(self):
        result = record_past_trip.invoke({
            "destination": "Paris",
            "dates": "2025-06-01 to 2025-06-07",
            "rating": 5,
            "notes": "Loved the food",
        })
        assert "Paris" in result
        prefs = load_preferences()
        assert len(prefs["past_trips"]) == 1

    def test_suggest_itinerary_includes_prefs(self):
        update_preferences({
            "family": {"adults": 2, "children": 2, "child_ages": [3, 7]},
            "trip_style": "leisure",
            "budget_level": "moderate",
        })
        result = suggest_itinerary.invoke({
            "destination": "Goa",
            "days": 5,
            "interests": "beaches, seafood",
        })
        assert "Goa" in result
        assert "leisure" in result.lower() or "relaxed" in result.lower()
        assert "2 children" in result or "children" in result.lower()

    def test_suggest_hotels_includes_family(self):
        update_preferences({
            "family": {"adults": 2, "children": 1, "child_ages": [4]},
            "budget_level": "premium",
            "hotel_preferences": {"star_rating_min": 4, "preferred_amenities": ["pool", "breakfast"]},
        })
        result = suggest_hotels.invoke({
            "city": "Mumbai",
            "checkin": "2026-01-10",
            "checkout": "2026-01-14",
        })
        assert "Mumbai" in result
        assert "$200-$400" in result
        assert "pool" in result

    def test_suggest_transport_uses_prefs(self):
        update_preferences({
            "family": {"adults": 2},
            "transport_preferences": {"flight_class": "business", "open_to_trains": True},
            "budget_level": "premium",
        })
        result = suggest_transport.invoke({
            "origin": "Delhi",
            "destination": "Mumbai",
            "date": "2026-02-15",
        })
        assert "Delhi" in result
        assert "Mumbai" in result
        assert "business" in result.lower()
        assert "Train" in result or "train" in result
