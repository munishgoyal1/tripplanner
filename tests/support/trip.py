"""Shared imports and isolated persistence fixture for trip ownership tests."""

# ruff: noqa: F401, I001

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tripplanner import storage_cosmos, user_context
from tripplanner.agents.trip_agent import (
    TRIP_SYSTEM_PROMPT,
    add_family_member as tool_add_family_member,
    add_user_dislike as tool_add_user_dislike,
    add_user_interest as tool_add_user_interest,
    build_trip_system_prompt,
    get_travel_preferences,
    record_past_trip,
    record_trip_mention as tool_record_trip_mention,
    record_trip_postmortem,
    remember_about_user,
    save_travel_preferences,
    update_user_profile as tool_update_user_profile,
)
from tripplanner.tools import (
    duffel_flights,
    google_places,
    trip_history,
    trip_planner,
    user_preferences,
    web_search,
)
from tripplanner.tools.activities_search import _get_coords
from tripplanner.tools.duffel_flights import (
    _format_duration,
    _format_offers,
    _format_segment,
    search_flights_duffel,
)
from tripplanner.tools.flight_search import resolve_iata
from tripplanner.tools.google_places import (
    _format_place,
    _format_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from tripplanner.tools.trip_planner import (
    _compute_trip_id,
    _merge_itinerary_days,
    add_hotel_stay,
    add_selection,
    create_trip_plan,
    delete_saved_trip,
    execute_bookings,
    finalize_trip,
    get_trip_plan,
    list_past_trips,
    list_saved_trips,
    planning_completion_gaps,
    remove_selection,
    resume_trip,
    set_stop_booked,
    switch_active_trip,
    update_trip_plan,
)
from tripplanner.tools.user_preferences import (
    _deep_merge,
    add_dislike,
    add_interest,
    add_learned_note,
    add_past_trip,
    add_trip_mention,
    load_preferences,
    save_preferences,
    update_preferences,
    update_profile,
    upsert_family_member,
)
from tripplanner.tools.web_search import web_search as web_search_tool

_TEST_DIR = Path.home() / f".tripplanner_test-{os.getpid()}"
_TEST_FILE = _TEST_DIR / "user_preferences.json"
_TEST_ACTIVE_TRIP = _TEST_DIR / "active_trip.json"
_TEST_TRIP_HISTORY = _TEST_DIR / "trips"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    """Redirect all persistent storage to a temp dir for each test."""
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)

    # Also redirect trip_planner storage
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", _TEST_ACTIVE_TRIP)
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", _TEST_TRIP_HISTORY)
    monkeypatch.setattr(trip_history, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_history, "_ACTIVE_TRIP_FILE", _TEST_ACTIVE_TRIP)
    monkeypatch.setattr(trip_history, "_TRIP_HISTORY_DIR", _TEST_TRIP_HISTORY)

    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


__all__ = [name for name in globals() if not name.startswith("__")]
