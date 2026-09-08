"""Pending profile suggestions: what chat noticed, before it becomes durable.

The passive-learning sweep used to overlay whatever it extracted straight onto
the saved preferences. Lab #26 (option D, "chat-led profile") makes that step
explicit instead: a noticed fact is queued here as a *suggestion*, the user
confirms or dismisses it in chat, and only a confirmed suggestion is merged
through the normal additive overlay.

Dismissed suggestions are remembered by fingerprint so the same sentence does
not produce the same question on every trip.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from tripplanner.tools.preferences_merge import additive_overlay_extracted
from tripplanner.tools.user_preferences import load_preferences, mutate_preferences

log = logging.getLogger(__name__)

PENDING_KEY = "profile_suggestions"
DISMISSED_KEY = "dismissed_profile_suggestions"

MAX_PENDING = 12
MAX_DISMISSED = 200

# Human labels for the extractor's nested groups.
_GROUP_LABELS = {
    "profile": "Profile",
    "food_preferences": "Food",
    "transport_preferences": "Travel",
    "hotel_preferences": "Stays",
}
_LIST_KEYS = ("interests", "dislikes")
_SCALAR_KEYS = ("trip_style", "budget_level")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(kind: str, payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{kind}:{body}".encode()).hexdigest()[:16]
    return f"sug_{digest}"


def _humanize(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _record(kind: str, label: str, summary: str, payload: dict, source_text: str) -> dict:
    return {
        "id": _fingerprint(kind, payload),
        "kind": kind,
        "label": label,
        "summary": summary,
        "detail": _humanize(next(iter(payload.values()))) if len(payload) == 1 else "",
        "payload": payload,
        "provenance": "suggested_from_chat",
        "source_text": source_text[:240],
        "created_at": _now(),
    }


def build_suggestions(
    extracted: dict[str, Any],
    learned_notes: list[dict] | None,
    source_text: str,
) -> list[dict]:
    """Turn one extraction result into individually confirmable suggestions."""
    records: list[dict] = []

    for group, group_label in _GROUP_LABELS.items():
        values = extracted.get(group)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if value in (None, "", [], {}):
                continue
            payload = {group: {key: value}}
            pretty = key.replace("_", " ")
            records.append(
                _record(
                    "preference",
                    group_label,
                    f"Remember your {pretty}: {_humanize(value)}?",
                    payload,
                    source_text,
                )
            )

    for key in _LIST_KEYS:
        values = extracted.get(key)
        if not isinstance(values, list) or not values:
            continue
        for value in values:
            records.append(
                _record(
                    "preference",
                    key.capitalize(),
                    f"Add {value} to your {key}?",
                    {key: [value]},
                    source_text,
                )
            )

    for key in _SCALAR_KEYS:
        value = extracted.get(key)
        if value in (None, "", [], {}):
            continue
        records.append(
            _record(
                "preference",
                key.replace("_", " ").capitalize(),
                f"Remember your {key.replace('_', ' ')}: {_humanize(value)}?",
                {key: value},
                source_text,
            )
        )

    for member in extracted.get("family_members") or []:
        if not isinstance(member, dict):
            continue
        name = str(member.get("name") or "").strip()
        relationship = str(member.get("relationship") or "").strip()
        who = name or relationship or "someone"
        records.append(
            _record(
                "family_member",
                "Family",
                f"Add {who} to your travel profile?",
                {"family_members": [member]},
                source_text,
            )
        )

    for note in learned_notes or []:
        if not isinstance(note, dict) or not (note.get("note") or "").strip():
            continue
        records.append(
            _record(
                "note",
                "Noticed",
                f"Remember that {note['note'].strip()}?",
                {"learned_notes": [note]},
                source_text,
            )
        )

    return records


def queue_suggestions(records: list[dict]) -> list[dict]:
    """Persist new suggestions, skipping dismissed and already-pending ones."""
    if not records:
        return []

    accepted: list[dict] = []

    def apply(prefs: dict[str, Any]) -> dict[str, Any]:
        accepted.clear()
        pending = [item for item in (prefs.get(PENDING_KEY) or []) if isinstance(item, dict)]
        dismissed = set(prefs.get(DISMISSED_KEY) or [])
        known = {item.get("id") for item in pending} | dismissed
        for record in records:
            if record["id"] in known:
                continue
            known.add(record["id"])
            pending.append(record)
            accepted.append(record)
        prefs[PENDING_KEY] = pending[-MAX_PENDING:]
        return prefs

    mutate_preferences(apply)
    return accepted


def list_pending() -> list[dict]:
    prefs = load_preferences()
    return [item for item in (prefs.get(PENDING_KEY) or []) if isinstance(item, dict)]


def _apply_payload(prefs: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    notes = payload.get("learned_notes")
    if notes:
        existing = list(prefs.get("learned_notes") or [])
        seen = {
            (entry.get("note") or "").strip().lower()
            for entry in existing
            if isinstance(entry, dict)
        }
        for note in notes:
            text = (note.get("note") or "").strip()
            if text and text.lower() not in seen:
                seen.add(text.lower())
                existing.append(note)
        prefs["learned_notes"] = existing
        return prefs
    return additive_overlay_extracted(prefs, payload)


def resolve(suggestion_id: str, action: str) -> dict | None:
    """Confirm ("save") or decline ("dismiss") one pending suggestion."""
    if action not in {"save", "dismiss"}:
        raise ValueError("action must be 'save' or 'dismiss'")

    resolved: dict[str, Any] = {}

    def apply(prefs: dict[str, Any]) -> dict[str, Any] | None:
        resolved.clear()
        pending = [item for item in (prefs.get(PENDING_KEY) or []) if isinstance(item, dict)]
        match = next((item for item in pending if item.get("id") == suggestion_id), None)
        if match is None:
            return None
        prefs[PENDING_KEY] = [item for item in pending if item.get("id") != suggestion_id]
        if action == "save":
            prefs = _apply_payload(prefs, match.get("payload") or {})
        else:
            dismissed = list(prefs.get(DISMISSED_KEY) or [])
            dismissed.append(suggestion_id)
            prefs[DISMISSED_KEY] = dismissed[-MAX_DISMISSED:]
        resolved.update({**match, "status": "saved" if action == "save" else "dismissed"})
        return prefs

    mutate_preferences(apply)
    return resolved or None
