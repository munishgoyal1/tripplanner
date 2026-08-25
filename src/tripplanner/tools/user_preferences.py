"""Persistent user preferences store.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON file** otherwise (CLI / tests / dev)

Stores family configuration, trip style, budget level, transport/hotel
preferences, dietary needs, and past trip history.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from tripplanner import storage_cosmos
from tripplanner.user_context import get_user_id

log = logging.getLogger(__name__)

_PREFS_DIR = Path.home() / ".tripplanner"
_PREFS_FILE = _PREFS_DIR / "user_preferences.json"

_COSMOS_CONTAINER = "users"
_PREFS_DOC_ID = "preferences"
_COSMOS_WRITE_ATTEMPTS = 3
_LOCAL_LOCKS: dict[str, Lock] = {}
_LOCAL_LOCKS_GUARD = Lock()

_DEFAULT_PREFS: dict[str, Any] = {
    # Who the user is (extracted passively from conversation)
    "profile": {
        "display_name": None,     # "Munish"
        "home_city": None,        # "Bengaluru"
        "home_area": None,        # "Whitefield"
        "home_country": None,     # "India"
        "display_region": None,   # Country or region used for presentation defaults
        "display_language": "en", # Presentation language selected by the traveller
        "passport_country": None,  # "Indian" — what they travel on, NOT where they live
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
    "planning_preferences": {
        "target_active_minutes_per_full_day": None,
        "preferred_free_time_ratio": None,
        "major_attractions_per_day": None,
        "preferred_day_start": None,
        "preferred_day_end": None,
    },
    "offer_benefits": [],
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
        "preferred_road_transport": None,  # own_car | taxi | either
        "max_continuous_drive_min": None,
        "road_break_duration_min": None,
        "road_break_preferences": [],  # snack, meal, restroom, stretch, scenic
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
    # Counters the system maintains from the user's SEARCH behavior (cabin
    # class searched, hotel star floor, activity categories). Internal — used
    # by search_learning to promote consistent signals into real preferences.
    # Shape: {category: {value: count}}.
    "behavior_signals": {},
    # User-authored free-text "About me" written via the ChatSettings panel.
    # Treated as the SOURCE OF TRUTH for whatever it covers: when the user
    # saves a new value the LLM extracts structured fields from it and
    # overwrites the corresponding individual fields (home_city, interests,
    # dietary, etc.). The raw text is also kept verbatim so the agent can
    # quote it back when reasoning.
    "about_me": "",    # SYSTEM-authored running summary of the user, synthesized by the LLM from
    # all durable signals (about_me + structured prefs + interests/dislikes +
    # family + learned_notes + past_trips). Distinct from "about_me" (which the
    # user owns/edits): this is derived output the system maintains and the user
    # may correct or reset. Regenerated only when durable facts change.
    "profile_summary": "",
    "profile_summary_updated_at": None,
    # How the agent handles a new trip request. "direct" (default) means jump
    # straight to a full plan + searches without stopping to ask clarifying
    # questions first. "interactive" means the agent may pause to ask for any
    # missing info it can't confidently infer (dates, companion count, budget).
    "planning_mode": "direct",
    "display_currency": "USD",
    # Cheap digest of the durable signals the last summary was built from — lets
    # update_summary() skip the LLM call when nothing durable changed.
    "profile_summary_digest": "",}


def _resolve_prefs_path() -> Path:
    """Path used by the local file backend for the current user.

    The default ("local") user maps to ``_PREFS_FILE`` so tests can monkeypatch
    the module attr. Real per-user IDs (OAuth/guest sessions) get a scoped subdir.
    """
    uid = get_user_id()
    if uid == "local":
        return _PREFS_FILE
    return _PREFS_DIR / "users" / uid / "preferences.json"


def _local_lock(path: Path) -> Lock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, Lock())


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


# Soft cap on free-form learned_notes so the list can't bloat the prompt
# unbounded over the life of an account. Oldest duplicates are folded out and,
# if still over cap, the oldest entries are dropped (most recent kept).
_MAX_LEARNED_NOTES = 200


def _consolidate_learned_notes(notes: list[Any]) -> list[Any]:
    """De-dupe learned notes (case-insensitive, keep oldest) and cap the list."""
    if not isinstance(notes, list):
        return []
    deduped: list[Any] = []
    seen: set[str] = set()
    for entry in notes:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("note") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    if len(deduped) > _MAX_LEARNED_NOTES:
        deduped = deduped[-_MAX_LEARNED_NOTES:]
    return deduped


def _prepare_preferences(prefs: dict[str, Any]) -> dict[str, Any]:
    prepared = copy.deepcopy(prefs)
    if isinstance(prepared.get("learned_notes"), list):
        prepared["learned_notes"] = _consolidate_learned_notes(
            prepared["learned_notes"]
        )
    return prepared


def adopt_missing_preferences(
    current: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Fill default-valued fields from another identity without replacing account data."""
    explicit_fields = {str(value) for value in current.get("_explicit_fields") or []}
    incoming_explicit_fields = {
        str(value) for value in incoming.get("_explicit_fields") or []
    }
    adopted_explicit_fields: set[str] = set()

    def merge_family_members(current_value: Any, incoming_value: Any) -> list[Any]:
        from tripplanner.tools.preferences_merge import merge_family_member

        members = copy.deepcopy(current_value) if isinstance(current_value, list) else []
        index: dict[tuple[str, str], int] = {}
        for member_index, member in enumerate(members):
            if not isinstance(member, dict):
                continue
            relationship = str(member.get("relationship") or "").strip().lower()
            name = str(member.get("name") or "").strip().lower()
            if name:
                index[(relationship, name)] = member_index
        for incoming_member in incoming_value if isinstance(incoming_value, list) else []:
            if not isinstance(incoming_member, dict):
                if incoming_member not in members:
                    members.append(copy.deepcopy(incoming_member))
                continue
            relationship = str(incoming_member.get("relationship") or "").strip().lower()
            name = str(incoming_member.get("name") or "").strip().lower()
            key = (relationship, name)
            if name and key in index:
                member_index = index[key]
                members[member_index] = merge_family_member(
                    members[member_index], incoming_member
                )
            else:
                members.append(copy.deepcopy(incoming_member))
                if name:
                    index[key] = len(members) - 1
        return members

    def merge(
        current_value: Any,
        incoming_value: Any,
        default_value: Any,
        path: str = "",
    ) -> Any:
        if path in explicit_fields:
            return copy.deepcopy(current_value)
        if isinstance(default_value, dict):
            current_dict = current_value if isinstance(current_value, dict) else {}
            incoming_dict = incoming_value if isinstance(incoming_value, dict) else {}
            return {
                key: merge(
                    current_dict.get(key),
                    incoming_dict.get(key),
                    default_child,
                    f"{path}.{key}" if path else key,
                )
                for key, default_child in default_value.items()
            } | {
                key: copy.deepcopy(value)
                for key, value in current_dict.items()
                if key not in default_value
            }
        if isinstance(default_value, list):
            current_list = current_value if isinstance(current_value, list) else []
            incoming_list = incoming_value if isinstance(incoming_value, list) else []
            if path == "family_members":
                merged_list = merge_family_members(current_list, incoming_list)
            else:
                merged_list = copy.deepcopy(current_list)
                for value in incoming_list:
                    if value not in merged_list:
                        merged_list.append(copy.deepcopy(value))
            if path in incoming_explicit_fields and (
                current_list == default_value or merged_list != current_list
            ):
                adopted_explicit_fields.add(path)
            return merged_list
        if current_value != default_value:
            return copy.deepcopy(current_value)
        if incoming_value != default_value:
            if path in incoming_explicit_fields:
                adopted_explicit_fields.add(path)
            return copy.deepcopy(incoming_value)
        if path in incoming_explicit_fields:
            adopted_explicit_fields.add(path)
        return copy.deepcopy(current_value)

    merged = merge(current, incoming, _DEFAULT_PREFS)
    merged["_explicit_fields"] = sorted(explicit_fields | adopted_explicit_fields)
    return merged


def mark_explicit_fields(preferences: dict[str, Any], fields: set[str]) -> None:
    existing = {str(value) for value in preferences.get("_explicit_fields") or []}
    preferences["_explicit_fields"] = sorted(existing | fields)


def has_non_default_preferences(preferences: dict[str, Any]) -> bool:
    """Whether an identity has durable preference data worth adopting."""
    return bool(preferences.get("_explicit_fields")) or any(
        preferences.get(key, copy.deepcopy(default)) != default
        for key, default in _DEFAULT_PREFS.items()
    )


def save_preferences(prefs: dict[str, Any]) -> None:
    """Replace the complete preference document with conflict detection."""
    prepared = _prepare_preferences(prefs)

    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        current = storage_cosmos.read_doc_versioned(
            _COSMOS_CONTAINER, user_id, _PREFS_DOC_ID
        )
        if current is None:
            storage_cosmos.create_doc_if_absent(
                _COSMOS_CONTAINER, user_id, _PREFS_DOC_ID, prepared
            )
        else:
            storage_cosmos.replace_doc_if_version(
                _COSMOS_CONTAINER,
                user_id,
                _PREFS_DOC_ID,
                prepared,
                current.version,
            )
        return

    path = _resolve_prefs_path()
    with _local_lock(path):
        _write_json_file_atomic(path, prepared)


def mutate_preferences(
    mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Apply a preference mutation, replaying it after Cosmos write conflicts."""
    if not storage_cosmos.is_enabled():
        path = _resolve_prefs_path()
        with _local_lock(path):
            raw = _read_json_file(path)
            current = (
                _deep_merge(_DEFAULT_PREFS, raw)
                if raw is not None
                else copy.deepcopy(_DEFAULT_PREFS)
            )
            updated = mutator(current)
            if updated is None:
                return current
            prepared = _prepare_preferences(updated)
            _write_json_file_atomic(path, prepared)
            return prepared

    user_id = get_user_id()
    for attempt in range(_COSMOS_WRITE_ATTEMPTS):
        versioned = storage_cosmos.read_doc_versioned(
            _COSMOS_CONTAINER, user_id, _PREFS_DOC_ID
        )
        if versioned is None:
            current = copy.deepcopy(_DEFAULT_PREFS)
        else:
            current = _deep_merge(_DEFAULT_PREFS, versioned.body)

        updated = mutator(current)
        if updated is None:
            return current
        prepared = _prepare_preferences(updated)

        try:
            if versioned is None:
                storage_cosmos.create_doc_if_absent(
                    _COSMOS_CONTAINER, user_id, _PREFS_DOC_ID, prepared
                )
            else:
                storage_cosmos.replace_doc_if_version(
                    _COSMOS_CONTAINER,
                    user_id,
                    _PREFS_DOC_ID,
                    prepared,
                    versioned.version,
                )
        except storage_cosmos.WriteConflictError:
            if attempt == _COSMOS_WRITE_ATTEMPTS - 1:
                raise
            continue
        return prepared

    raise AssertionError("unreachable")


def reset_preferences() -> dict[str, Any]:
    """Reset preferences to the default schema and persist."""
    fresh = json.loads(json.dumps(_DEFAULT_PREFS))
    return mutate_preferences(lambda _current: fresh)


def update_preferences(updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge updates into existing preferences and save.

    List fields in ``_ADDITIVE_LIST_PATHS`` (interests, dislikes, dietary,
    cuisine likes/dislikes, hotel amenities/chains, accessibility needs) are
    UNIONED with what's already saved instead of being replaced — so the agent
    calling ``save_travel_preferences`` with e.g. ``{"food_preferences":
    {"dietary": ["vegan"]}}`` can never wipe previously learned dietary needs.
    All other leaves keep replace-wins semantics.
    """
    return mutate_preferences(lambda current: _deep_merge_additive(current, updates))


def add_past_trip(
    destination: str,
    dates: str,
    rating: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Append a trip to history and save."""
    entry = {
        "destination": destination,
        "dates": dates,
        "rating": rating,
        "notes": notes,
    }

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        prefs["past_trips"] = list(prefs.get("past_trips") or []) + [entry]
        return prefs

    return mutate_preferences(apply)


def update_past_trip_postmortem(
    destination: str,
    rating: int | None,
    what_worked: list[str] | None,
    what_didnt: list[str] | None,
    dates: str = "",
    pace_feedback: str = "",
    actual_active_minutes_per_full_day: int | None = None,
) -> dict[str, Any]:
    """Attach a structured post-mortem to a past trip.

    Matches the most recent past_trip whose destination is a case-insensitive
    substring match. If no match, appends a new entry. Rating, what_worked,
    and what_didnt are stored on the entry; non-empty lists are also surfaced
    into learned_notes (source=stated) so future planning sessions can recall
    them via memory_recall without re-reading the full trip log.
    """
    dest_l = (destination or "").strip().lower()
    worked = [w.strip() for w in (what_worked or []) if isinstance(w, str) and w.strip()]
    didnt = [d.strip() for d in (what_didnt or []) if isinstance(d, str) and d.strip()]
    normalized_pace = str(pace_feedback or "").strip().lower()
    if normalized_pace not in {"too_rushed", "just_right", "too_sparse"}:
        normalized_pace = ""
    active_minutes = (
        max(180, min(600, actual_active_minutes_per_full_day))
        if isinstance(actual_active_minutes_per_full_day, int)
        and not isinstance(actual_active_minutes_per_full_day, bool)
        else None
    )

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        from datetime import UTC, datetime

        trips = prefs.setdefault("past_trips", [])
        target = None
        if dest_l:
            for trip in reversed(trips):
                if dest_l in str(trip.get("destination", "")).lower():
                    target = trip
                    break
        if target is None:
            target = {
                "destination": destination,
                "dates": dates,
                "rating": None,
                "notes": "",
            }
            trips.append(target)

        if rating is not None:
            target["rating"] = rating
        if dates:
            target["dates"] = dates
        if worked:
            target["what_worked"] = worked
        if didnt:
            target["what_didnt"] = didnt
        if normalized_pace:
            target["pace_feedback"] = normalized_pace
        if active_minutes is not None:
            target["actual_active_minutes_per_full_day"] = active_minutes

        notes = list(prefs.get("learned_notes") or [])
        seen = {
            (entry.get("note") or "").strip().lower()
            for entry in notes
            if isinstance(entry, dict)
        }
        dest_label = destination or target.get("destination") or "this trip"
        day = datetime.now(UTC).date().isoformat()
        for note in [
            *(f"Liked on {dest_label} trip: {item}" for item in worked),
            *(f"Disliked on {dest_label} trip: {item}" for item in didnt),
        ]:
            if note.lower() in seen:
                continue
            seen.add(note.lower())
            notes.append({"note": note, "source": "stated", "at": day})
        prefs["learned_notes"] = notes
        return prefs

    return mutate_preferences(apply)


def add_learned_note(note: str, source: str = "stated") -> dict[str, Any]:
    """Append a free-form observation about the user.

    De-dupes by exact note text (case-insensitive) so the same insight isn't
    written twice across turns.
    """
    from datetime import datetime, timezone

    cleaned = note.strip()
    if not cleaned:
        return load_preferences()
    entry = {
        "note": cleaned,
        "source": source if source in ("stated", "inferred") else "stated",
        "at": datetime.now(timezone.utc).date().isoformat(),
    }

    def apply(prefs: dict[str, Any]) -> dict[str, Any] | None:
        existing = {
            item.get("note", "").strip().lower()
            for item in prefs.get("learned_notes", [])
            if isinstance(item, dict)
        }
        if cleaned.lower() in existing:
            return None
        prefs.setdefault("learned_notes", []).append(entry)
        return prefs

    return mutate_preferences(apply)


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
    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
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
        return prefs

    return mutate_preferences(apply)


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

    def _key(m: dict[str, Any]) -> tuple[str, str]:
        return (
            (m.get("relationship") or "").strip().lower(),
            (m.get("name") or "").strip().lower(),
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

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        members = list(prefs.get("family_members") or [])
        target_key = (rel, (nm or "").lower())
        existing_idx = next(
            (i for i, member in enumerate(members) if _key(member) == target_key),
            None,
        )

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
        return prefs

    return mutate_preferences(apply)


def _family_member_key(relationship: str, name: str) -> tuple[str, str]:
    return (relationship or "").strip().lower(), (name or "").strip().lower()


def set_family_member(
    *,
    original_relationship: str | None,
    original_name: str | None,
    relationship: str,
    name: str,
    age: int | None,
    dietary: list[str],
    mobility: list[str],
    interests: list[str],
    notes: str,
) -> dict[str, Any]:
    """Add or fully replace one traveller's editable profile, keyed by (relationship, name).

    Unlike ``upsert_family_member`` (additive chat learning), every field here
    is set to exactly what the caller sent, since this backs a direct editing
    UI where clearing a tag or renaming a person must take effect immediately.
    """
    rel = (relationship or "").strip().lower()
    if rel not in _VALID_RELATIONSHIPS:
        rel = "other"
    original_key = (
        _family_member_key(original_relationship, original_name or "")
        if original_relationship
        else None
    )
    member = {
        "relationship": rel,
        "name": (name or "").strip() or None,
        "age": age,
        "dietary": [t.strip() for t in dietary if t.strip()],
        "mobility": [t.strip() for t in mobility if t.strip()],
        "interests": [t.strip() for t in interests if t.strip()],
        "notes": (notes or "").strip() or None,
    }

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        members = list(prefs.get("family_members") or [])
        target_index = None
        if original_key is not None:
            target_index = next(
                (i for i, m in enumerate(members) if _family_member_key(m.get("relationship", ""), m.get("name") or "") == original_key),
                None,
            )
        if target_index is not None:
            members[target_index] = member
        else:
            members.append(member)
        prefs["family_members"] = members
        return prefs

    return mutate_preferences(apply)


def remove_family_member(relationship: str, name: str) -> dict[str, Any]:
    """Remove one traveller, keyed by (relationship, name)."""
    target_key = _family_member_key(relationship, name)

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        members = [
            m for m in (prefs.get("family_members") or [])
            if _family_member_key(m.get("relationship", ""), m.get("name") or "") != target_key
        ]
        prefs["family_members"] = members
        return prefs

    return mutate_preferences(apply)



def _append_unique_str(field: str, item: str) -> dict[str, Any]:
    cleaned = (item or "").strip()
    if not cleaned:
        return load_preferences()

    def apply(prefs: dict[str, Any]) -> dict[str, Any] | None:
        bucket = list(prefs.get(field) or [])
        if cleaned.lower() in {
            value.strip().lower() for value in bucket if isinstance(value, str)
        }:
            return None
        bucket.append(cleaned)
        prefs[field] = bucket
        return prefs

    return mutate_preferences(apply)


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
    sentiment_norm = (
        sentiment
        if sentiment in ("positive", "negative", "mixed", "neutral")
        else "neutral"
    )
    source_norm = source if source in ("stated", "inferred") else "stated"

    target_key = (dest.lower(), (when_norm or "").lower())
    entry = {
        "destination": dest,
        "when": when_norm,
        "with_whom": (with_whom or "").strip() or None,
        "sentiment": sentiment_norm,
        "notes": (notes or "").strip(),
        "source": source_norm,
        "at": datetime.now(timezone.utc).date().isoformat(),
    }

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        mentions = list(prefs.get("past_trip_mentions") or [])
        existing_idx = next(
            (
                index
                for index, mention in enumerate(mentions)
                if (
                    (mention.get("destination") or "").strip().lower(),
                    (mention.get("when") or "").strip().lower(),
                ) == target_key
            ),
            None,
        )
        if existing_idx is not None:
            nonempty = {key: value for key, value in entry.items() if value not in (None, "")}
            mentions[existing_idx] = {**mentions[existing_idx], **nonempty}
        else:
            mentions.append(entry)
        prefs["past_trip_mentions"] = mentions
        return prefs

    return mutate_preferences(apply)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins for leaf values."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


# Dotted paths whose list values are ADDITIVE (unioned) rather than replaced
# when written via update_preferences / save_travel_preferences. Keeps the save
# path consistent with the "always additive, never remove" rule the rest of the
# learning system follows.
_ADDITIVE_LIST_PATHS: frozenset[str] = frozenset({
    "interests",
    "dislikes",
    "accessibility_needs",
    "food_preferences.dietary",
    "food_preferences.cuisine_likes",
    "food_preferences.cuisine_dislikes",
    "hotel_preferences.preferred_amenities",
    "hotel_preferences.preferred_chains",
})


def _union_ci(existing: list[Any] | None, incoming: list[Any] | None) -> list[Any]:
    """Append ``incoming`` to ``existing`` with case-insensitive dedupe for
    strings (existing casing wins). Non-string items dedupe by value."""
    out: list[Any] = []
    seen: set[Any] = set()
    for item in list(existing or []) + list(incoming or []):
        if item is None:
            continue
        if isinstance(item, str):
            s = item.strip()
            if not s:
                continue
            key: Any = s.lower()
        else:
            s = item
            key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _deep_merge_additive(base: dict, override: dict, prefix: str = "") -> dict:
    """Like ``_deep_merge`` but UNIONS list leaves at ``_ADDITIVE_LIST_PATHS``
    instead of replacing them. Other leaves keep replace-wins semantics."""
    result = base.copy()
    for key, val in override.items():
        path = f"{prefix}{key}"
        cur = result.get(key)
        if isinstance(cur, dict) and isinstance(val, dict):
            result[key] = _deep_merge_additive(cur, val, prefix=f"{path}.")
        elif path in _ADDITIVE_LIST_PATHS and isinstance(val, list):
            result[key] = _union_ci(cur if isinstance(cur, list) else [], val)
        else:
            result[key] = val
    return result

