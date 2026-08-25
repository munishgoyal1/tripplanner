"""Shared, side-effect-free trip primitives.

Low-level helpers used by both the validation and edit clusters of
``trip_planner`` — stop/place normalization, geo distance, HH:MM parsing, and
per-day fullness stats/caps. Split out (tech-debt #8) as a leaf module so the
validation logic can live separately without import cycles; ``trip_planner``
re-exports these names so existing callers and tests resolve unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from tripplanner.web import places_cache

_MAX_DAY_STOPS = 5
_MAX_DAY_DISTANCE_KM = 18.0
_MAX_DAY_DURATION_MIN = 360
_MEAL_PLACEHOLDER_RE = re.compile(
    r"\b(tbd|to be decided|restaurant option|restaurant recommendation|"
    r"lunch stop|dinner stop|breakfast stop|meal stop)\b",
    re.I,
)
_MEAL_NOUN_RE = re.compile(
    r"\b(restaurants?|caf[eé]s?|eater(?:y|ies)|dhaba|bistros?|food courts?|"
    r"dining options?|meal options?)\b",
    re.I,
)
_MEAL_QUALIFIER_RE = re.compile(
    r"\b(a|an|the|in|at|near|local|recommended|popular|traditional|authentic|"
    r"vegetarian|vegan|jain|halal|kosher|gluten[ -]?free|breakfast|brunch|"
    r"lunch|dinner|food|cuisine)\b",
    re.I,
)
_MEAL_PREPOSITION_RE = re.compile(
    r"\b(restaurants?|caf[eé]s?|eater(?:y|ies)|dhaba|bistros?|food courts?)\s+"
    r"(in|at|near|around|close to)\b",
    re.I,
)
_HOTEL_PLACEHOLDER_RE = re.compile(
    r"\b(tbd|to be decided|hotel option|hotel recommendation|"
    r"accommodation option|accommodation recommendation)\b",
    re.I,
)
#: The lodging word itself, plus the adjectives a plan uses to describe a stay it
#: has not actually chosen. "Premium", "accessible" and "budget" restate the
#: brief; none of them identifies a property anyone can book.
_LODGING_NOUN_RE = re.compile(
    r"\b(hotels?|resorts?|homestays?|guest\s?houses?|accommodations?|"
    r"lodges?|stays?|inns?|apartments?|camps?)\b",
    re.I,
)
_LODGING_QUALIFIER_RE = re.compile(
    r"\b(a|an|the|in|at|near|premium|luxury|budget|accessible|boutique|"
    r"comfortable|central|recommended|suitable|family|friendly|pet)\b",
    re.I,
)
#: A preposition straight after the lodging word means what follows is where the
#: stay is, not which stay it is -- no gazetteer needed to know it names nobody.
_LODGING_PREPOSITION_RE = re.compile(
    r"\b(hotels?|resorts?|homestays?|guest\s?houses?|accommodations?|"
    r"lodges?|stays?|inns?|apartments?|camps?)\s+(in|at|near|around|close to)\b",
    re.I,
)


def unnamed_lodging(name: str, cities: set[str]) -> bool:
    """True when a stay names no property -- only a lodging word and a place.

    ``Hotel in Kochi`` and ``Colombo Hotel`` read like plans but cannot be
    booked, reached, or priced, while ``Hotel Olathang`` and ``Taj Swarna,
    Amritsar`` are real. The difference is whether anything survives once the
    lodging word, the describing adjectives and the city are removed.
    """
    text = str(name or "").strip()
    if not text:
        return True
    if not _LODGING_NOUN_RE.search(text):
        return False
    if _LODGING_PREPOSITION_RE.search(text):
        return True
    rest = _LODGING_NOUN_RE.sub(" ", text)
    for city in sorted(cities, key=len, reverse=True):
        city = city.strip()
        if city:
            rest = re.sub(rf"\b{re.escape(city)}\b", " ", rest, flags=re.I)
    rest = _LODGING_QUALIFIER_RE.sub(" ", rest)
    return not re.sub(r"[^A-Za-z0-9]+", "", rest)


def unnamed_meal(name: str, cities: set[str]) -> bool:
    """True when a meal stop describes a preference or place but names no venue."""
    text = str(name or "").strip()
    if not text:
        return True
    if _MEAL_PLACEHOLDER_RE.search(text) or _MEAL_PREPOSITION_RE.search(text):
        return True
    if not _MEAL_NOUN_RE.search(text):
        return False
    rest = _MEAL_NOUN_RE.sub(" ", text)
    for city in sorted(cities, key=len, reverse=True):
        city = city.strip()
        if city:
            rest = re.sub(rf"\b{re.escape(city)}\b", " ", rest, flags=re.I)
    rest = _MEAL_QUALIFIER_RE.sub(" ", rest)
    return not re.sub(r"[^A-Za-z0-9]+", "", rest)


def _is_place_kind(kind: str) -> bool:
    return kind in {"hotel", "attraction", "activity", "meal", "restaurant"}


def _canonical_place_kind(kind: str) -> str:
    if kind == "hotel":
        return "hotel"
    if kind in {"meal", "restaurant"}:
        return "meal"
    return "attraction"


def _summary_for_place(name: str, destination: str) -> dict[str, Any]:
    info = places_cache.get_summary(name, destination) or {}
    return info if isinstance(info, dict) else {}


def _coords_from_summary(summary: dict[str, Any]) -> tuple[float, float] | None:
    lat = summary.get("lat")
    lng = summary.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lng1 = radians(a[0]), radians(a[1])
    lat2, lng2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(h))


def _stop_name(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("name") or "").strip()
    return str(raw or "").strip()


def _stop_kind(raw: Any, default_kind: str = "attraction") -> str:
    if isinstance(raw, dict):
        kind = str(raw.get("kind") or "").strip().lower()
        if kind == "restaurant":
            return "meal"
        if kind in {"hotel", "attraction", "meal", "transport", "flight", "other"}:
            return kind
    return _canonical_place_kind(default_kind)


def _parse_hhmm(value: str) -> int | None:
    text = str(value or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return hh * 60 + mm


def _fmt_hhmm(minutes: int) -> str:
    m = max(0, min(minutes, 23 * 60 + 59))
    return f"{m // 60:02d}:{m % 60:02d}"


def _style_caps(plan: dict[str, Any] | None) -> tuple[int, int, float]:
    """Per-day fullness caps tuned to the trip's style.

    A trip tagged ``relaxed``/``leisure`` should feel unhurried, so it packs
    fewer stops and less driving per day before the rebalancer trims a
    low-value stop; a ``packed`` style tolerates more. Returns
    ``(max_stops, max_duration_min, max_distance_km)``.
    """
    style = str((plan or {}).get("trip_style") or "").strip().lower()
    if style in {"relaxed", "leisure"}:
        return (4, 300, 14.0)
    if style in {"packed", "packed_sightseeing", "adventure", "adventurous"}:
        return (6, 420, 22.0)
    return (_MAX_DAY_STOPS, _MAX_DAY_DURATION_MIN, _MAX_DAY_DISTANCE_KM)


def _day_stats(
    day: dict[str, Any],
    destination: str,
    caps: tuple[int, int, float] | None = None,
) -> dict[str, Any]:
    stops = day.get("stops") if isinstance(day.get("stops"), list) else []
    coords: list[tuple[float, float]] = []
    selected_attractions = 0
    booked = 0
    duration = 0
    for raw in stops:
        name = _stop_name(raw)
        if not name:
            continue
        kind = _stop_kind(raw)
        summary = _summary_for_place(name, destination)
        coords_value = _coords_from_summary(summary)
        if coords_value:
            coords.append(coords_value)
        if kind == "attraction":
            selected_attractions += 1
        if isinstance(raw, dict) and raw.get("booked"):
            booked += 1
        dur = raw.get("duration_min") if isinstance(raw, dict) else None
        if isinstance(dur, (int, float)):
            duration += int(dur)
        elif kind == "hotel":
            duration += 45
        else:
            duration += 90

    route_km = 0.0
    for idx in range(1, len(coords)):
        route_km += _haversine_km(coords[idx - 1], coords[idx])

    max_stops, max_duration, max_km = caps or (
        _MAX_DAY_STOPS,
        _MAX_DAY_DURATION_MIN,
        _MAX_DAY_DISTANCE_KM,
    )
    return {
        "count": len(stops),
        "selected_attractions": selected_attractions,
        "booked": booked,
        "duration_min": duration,
        "route_km": route_km,
        "packed": len(stops) >= max_stops or duration >= max_duration or route_km >= max_km,
    }
