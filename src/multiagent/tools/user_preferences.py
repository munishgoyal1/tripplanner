"""Persistent user preferences store.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON file** otherwise (CLI / tests / dev)

Stores family configuration, trip style, budget level, transport/hotel
preferences, dietary needs, and past trip history.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from multiagent import storage_cosmos
from multiagent.user_context import get_user_id

log = logging.getLogger(__name__)

_PREFS_DIR = Path.home() / ".multiagent"
_PREFS_FILE = _PREFS_DIR / "user_preferences.json"

_COSMOS_CONTAINER = "users"
_PREFS_DOC_ID = "preferences"

_DEFAULT_PREFS: dict[str, Any] = {
    # Who the user is (extracted passively from conversation)
    "profile": {
        "display_name": None,     # "Munish"
        "home_city": None,        # "Bengaluru"
        "home_country": None,     # "India"
        "age_band": None,         # "20-30" | "30-40" | "40-50" | "50-60" | "60+"
        "occupation": None,       # "software engineer" | "doctor" | ...
    },
    # Rich family roster (richer than the legacy `family` counts below)
    # Each: {relationship, name, age, dietary, mobility, interests, notes}
    "family_members": [],
    # High-level interests / dislikes the user reveals over time
    "interests": [],              # ["hiking", "food", "culture", "photography"]
    "dislikes": [],               # ["crowded places", "long drives", "spicy food"]
    # Trips the user CASUALLY MENTIONED (not planned by this agent).
    # Each: {destination, when, with_whom, sentiment, notes, source, at}
    "past_trip_mentions": [],
    # Legacy counters (kept for back-compat; family_members is the new source of truth)
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
    "past_trips": [],  # agent-planned trips: [{destination, dates, rating, notes}]
    # Free-form observations the agent picks up during conversation.
    # Each entry: {"note": str, "source": "stated" | "inferred", "at": ISO date}
    # Examples: "prefers window seats", "scared of long bus rides",
    # "always travels with mother who needs an elevator".
    "learned_notes": [],
    # User-authored free-text "About me" written via the ChatSettings panel.
    # Treated as the SOURCE OF TRUTH for whatever it covers: when the user
    # saves a new value the LLM extracts structured fields from it and
    # overwrites the corresponding individual fields (home_city, interests,
    # dietary, etc.). The raw text is also kept verbatim so the agent can
    # quote it back when reasoning.
    "about_me": "",
}


def _resolve_prefs_path() -> Path:
    """Path used by the local file backend for the current user.

    The default ("local") user maps to ``_PREFS_FILE`` so tests can monkeypatch
    the module attr. Real per-user IDs (OAuth/guest sessions) get a scoped subdir.
    """
    uid = get_user_id()
    if uid == "local":
        return _PREFS_FILE
    return _PREFS_DIR / "users" / uid / "preferences.json"


def _read_json_file(path: Path) -> dict[str, Any] | None:
    """Read a JSON file tolerantly.

    Returns ``None`` if the file is missing, empty, or contains invalid JSON
    (e.g. a half-written file from a concurrent crash). The caller falls back
    to defaults. We log a warning so the corruption isn't silent, and the
    corrupted file is renamed to ``*.corrupt`` so the user can inspect it.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        backup = path.with_suffix(path.suffix + ".corrupt")
        try:
            path.replace(backup)
            log.warning(
                "Preferences file %s was corrupt (%s); moved to %s and restoring defaults",
                path,
                exc,
                backup,
            )
        except OSError:
            log.warning("Preferences file %s was corrupt (%s)", path, exc)
        return None


def _write_json_file_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically so concurrent reads never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Write to a sibling temp file then rename. On Windows, os.replace is atomic
    # within the same directory.
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_preferences() -> dict[str, Any]:
    """Load preferences, merging with defaults for any missing keys."""
    if storage_cosmos.is_enabled():
        raw = storage_cosmos.read_doc(_COSMOS_CONTAINER, get_user_id(), _PREFS_DOC_ID)
        if raw:
            return _deep_merge(_DEFAULT_PREFS, raw)
        return json.loads(json.dumps(_DEFAULT_PREFS))

    path = _resolve_prefs_path()
    raw = _read_json_file(path)
    if raw is not None:
        return _deep_merge(_DEFAULT_PREFS, raw)
    return json.loads(json.dumps(_DEFAULT_PREFS))


def save_preferences(prefs: dict[str, Any]) -> None:
    """Persist preferences (Cosmos when configured, else local JSON)."""
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(_COSMOS_CONTAINER, get_user_id(), _PREFS_DOC_ID, prefs)
        return

    _write_json_file_atomic(_resolve_prefs_path(), prefs)


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


_VALID_RELATIONSHIPS = {
    "self", "spouse", "partner", "child", "parent", "sibling",
    "friend", "pet", "other",
}


def update_profile(updates: dict[str, Any]) -> dict[str, Any]:
    """Patch the user's profile (display_name, home_city, etc.).

    Only non-None values in `updates` are applied — explicit None is treated
    as 'don't touch this field' rather than 'clear it' so the agent can call
    the tool with partial info safely.
    """
    prefs = load_preferences()
    profile = dict(prefs.get("profile") or {})
    for key, val in updates.items():
        if val is None:
            continue
        if isinstance(val, str):
            val = val.strip()
            if not val:
                continue
        profile[key] = val
    prefs["profile"] = profile
    save_preferences(prefs)
    return prefs


def upsert_family_member(
    relationship: str,
    name: str | None = None,
    age: int | None = None,
    dietary: list[str] | None = None,
    mobility: list[str] | None = None,
    interests: list[str] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add or update a family member, keyed by (relationship, name).

    Match is case-insensitive on both. When a match exists, non-None fields
    overwrite; list fields are merged (de-duped). Unknown relationship maps
    to 'other'.
    """
    rel = (relationship or "").strip().lower()
    if rel not in _VALID_RELATIONSHIPS:
        rel = "other"
    nm = (name or "").strip() or None

    prefs = load_preferences()
    members = list(prefs.get("family_members") or [])

    def _key(m: dict[str, Any]) -> tuple[str, str]:
        return (
            (m.get("relationship") or "").strip().lower(),
            (m.get("name") or "").strip().lower(),
        )

    target_key = (rel, (nm or "").lower())
    existing_idx = next(
        (i for i, m in enumerate(members) if _key(m) == target_key),
        None,
    )

    def _merge_list(old: list[str] | None, new: list[str] | None) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in (old or []) + (new or []):
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                merged.append(cleaned)
        return merged

    if existing_idx is not None:
        member = dict(members[existing_idx])
        if age is not None:
            member["age"] = age
        if dietary is not None:
            member["dietary"] = _merge_list(member.get("dietary"), dietary)
        if mobility is not None:
            member["mobility"] = _merge_list(member.get("mobility"), mobility)
        if interests is not None:
            member["interests"] = _merge_list(member.get("interests"), interests)
        if notes is not None and notes.strip():
            member["notes"] = notes.strip()
        members[existing_idx] = member
    else:
        members.append({
            "relationship": rel,
            "name": nm,
            "age": age,
            "dietary": _merge_list(None, dietary),
            "mobility": _merge_list(None, mobility),
            "interests": _merge_list(None, interests),
            "notes": (notes or "").strip() or None,
        })

    prefs["family_members"] = members
    save_preferences(prefs)
    return prefs


def _append_unique_str(field: str, item: str) -> dict[str, Any]:
    cleaned = (item or "").strip()
    if not cleaned:
        return load_preferences()
    prefs = load_preferences()
    bucket = list(prefs.get(field) or [])
    if cleaned.lower() not in {x.strip().lower() for x in bucket if isinstance(x, str)}:
        bucket.append(cleaned)
        prefs[field] = bucket
        save_preferences(prefs)
    return prefs


def add_interest(item: str) -> dict[str, Any]:
    """Append a high-level interest (de-duped, case-insensitive)."""
    return _append_unique_str("interests", item)


def add_dislike(item: str) -> dict[str, Any]:
    """Append a high-level dislike (de-duped, case-insensitive)."""
    return _append_unique_str("dislikes", item)


def add_trip_mention(
    destination: str,
    when: str | None = None,
    with_whom: str | None = None,
    sentiment: str = "neutral",
    notes: str = "",
    source: str = "stated",
) -> dict[str, Any]:
    """Record a trip the user casually mentioned (NOT planned by this agent).

    De-dupes by (destination, when) case-insensitive — if the same pair shows
    up again, the existing entry's sentiment/notes get updated instead of a
    duplicate row being added.
    """
    from datetime import datetime, timezone

    dest = (destination or "").strip()
    if not dest:
        return load_preferences()
    when_norm = (when or "").strip() or None
    sentiment_norm = sentiment if sentiment in ("positive", "negative", "mixed", "neutral") else "neutral"
    source_norm = source if source in ("stated", "inferred") else "stated"

    prefs = load_preferences()
    mentions = list(prefs.get("past_trip_mentions") or [])
    target_key = (dest.lower(), (when_norm or "").lower())
    existing_idx = next(
        (
            i for i, m in enumerate(mentions)
            if (
                (m.get("destination") or "").strip().lower(),
                (m.get("when") or "").strip().lower(),
            ) == target_key
        ),
        None,
    )
    entry = {
        "destination": dest,
        "when": when_norm,
        "with_whom": (with_whom or "").strip() or None,
        "sentiment": sentiment_norm,
        "notes": (notes or "").strip(),
        "source": source_norm,
        "at": datetime.now(timezone.utc).date().isoformat(),
    }
    if existing_idx is not None:
        merged = {**mentions[existing_idx], **{k: v for k, v in entry.items() if v not in (None, "")}}
        mentions[existing_idx] = merged
    else:
        mentions.append(entry)
    prefs["past_trip_mentions"] = mentions
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
