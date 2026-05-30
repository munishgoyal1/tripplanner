"""Persistent user preferences store — JSON file backed.

Stores family configuration, trip style, budget level, transport/hotel
preferences, dietary needs, and past trip history. Shared across agents
but primarily used by the Trip Planner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PREFS_DIR = Path.home() / ".multiagent"
_PREFS_FILE = _PREFS_DIR / "user_preferences.json"

_DEFAULT_PREFS: dict[str, Any] = {
    "family": {
        "adults": 1,
        "children": 0,
        "child_ages": [],
        "elderly": 0,
        "pets": False,
    },
    "trip_style": "balanced",  # leisure | balanced | packed_sightseeing | adventure
    "budget_level": "moderate",  # budget | moderate | premium | luxury
    "hotel_preferences": {
        "star_rating_min": 3,
        "preferred_amenities": [],  # pool, gym, breakfast, parking, wifi, spa
        "preferred_chains": [],
        "room_type": "standard",  # standard | suite | apartment
    },
    "transport_preferences": {
        "flight_class": "economy",  # economy | premium_economy | business | first
        "prefer_direct_flights": True,
        "open_to_trains": True,
        "open_to_rental_car": True,
        "open_to_bus": False,
    },
    "food_preferences": {
        "dietary": [],  # vegetarian, vegan, halal, kosher, gluten-free
        "cuisine_likes": [],
        "cuisine_dislikes": [],
    },
    "accessibility_needs": [],
    "past_trips": [],  # [{destination, dates, rating, notes}]
}


def _ensure_dir() -> None:
    _PREFS_DIR.mkdir(parents=True, exist_ok=True)


def load_preferences() -> dict[str, Any]:
    """Load preferences from disk, merging with defaults for any missing keys."""
    if _PREFS_FILE.exists():
        raw = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        return _deep_merge(_DEFAULT_PREFS, raw)
    return json.loads(json.dumps(_DEFAULT_PREFS))  # deep copy


def save_preferences(prefs: dict[str, Any]) -> None:
    """Persist preferences to disk."""
    _ensure_dir()
    _PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def update_preferences(updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge updates into existing preferences and save."""
    current = load_preferences()
    merged = _deep_merge(current, updates)
    save_preferences(merged)
    return merged


def add_past_trip(
    destination: str,
    dates: str,
    rating: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Append a trip to history and save."""
    prefs = load_preferences()
    prefs["past_trips"].append({
        "destination": destination,
        "dates": dates,
        "rating": rating,
        "notes": notes,
    })
    save_preferences(prefs)
    return prefs


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins for leaf values."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
