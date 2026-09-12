"""Automatic profile-save receipts with conditional Undo and optional suggestions.

Clear conversational facts are saved immediately by the background learner.
Uncertain optional suggestions still support explicit save or dismissal.
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from tripplanner.tools.preferences_merge import additive_overlay_extracted, union_keep_existing_case
from tripplanner.tools.user_preferences import load_preferences, mutate_preferences

log = logging.getLogger(__name__)

PENDING_KEY = "profile_suggestions"
DISMISSED_KEY = "dismissed_profile_suggestions"
UPDATES_KEY = "profile_updates"

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
    return datetime.now(UTC).isoformat()


def _fingerprint(kind: str, payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{kind}:{body}".encode()).hexdigest()[:16]
    return f"sug_{digest}"


def _humanize(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_humanize(item) for item in value)
    if isinstance(value, dict):
        if value.get("note"):
            return str(value["note"])
        who = str(value.get("name") or value.get("relationship") or "traveller")
        return f"{who} (age {value['age']})" if value.get("age") is not None else who
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
    return [
        item for item in [*(prefs.get(UPDATES_KEY) or []), *(prefs.get(PENDING_KEY) or [])]
        if isinstance(item, dict)
    ]


def save_extracted(
    prefs: dict, extracted: dict, source: str, baseline: dict, *, sequence: int = 0
) -> list[str]:
    """Apply stated facts atomically, preserving edits made while extraction ran."""
    changes = {}
    for group, incoming in extracted.items():
        if group == "_learned_notes_to_append":
            group = "learned_notes"
        values = incoming.items() if isinstance(incoming, dict) else [(None, incoming)]
        for key, value in values:
            target = prefs.setdefault(group, {}) if key else prefs
            prior = baseline.get(group, {}) if key else baseline
            field = key or group
            path = f"{group}.{key}" if key else group
            versions = prefs.setdefault("_learned_field_versions", {})
            version = versions.get(path) or {}
            if version.get("sequence", -1) > sequence:
                continue
            before = deepcopy(target.get(field))
            if before != prior.get(field) and before != version.get("value"):
                continue
            if isinstance(value, list):
                if group == "family_members":
                    members = deepcopy(before or [])
                    for member in value:
                        matches = [
                            item for item in members
                            if item.get("relationship") == member.get("relationship")
                            and (item.get("name") or "").casefold()
                            == (member.get("name") or "").casefold()
                        ]
                        if not matches:
                            relatives = [
                                item for item in members
                                if item.get("relationship") == member.get("relationship")
                            ]
                            if len(relatives) == 1 and (
                                not relatives[0].get("name") or not member.get("name")
                            ):
                                matches = relatives
                        if len(matches) == 1:
                            for member_key, member_value in member.items():
                                if member_value in (None, ""):
                                    continue
                                matches[0][member_key] = (
                                    union_keep_existing_case(
                                        matches[0].get(member_key) or [], member_value
                                    ) if isinstance(member_value, list) else member_value
                                )
                        elif member not in members:
                            members.append(deepcopy(member))
                    value = members
                elif group == "learned_notes":
                    value = deepcopy(before or []) + [
                        item for item in value if item not in (before or [])
                    ]
                else:
                    value = union_keep_existing_case(before or [], value)
            if value == before or value in (None, "", [], {}):
                continue
            target[field] = deepcopy(value)
            versions[path] = {"sequence": sequence, "value": deepcopy(value)}
            changes[path] = {"before": before, "after": deepcopy(value)}
    if not changes:
        return []
    record = _record(
        "preference", "Travel profile", "Saved from your conversation",
        {}, source,
    )
    record.update({
        "id": _fingerprint("saved", {"source": source, "changes": changes}),
        "status": "saved", "provenance": "stated_in_chat", "changes": changes,
        "detail": ", ".join(path.replace("_", " ") for path in changes),
    })
    record["summary"] = "Remembered: " + "; ".join(
        f"{path.split('.')[-1].replace('_', ' ')}: {_humanize(change['after'])}"
        for path, change in changes.items()
    )[:240]
    prefs[UPDATES_KEY] = [*(prefs.get(UPDATES_KEY) or []), record][-MAX_PENDING:]
    return list(changes)


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
    """Resolve an optional suggestion or undo/dismiss an automatic-save receipt."""
    if action not in {"save", "dismiss", "undo"}:
        raise ValueError("action must be 'save', 'dismiss' or 'undo'")

    resolved: dict[str, Any] = {}

    def apply(prefs: dict[str, Any]) -> dict[str, Any] | None:
        resolved.clear()
        updates = prefs.get(UPDATES_KEY) or []
        saved = next((item for item in updates if item.get("id") == suggestion_id), None)
        if saved:
            if action == "undo":
                for path, change in saved.get("changes", {}).items():
                    parts = path.split(".")
                    target = prefs.get(parts[0], {}) if len(parts) > 1 else prefs
                    field = parts[-1]
                    if target.get(field) == change["after"]:
                        target[field] = change["before"]
            prefs[UPDATES_KEY] = [item for item in updates if item.get("id") != suggestion_id]
            resolved.update({**saved, "status": "undone" if action == "undo" else "dismissed"})
            return prefs
        pending = [item for item in (prefs.get(PENDING_KEY) or []) if isinstance(item, dict)]
        match = next((item for item in pending if item.get("id") == suggestion_id), None)
        if match is None:
            return None
        if action == "undo":
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
