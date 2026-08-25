"""How confidently an itinerary stop names a real, mappable place.

The geocoder answers every query with something, so asking it "where is Dinner?"
returns a specific restaurant the planner never chose. Deciding what a stop *is*
before asking keeps those off the map, and lets a stop the map cannot place be
reported instead of dropped in silence.

Pure string logic (no network, no UI) so both the map-pin builder and its tests
can use it without touching ``places_cache``.
"""

from __future__ import annotations

import re
from typing import Any

# The trip's shape depends on these: where the traveller sleeps, how they arrive
# and leave, and anything already paid for. Missing one breaks the day's route.
ANCHOR = "anchor"
# A named place. The plan survives without its pin; the map is just less useful.
PLACE = "place"
# An activity label ("Free time"), not a place. Pinning it would invent a
# location the plan never chose.
LABEL = "label"

_ANCHOR_KINDS = frozenset({"hotel", "airport", "station", "bus_station", "origin"})

# Words that describe an activity, a time of day, or a generic feature rather
# than naming somewhere. A stop built only from these names no place. Words that
# could anchor a real name ("Marais", "Eiffel") are deliberately absent, and the
# borderline ones ("old", "town") are included on purpose: a wrongly quiet stop
# is recoverable from the map's list, a wrongly placed pin sends someone across
# the city.
_GENERIC_TOKENS = frozenset({
    "activities", "activity", "afternoon", "and", "area", "around", "arrival",
    "arrive", "beach", "breakfast", "brunch", "check", "checkin", "checkout",
    "center", "centre", "city", "class", "day", "days", "depart", "departure",
    "dinner", "district", "dive", "diving",
    "downtown", "drinks", "evening", "explore", "exploring", "for", "free",
    "from", "home", "hotel", "late", "leisure", "local", "lunch", "meal",
    "morning", "near", "nearby", "night", "old", "onward", "optional", "our",
    "own", "pace", "pool", "relax", "restaurant", "rest", "return", "scuba",
    "shop", "shopping", "sightseeing", "snack", "spa", "stay", "stroll",
    "supper", "tbd", "the", "time", "tour", "town", "transfer", "travel", "trip",
    "visit", "walk", "walking", "with", "your",
})


def _identity_tokens(name: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", str(name or "").lower()) if len(token) > 2]


def names_a_place(text: str) -> bool:
    """Whether a phrase identifies somewhere, rather than describing a day."""
    tokens = _identity_tokens(text)
    return bool(tokens) and not all(token in _GENERIC_TOKENS for token in tokens)


def stop_place_tier(
    name: str,
    kind: str,
    *,
    selected: frozenset[str] | set[str] = frozenset(),
    booked: bool = False,
) -> str:
    """Classify one itinerary stop by what is lost when the map cannot place it."""
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind in _ANCHOR_KINDS or booked:
        return ANCHOR
    # An explicit pick is a real place even when its name reads generic.
    if str(name or "").strip().lower() in selected:
        return PLACE
    tokens = _identity_tokens(name)
    if tokens and all(token in _GENERIC_TOKENS for token in tokens):
        return LABEL
    return PLACE


def stop_is_booked(stop: Any) -> bool:
    if not isinstance(stop, dict):
        return False
    if stop.get("booked"):
        return True
    price = stop.get("price") or stop.get("cost")
    return bool(price) and str(price).strip() not in {"", "0"}


def confirmed_bindings(trip: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Stop name -> the place the user confirmed for it."""
    raw = (trip or {}).get("place_bindings")
    if not isinstance(raw, dict):
        return {}
    bindings: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            continue
        if value.get("lat") is None or value.get("lng") is None:
            continue
        bindings[str(name).strip().lower()] = value
    return bindings
