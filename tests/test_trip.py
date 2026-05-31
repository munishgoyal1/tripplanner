"""Tests for user preferences, trip planner state, and trip agent tools."""

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
_TEST_ACTIVE_TRIP = _TEST_DIR / "active_trip.json"
_TEST_TRIP_HISTORY = _TEST_DIR / "trips"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    """Redirect all persistent storage to a temp dir for each test."""
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)

    # Also redirect trip_planner storage
    from multiagent.tools import trip_planner
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", _TEST_ACTIVE_TRIP)
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", _TEST_TRIP_HISTORY)

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
# Trip agent preference tools
# ---------------------------------------------------------------------------
from multiagent.agents.trip_agent import (
    get_travel_preferences,
    record_past_trip,
    save_travel_preferences,
)


class TestPreferenceTools:
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


# ---------------------------------------------------------------------------
# Trip planner state management tools
# ---------------------------------------------------------------------------
from multiagent.tools.trip_planner import (
    create_trip_plan,
    execute_bookings,
    finalize_trip,
    get_trip_plan,
    list_past_trips,
    update_trip_plan,
)


class TestTripPlanState:
    def test_create_trip_plan(self):
        result = create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
            "origin": "Delhi",
        })
        assert "Goa" in result
        assert "DRAFT" in result

    def test_get_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Goa"
        assert parsed["status"] == "draft"

    def test_get_trip_plan_no_plan(self):
        result = get_trip_plan.invoke({})
        assert "No active trip plan" in result

    def test_update_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update = json.dumps({
            "selected_flights": [{"airline": "IndiGo", "price": 8500}],
            "total_cost": 8500,
        })
        result = update_trip_plan.invoke({"updates_json": update})
        assert "updated" in result

        plan = json.loads(get_trip_plan.invoke({}))
        assert len(plan["selected_flights"]) == 1
        assert plan["total_cost"] == 8500

    def test_finalize_trip(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_flights": [{"airline": "IndiGo", "price": 8500}],
            "selected_hotels": [{"name": "Taj Goa", "price": 15000}],
        })})
        result = finalize_trip.invoke({})
        assert "FINALIZED" in result
        assert "IndiGo" in result

    def test_finalize_requires_selections(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = finalize_trip.invoke({})
        assert "Cannot finalize" in result

    def test_execute_bookings(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_flights": [{"airline": "IndiGo", "price": 8500}],
            "selected_hotels": [{"name": "Taj Goa", "price": 15000}],
        })})
        finalize_trip.invoke({})
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert "No active trip plan" in get_trip_plan.invoke({})

    def test_execute_requires_finalized(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = execute_bookings.invoke({})
        assert "must be finalized" in result

    def test_list_past_trips_empty(self):
        result = list_past_trips.invoke({})
        assert "No past trips" in result

    def test_full_lifecycle(self):
        """Test the complete plan → finalize → execute → history cycle."""
        # Create
        create_trip_plan.invoke({
            "destination": "Manali",
            "departure_date": "2026-08-01",
            "return_date": "2026-08-06",
            "origin": "Delhi",
        })
        # Add selections
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_flights": [{"airline": "Air India", "price": 7000}],
            "selected_hotels": [{"name": "Snow Valley", "price": 12000}],
            "selected_activities": [{"name": "Rohtang Pass", "price": 2000}],
            "cost_breakdown": {"flights": 7000, "hotel": 12000, "activities": 2000},
            "total_cost": 21000,
        })})
        # Finalize
        result = finalize_trip.invoke({})
        assert "FINALIZED" in result
        # Execute
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        # Check history
        result = list_past_trips.invoke({})
        assert "manali" in result.lower()


# ---------------------------------------------------------------------------
# Flight search helpers
# ---------------------------------------------------------------------------
from multiagent.tools.flight_search import resolve_iata


class TestFlightHelpers:
    def test_resolve_iata_city_name(self):
        assert resolve_iata("Delhi") == "DEL"
        assert resolve_iata("mumbai") == "BOM"
        assert resolve_iata("Goa") == "GOI"

    def test_resolve_iata_already_code(self):
        assert resolve_iata("DEL") == "DEL"
        assert resolve_iata("bom") == "BOM"

    def test_resolve_iata_international(self):
        assert resolve_iata("Dubai") == "DXB"
        assert resolve_iata("Singapore") == "SIN"
        assert resolve_iata("London") == "LHR"


# ---------------------------------------------------------------------------
# Activity search helpers
# ---------------------------------------------------------------------------
from multiagent.tools.activities_search import _get_coords


class TestActivityHelpers:
    def test_known_city_coords(self):
        coords = _get_coords("Goa")
        assert coords is not None
        lat, lon = coords
        assert 15 < lat < 16
        assert 73 < lon < 74

    def test_unknown_city_coords(self):
        assert _get_coords("Narnia") is None


# ---------------------------------------------------------------------------
# Google Places + Web search helpers (no network — config checks only)
# ---------------------------------------------------------------------------
from multiagent.tools import google_places, web_search
from multiagent.tools.google_places import (
    _format_place,
    _format_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from multiagent.tools.web_search import web_search as web_search_tool


class TestGooglePlacesHelpers:
    def test_format_place_full(self):
        out = _format_place({
            "id": "abc",
            "displayName": {"text": "Taj Mahal Palace"},
            "formattedAddress": "Mumbai, India",
            "rating": 4.6,
            "userRatingCount": 1234,
            "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE",
            "types": ["lodging", "hotel", "establishment"],
            "websiteUri": "https://taj.com",
            "internationalPhoneNumber": "+91 22 6665 3366",
            "currentOpeningHours": {"openNow": True},
        })
        assert out["name"] == "Taj Mahal Palace"
        assert out["rating"] == 4.6
        assert out["place_id"] == "abc"
        assert len(out["types"]) == 3

    def test_format_place_minimal(self):
        out = _format_place({})
        assert out["name"] == ""
        assert out["rating"] is None
        assert out["types"] == []

    def test_format_reviews_truncates(self):
        reviews = [
            {
                "rating": 5,
                "text": {"text": "x" * 500},
                "authorAttribution": {"displayName": "Alice"},
                "relativeTimeDescription": "1 month ago",
            }
        ] * 10
        out = _format_reviews(reviews, limit=3)
        assert len(out) == 3
        assert len(out[0]["text"]) == 300

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from multiagent import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"google_places_api_key": ""})(),
        )
        # Re-bind in module under test
        monkeypatch.setattr(google_places, "get_settings", config.get_settings)
        assert not google_places.is_configured()
        result = search_places_with_reviews.invoke({"query": "test", "city": "Goa"})
        assert "not configured" in result.lower()
        result = nearby_restaurants.invoke({"city": "Goa"})
        assert "not configured" in result.lower()


class TestWebSearchHelpers:
    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from multiagent import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"tavily_api_key": ""})(),
        )
        monkeypatch.setattr(web_search, "get_settings", config.get_settings)
        assert not web_search.is_configured()
        result = web_search_tool.invoke({"query": "best beaches in Goa"})
        assert "not configured" in result.lower()


# ---------------------------------------------------------------------------
# Duffel flight search helpers (no network — formatting & config checks only)
# ---------------------------------------------------------------------------
from multiagent.tools import duffel_flights
from multiagent.tools.duffel_flights import (
    _format_duration,
    _format_offers,
    _format_segment,
    search_flights_duffel,
)


class TestDuffelHelpers:
    def test_format_duration_basic(self):
        assert _format_duration("PT5H30M") == "5h 30m"
        assert _format_duration("PT2H") == "2h"
        assert _format_duration("PT45M") == "45m"
        assert _format_duration("") == ""

    def test_format_segment_minimal(self):
        seg = {
            "marketing_carrier": {"iata_code": "AI"},
            "marketing_carrier_flight_number": "101",
            "origin": {"iata_code": "DEL"},
            "destination": {"iata_code": "BOM"},
            "departing_at": "2026-03-01T09:30:00",
            "arriving_at": "2026-03-01T11:45:00",
            "duration": "PT2H15M",
        }
        line = _format_segment(seg)
        assert "AI101" in line
        assert "DEL 09:30" in line
        assert "BOM 11:45" in line
        assert "2h 15m" in line

    def test_format_offers_empty(self):
        assert "No Duffel offers" in _format_offers([], 5)

    def test_format_offers_sorts_by_price(self):
        offers = [
            {
                "total_amount": "500.00",
                "total_currency": "INR",
                "owner": {"name": "Expensive Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "XX"},
                                "marketing_carrier_flight_number": "999",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T08:00:00",
                                "arriving_at": "2026-03-01T10:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
            {
                "total_amount": "100.00",
                "total_currency": "INR",
                "owner": {"name": "Cheap Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "YY"},
                                "marketing_carrier_flight_number": "1",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T09:00:00",
                                "arriving_at": "2026-03-01T11:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
        ]
        out = _format_offers(offers, 5)
        cheap_pos = out.find("Cheap Air")
        exp_pos = out.find("Expensive Air")
        assert 0 <= cheap_pos < exp_pos

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from multiagent import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"duffel_api_key": ""})(),
        )
        monkeypatch.setattr(duffel_flights, "get_settings", config.get_settings)
        assert not duffel_flights.is_configured()
        result = search_flights_duffel.invoke({
            "origin": "Delhi",
            "destination": "Mumbai",
            "departure_date": "2026-03-01",
        })
        assert "not configured" in result.lower()
        assert "duffel.com/sign-up" in result.lower()


# ---------------------------------------------------------------------------
# Cosmos DB dispatch (mocked — verifies preferences + trip_planner branch
# correctly when storage_cosmos.is_enabled() returns True). No network.
# ---------------------------------------------------------------------------
from multiagent import storage_cosmos, user_context
from multiagent.tools import trip_planner


class TestCosmosDispatch:
    """When Cosmos is enabled, read/write go through storage_cosmos, not files."""

    def test_load_preferences_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {"trip_style": "adventure", "budget_level": "premium"},
        )
        prefs = load_preferences()
        assert prefs["trip_style"] == "adventure"
        assert prefs["budget_level"] == "premium"
        # defaults still merged for unspecified keys
        assert prefs["family"]["adults"] == 1

    def test_load_preferences_cosmos_missing_returns_defaults(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        prefs = load_preferences()
        assert prefs["trip_style"] == "balanced"

    def test_save_preferences_uses_cosmos(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: captured.update(
                {"container": c, "user_id": u, "doc_id": d, "body": body}
            ),
        )
        save_preferences({"trip_style": "adventure"})
        assert captured["container"] == "users"
        assert captured["doc_id"] == "preferences"
        assert captured["user_id"] == "local"  # default user
        assert captured["body"]["trip_style"] == "adventure"

    def test_save_preferences_uses_current_user_id(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: captured.update({"user_id": u}),
        )
        token = user_context._user_id.set("session-abc-123")
        try:
            save_preferences({"trip_style": "leisure"})
        finally:
            user_context._user_id.reset(token)
        assert captured["user_id"] == "session-abc-123"

    def test_load_active_trip_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {
                "destination": "Tokyo",
                "departure_date": "2026-09-01",
                "return_date": "2026-09-08",
                "status": "draft",
            },
        )
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Tokyo"
        assert parsed["status"] == "draft"

    def test_create_trip_plan_writes_to_cosmos(self, monkeypatch):
        captured: list[dict[str, object]] = []
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        # read_doc is called for preferences (load_preferences) and active_trip
        # — return None so defaults are used and no existing plan is found.
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: captured.append(
                {"container": c, "doc_id": d, "body": body}
            ),
        )
        result = create_trip_plan.invoke({
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
        })
        assert "Bali" in result
        # Should have upserted exactly the active_trip doc to the users container.
        active_writes = [
            c for c in captured
            if c["container"] == "users" and c["doc_id"] == "active_trip"
        ]
        assert len(active_writes) == 1
        assert active_writes[0]["body"]["destination"] == "Bali"

    def test_execute_bookings_deletes_active_trip_from_cosmos(self, monkeypatch):
        # State machine: cosmos read returns a finalized plan, then upserts and
        # deletes get captured. Mock all read_doc calls (prefs + active_trip).
        active_plan = {
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
            "travelers": "2 adults",
            "selected_flights": [{"airline": "AI", "price": 5000}],
            "selected_hotels": [{"name": "Hotel", "price": 8000}],
            "selected_activities": [],
            "day_wise_itinerary": [],
            "cost_breakdown": {},
            "total_cost": 13000,
            "notes": "",
            "status": "finalized",
        }
        delete_calls: list[tuple[str, str, str]] = []
        upsert_calls: list[tuple[str, str, str]] = []

        def _read(container: str, user: str, doc_id: str):
            if doc_id == "active_trip":
                return dict(active_plan)
            return None  # preferences fall back to defaults

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", _read)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: upsert_calls.append((c, u, d)),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "delete_doc",
            lambda c, u, d: delete_calls.append((c, u, d)),
        )

        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert ("users", "local", "active_trip") in delete_calls
        # The archived trip should be written to the trips container.
        assert any(c == "trips" for c, _, _ in upsert_calls)

    def test_list_past_trips_queries_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "query_docs",
            lambda c, u: [
                {
                    "destination": "Goa",
                    "departure_date": "2025-06-01",
                    "return_date": "2025-06-05",
                    "total_cost": 25000,
                    "status": "booked",
                },
                {
                    "destination": "Kerala",
                    "departure_date": "2025-12-10",
                    "return_date": "2025-12-15",
                    "total_cost": 30000,
                    "status": "booked",
                },
            ],
        )
        result = list_past_trips.invoke({})
        assert "Goa" in result
        assert "Kerala" in result


class TestUserContext:
    """ContextVar default + scoped override behavior."""

    def test_default_user_id(self):
        assert user_context.get_user_id() == "local"
        assert user_context.is_default_user() is True

    def test_set_and_reset_user_id(self):
        token = user_context._user_id.set("alice")
        try:
            assert user_context.get_user_id() == "alice"
            assert user_context.is_default_user() is False
        finally:
            user_context._user_id.reset(token)
        assert user_context.get_user_id() == "local"

