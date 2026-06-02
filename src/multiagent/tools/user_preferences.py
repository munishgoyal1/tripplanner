"""Persistent user preferences store.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON file** otherwise (CLI / tests / dev)

Stores family configuration, trip style, budget level, transport/hotel
preferences, dietary needs, and past trip history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from multiagent import storage_cosmos
from multiagent.user_context import get_user_id

_PREFS_DIR = Path.home() / ".multiagent"
_PREFS_FILE = _PREFS_DIR / "user_preferences.json"

_COSMOS_CONTAINER = "users"
_PREFS_DOC_ID = "preferences"

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
    # Free-form observations the agent picks up during conversation.
    # Each entry: {"note": str, "source": "stated" | "inferred", "at": ISO date}
    # Examples: "prefers window seats", "scared of long bus rides",
    # "always travels with mother who needs an elevator".
    "learned_notes": [],
}


def _resolve_prefs_path() -> Path:
    """Path used by the local file backend for the current user.

    The default ("local") user maps to ``_PREFS_FILE`` so tests can monkeypatch
    the module attr. Real per-user IDs (Chainlit sessions) get a scoped subdir.
    """
    uid = get_user_id()
    if uid == "local":
        return _PREFS_FILE
    return _PREFS_DIR / "users" / uid / "preferences.json"


def load_preferences() -> dict[str, Any]:
    """Load preferences, merging with defaults for any missing keys."""
    if storage_cosmos.is_enabled():
        raw = storage_cosmos.read_doc(_COSMOS_CONTAINER, get_user_id(), _PREFS_DOC_ID)
        if raw:
            return _deep_merge(_DEFAULT_PREFS, raw)
        return json.loads(json.dumps(_DEFAULT_PREFS))

    path = _resolve_prefs_path()
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _deep_merge(_DEFAULT_PREFS, raw)
    return json.loads(json.dumps(_DEFAULT_PREFS))


def save_preferences(prefs: dict[str, Any]) -> None:
    """Persist preferences (Cosmos when configured, else local JSON)."""
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(_COSMOS_CONTAINER, get_user_id(), _PREFS_DOC_ID, prefs)
        return

    path = _resolve_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


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


def add_learned_note(note: str, source: str = "stated") -> dict[str, Any]:
    """Append a free-form observation about the user.

    De-dupes by exact note text (case-insensitive) so the same insight isn't
    written twice across turns.
    """
    from datetime import datetime, timezone

    prefs = load_preferences()
    existing = {n.get("note", "").strip().lower() for n in prefs.get("learned_notes", [])}
    cleaned = note.strip()
    if cleaned.lower() in existing or not cleaned:
        return prefs
    prefs.setdefault("learned_notes", []).append({
        "note": cleaned,
        "source": source if source in ("stated", "inferred") else "stated",
        "at": datetime.now(timezone.utc).date().isoformat(),
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
