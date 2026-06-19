"""Infer durable preferences from the user's SEARCH behavior.

The agent's search tool calls carry signal the user never states outright:
repeatedly searching business-class flights, always filtering hotels to 5-star,
consistently looking up the same kind of activity. This module observes those
calls (best-effort, from the tools_cache wrapper) and, once a signal is
consistent enough, PROMOTES it to a real preference — conservatively and
additively:

* counts accumulate under ``prefs["behavior_signals"][category][value]``;
* once a value crosses ``_PROMOTE_THRESHOLD``, it's promoted ONCE — a learned
  note is added and the structured field is set only when it's still at its
  default (so an explicit user choice is never overwritten).

Every entry point swallows errors and never raises into the tool call.
"""
from __future__ import annotations

import logging
from typing import Any

from tripplanner.tools.user_preferences import (
    load_preferences,
    save_preferences,
)

log = logging.getLogger(__name__)

# How many times a signal must be seen before it's promoted to a preference.
_PROMOTE_THRESHOLD = 3

_VALID_CABINS = {"economy", "premium_economy", "business", "first"}


def _add_note(prefs: dict[str, Any], note: str) -> None:
    """Append a learned note to ``prefs`` in place, deduped case-insensitively.

    Mutates the passed dict so the caller's single ``save_preferences`` persists
    it — we must NOT call ``user_preferences.add_learned_note`` here because its
    own load/save would be overwritten by the caller's later save.
    """
    from datetime import datetime, timezone

    notes = list(prefs.get("learned_notes") or [])
    cleaned = note.strip()
    if not cleaned:
        return
    if cleaned.lower() in {(n.get("note") or "").strip().lower() for n in notes if isinstance(n, dict)}:
        return
    notes.append({
        "note": cleaned,
        "source": "inferred",
        "at": datetime.now(timezone.utc).date().isoformat(),
    })
    prefs["learned_notes"] = notes


def _add_interest(prefs: dict[str, Any], item: str) -> None:
    """Append an interest to ``prefs`` in place, deduped case-insensitively."""
    cleaned = (item or "").strip()
    if not cleaned:
        return
    bucket = list(prefs.get("interests") or [])
    if cleaned.lower() not in {x.strip().lower() for x in bucket if isinstance(x, str)}:
        bucket.append(cleaned)
        prefs["interests"] = bucket



def _norm_cabin(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    return v if v in _VALID_CABINS else None


def _hotel_rating_floor(value: Any) -> str | None:
    """A narrow high-star filter (min >= 4) is a signal; the default 3,4,5 isn't."""
    if not isinstance(value, str):
        return None
    nums = [int(p) for p in value.replace(" ", "").split(",") if p.isdigit()]
    if not nums:
        return None
    floor = min(nums)
    return str(floor) if floor >= 4 else None


def _categories(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    out: list[str] = []
    for part in value.replace(";", ",").split(","):
        token = part.strip().lower()
        if len(token) >= 3:
            out.append(token)
    return out


def _extract_signals(tool_name: str, args: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (category, value) pairs worth counting for this tool call."""
    if not isinstance(args, dict):
        return []
    signals: list[tuple[str, str]] = []

    if tool_name in ("search_flights_duffel", "search_flights"):
        cabin = _norm_cabin(args.get("cabin_class") or args.get("travel_class"))
        if cabin:
            signals.append(("flight_class", cabin))

    elif tool_name == "search_hotels":
        floor = _hotel_rating_floor(args.get("ratings"))
        if floor:
            signals.append(("hotel_rating_floor", floor))

    elif tool_name in ("search_activities", "search_points_of_interest"):
        for cat in _categories(args.get("categories")):
            signals.append(("activity_interest", cat))

    return signals


def _promote(prefs: dict[str, Any], category: str, value: str) -> bool:
    """Apply a promotion (additive / default-only), mutating ``prefs`` in place.
    Returns True if anything changed so the caller knows to persist."""
    if category == "flight_class":
        if value == "economy":
            return False  # economy is the default — nothing to learn
        transport = dict(prefs.get("transport_preferences") or {})
        if transport.get("flight_class", "economy") == "economy":
            transport["flight_class"] = value
            prefs["transport_preferences"] = transport
        _add_note(prefs, f"Tends to search {value.replace('_', ' ')} class flights")
        return True  # note added (and possibly the field) — persist

    if category == "hotel_rating_floor":
        floor = int(value)
        hotel = dict(prefs.get("hotel_preferences") or {})
        if int(hotel.get("star_rating_min", 3) or 3) < floor:
            hotel["star_rating_min"] = floor
            prefs["hotel_preferences"] = hotel
        _add_note(prefs, f"Tends to filter hotels to {floor}-star and above")
        return True

    if category == "activity_interest":
        _add_interest(prefs, value)
        return True

    return False


def observe(tool_name: str, args: dict[str, Any] | None) -> list[str]:
    """Record search signals for one tool call; promote any that cross the
    threshold. Returns the list of "category:value" promotions applied (for
    tests/telemetry). Best-effort — never raises.
    """
    try:
        signals = _extract_signals(tool_name, args or {})
        if not signals:
            return []

        prefs = load_preferences()
        buckets: dict[str, dict[str, int]] = dict(prefs.get("behavior_signals") or {})
        promoted_state: dict[str, list[str]] = dict(prefs.get("_promoted_signals") or {})
        promoted: list[str] = []
        dirty = False

        for category, value in signals:
            cat_bucket = dict(buckets.get(category) or {})
            cat_bucket[value] = int(cat_bucket.get(value, 0)) + 1
            buckets[category] = cat_bucket
            dirty = True

            already = promoted_state.get(category) or []
            if cat_bucket[value] >= _PROMOTE_THRESHOLD and value not in already:
                if _promote(prefs, category, value):
                    dirty = True
                already = already + [value]
                promoted_state[category] = already
                promoted.append(f"{category}:{value}")

        if dirty:
            prefs["behavior_signals"] = buckets
            prefs["_promoted_signals"] = promoted_state
            save_preferences(prefs)
        return promoted
    except Exception as exc:  # never break a tool call
        log.warning("search-learning observe failed: %s", exc)
        return []
