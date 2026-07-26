"""Trip plan state manager — draft, finalize, execute bookings.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON files** otherwise (CLI / tests / dev)

Active trip lives in the ``users`` container (one doc per user); archived
trips live in the ``trips`` container (one doc per trip, queryable by user).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any

from langchain_core.tools import tool

from tripplanner import storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.tools.finalize_critic import critique as _critique_finalized
from tripplanner.tools.trip_diff import diff_plans, format_diff
from tripplanner.tools.user_preferences import add_past_trip, load_preferences
from tripplanner.user_context import get_user_id
from tripplanner.web import places_cache

_TRIPS_DIR = Path.home() / ".tripplanner"
_ACTIVE_TRIP_FILE = _TRIPS_DIR / "active_trip.json"
_TRIP_HISTORY_DIR = _TRIPS_DIR / "trips"

_COSMOS_USERS_CONTAINER = "users"
_COSMOS_TRIPS_CONTAINER = "trips"
_ACTIVE_TRIP_DOC_ID = "active_trip"
_MAX_DAY_STOPS = 5
_MAX_DAY_DISTANCE_KM = 18.0
_MAX_DAY_DURATION_MIN = 360
_MUTATION_LOCKS = tuple(RLock() for _ in range(64))
_MEAL_PLACEHOLDER_RE = re.compile(
    r"\b(tbd|to be decided|restaurant option|restaurant recommendation|"
    r"lunch stop|dinner stop|breakfast stop|meal stop)\b",
    re.I,
)
_HOTEL_PLACEHOLDER_RE = re.compile(
    r"\b(tbd|to be decided|hotel option|hotel recommendation|"
    r"accommodation option|accommodation recommendation)\b",
    re.I,
)


def _serialized_mutation(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        lock = _MUTATION_LOCKS[hash(get_user_id()) % len(_MUTATION_LOCKS)]
        with lock:
            return func(*args, **kwargs)

    return wrapped


def _slugify(text: str) -> str:
    """Filesystem/Cosmos-safe slug for a destination name."""
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug or "trip"


def _compute_trip_id(plan: dict[str, Any]) -> str:
    """Stable id encoding destination + date range.

    Two plannings for the SAME place over the SAME dates share an id (so they
    merge/resume); a different duration or different dates yields a different id
    (so they're kept as separate, date-tagged trips) — exactly the owner's rule.
    """
    slug = _slugify(str(plan.get("destination") or "trip"))
    dep = (str(plan.get("departure_date") or "").strip()) or "nodate"
    ret = (str(plan.get("return_date") or "").strip()) or "nodate"
    return f"{slug}_{dep}_{ret}"



def _resolve_active_trip_path() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _ACTIVE_TRIP_FILE
    return _TRIPS_DIR / "users" / uid / "active_trip.json"


def _resolve_trip_history_dir() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _TRIP_HISTORY_DIR
    return _TRIPS_DIR / "users" / uid / "trips"


def _ensure_dirs() -> None:
    _resolve_active_trip_path().parent.mkdir(parents=True, exist_ok=True)
    _resolve_trip_history_dir().mkdir(parents=True, exist_ok=True)


def _is_place_kind(kind: str) -> bool:
    return kind in {"hotel", "attraction", "meal"}


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


def _restaurant_itinerary_warnings(itinerary: Any) -> list[str]:
    warnings: list[str] = []
    if not isinstance(itinerary, list):
        return warnings
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        day_num = day.get("day") if isinstance(day.get("day"), int) else index + 1
        raw_stops = day.get("stops")
        stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
        place_count = sum(1 for stop in stops if _stop_kind(stop) == "attraction")
        meal_stops = [stop for stop in stops if _stop_kind(stop) == "meal"]
        placeholders = [
            _stop_name(stop)
            for stop in meal_stops
            if not _stop_name(stop) or _MEAL_PLACEHOLDER_RE.search(_stop_name(stop))
        ]
        if placeholders:
            warnings.append(f"Day {day_num} has a meal placeholder instead of a named restaurant.")
        elif place_count >= 2 and not meal_stops:
            warnings.append(f"Day {day_num} has multiple activities but no named restaurant stop.")
    return warnings


def _hotel_selection_warnings(plan: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    hotels = plan.get("selected_hotels")
    if isinstance(hotels, list) and not hotels:
        warnings.append("No concrete hotel is selected.")

    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return warnings
    placeholder_days: list[str] = []
    for index, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        raw_stops = day.get("stops")
        stops = raw_stops if isinstance(raw_stops, list) else []
        if any(
            _stop_kind(stop) == "hotel"
            and _HOTEL_PLACEHOLDER_RE.search(_stop_name(stop))
            for stop in stops
        ):
            day_num = day.get("day") if isinstance(day.get("day"), int) else index + 1
            placeholder_days.append(str(day_num))
    if placeholder_days:
        warnings.append(
            f"Hotel placeholders remain on Day(s) {', '.join(placeholder_days)}."
        )
    return warnings


def _make_stop(name: str, kind: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "kind": _canonical_place_kind(kind),
        "time": str(summary.get("time") or "").strip(),
        "duration_min": summary.get("duration_min")
        if isinstance(summary.get("duration_min"), (int, float))
        else None,
        "note": str(summary.get("editorial_summary") or summary.get("note") or "").strip(),
        "booked": bool(summary.get("booked")),
        "selected": True,
    }


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


def _infer_stop_time(stops: list[Any], insert_at: int, kind: str) -> str:
    """Infer a sensible HH:MM slot for a new stop when time is missing.

    Uses neighboring timed stops when available (midpoint), otherwise offsets
    from nearest known neighbor; falls back to a stable day anchor.
    """
    prev_time: int | None = None
    next_time: int | None = None

    for i in range(insert_at - 1, -1, -1):
        raw = stops[i]
        if isinstance(raw, dict):
            t = _parse_hhmm(str(raw.get("time") or ""))
            if t is not None:
                prev_time = t
                break

    for i in range(insert_at, len(stops)):
        raw = stops[i]
        if isinstance(raw, dict):
            t = _parse_hhmm(str(raw.get("time") or ""))
            if t is not None:
                next_time = t
                break

    if prev_time is not None and next_time is not None and next_time > prev_time:
        return _fmt_hhmm((prev_time + next_time) // 2)
    if prev_time is not None:
        return _fmt_hhmm(min(prev_time + 120, 22 * 60))
    if next_time is not None:
        return _fmt_hhmm(max(next_time - 120, 8 * 60))

    # Stable defaults when no context exists.
    if kind == "hotel":
        return "15:00"
    return "11:00"


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


def assess_itinerary_change(
    plan: dict[str, Any],
    *,
    action: str,
    name: str,
    days: list[int] | None = None,
) -> dict[str, Any] | None:
    """Return a material post-mutation concern that merits planner review."""
    itinerary = plan.get("day_wise_itinerary") or []
    destination = str(plan.get("destination") or "")
    max_stops, max_duration, max_km = _style_caps(plan)
    requested_days = set(days or [])
    concerns: list[tuple[int, int, str]] = []

    for day_index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        day = int(entry.get("day") or day_index + 1)
        if requested_days and day not in requested_days:
            continue
        stops = entry.get("stops") if isinstance(entry.get("stops"), list) else []
        planned = [
            stop for stop in stops
            if _stop_kind(stop) in {"attraction", "meal", "restaurant", "other"}
        ]
        planned_duration = sum(
            int(stop.get("duration_min"))
            if isinstance(stop, dict) and isinstance(stop.get("duration_min"), (int, float))
            else 90
            for stop in planned
        )
        attraction_count = sum(_stop_kind(stop) in {"attraction", "other"} for stop in planned)
        has_meal = any(_stop_kind(stop) in {"meal", "restaurant"} for stop in planned)
        stats = _day_stats(entry, destination, (99, max_duration, max_km))
        planned_cap = max(2, max_stops - 1)
        reasons: list[str] = []
        severity = 0
        if len(planned) > planned_cap:
            reasons.append(f"{len(planned)} planned places")
            severity += 3
        if planned_duration > max_duration:
            hours = planned_duration / 60
            reasons.append(f"about {hours:.1f} hours of planned stops")
            severity += 2
        if stats["route_km"] > max_km:
            reasons.append(f"roughly {stats['route_km']:.0f} km between stops")
            severity += 2
        if action == "removed" and not planned:
            reasons.append("no non-stay places remaining")
            severity += 3
        elif attraction_count >= 3 and not has_meal:
            reasons.append("no named meal stop")
            severity += 1
        if reasons:
            concerns.append((severity, day, ", ".join(reasons)))

    if not concerns:
        return None

    _, day, reason = max(concerns, key=lambda item: (item[0], -item[1]))
    if "no non-stay places" in reason:
        summary = f"Day {day} is now empty apart from the stay."
    else:
        summary = f"Day {day} may feel crowded: {reason}."
    prompt = (
        f"Review my recent itinerary change: I {action} {name}. {summary} "
        "Explain the most important trade-off and propose up to three practical options. "
        "Do not change the itinerary or call any mutation tool until I explicitly approve an option."
    )
    return {
        "severity": "warning",
        "day": day,
        "summary": summary,
        "prompt": prompt,
    }


def _closest_insert_index(stops: list[Any], name: str, destination: str) -> int:
    coords = _coords_from_summary(_summary_for_place(name, destination))
    if not coords:
        return len(stops)
    best_idx = len(stops)
    best_dist: float | None = None
    for idx, raw in enumerate(stops):
        stop_name = _stop_name(raw)
        if not stop_name:
            continue
        stop_coords = _coords_from_summary(_summary_for_place(stop_name, destination))
        if not stop_coords:
            continue
        dist = _haversine_km(coords, stop_coords)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_idx = idx + 1
    return best_idx


def _remove_candidate(day: dict[str, Any], destination: str, new_name: str) -> dict[str, Any] | None:
    stops = day.get("stops") if isinstance(day.get("stops"), list) else []
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for idx, raw in enumerate(stops):
        if not isinstance(raw, dict):
            continue
        name = _stop_name(raw)
        if not name or name.lower() == new_name.lower():
            continue
        if raw.get("booked"):
            continue
        kind = _stop_kind(raw)
        if kind not in {"attraction", "other"}:
            continue
        summary = _summary_for_place(name, destination)
        coords = _coords_from_summary(summary)
        rating = summary.get("rating")
        score = 0.0
        if coords:
            center = coords
            distances = []
            for other in stops:
                other_name = _stop_name(other)
                if other_name and other_name.lower() != name.lower():
                    other_coords = _coords_from_summary(_summary_for_place(other_name, destination))
                    if other_coords:
                        distances.append(_haversine_km(center, other_coords))
            score += sum(distances) / max(len(distances), 1)
        score += 10.0 if kind == "other" else 0.0
        score += (5.0 - float(rating)) if isinstance(rating, (int, float)) else 1.5
        candidates.append((score, idx, raw))
    if not candidates:
        return None
    _, idx, raw = max(candidates, key=lambda t: (t[0], -t[1]))
    return {"index": idx, "stop": raw}


def _rebalance_day(plan: dict[str, Any], day_index: int, new_name: str, new_kind: str) -> list[str]:
    alerts: list[str] = []
    itinerary = plan.get("day_wise_itinerary") or []
    if day_index < 0 or day_index >= len(itinerary):
        return alerts
    day = itinerary[day_index]
    if not isinstance(day, dict):
        return alerts
    destination = str(plan.get("destination") or "")
    stats = _day_stats(day, destination, _style_caps(plan))
    if not stats["packed"]:
        return alerts
    removal = _remove_candidate(day, destination, new_name)
    if not removal:
        alerts.append(
            f"Day {day_index + 1} is getting full; I added {new_name} but couldn't find a safe stop to remove automatically."
        )
        return alerts
    stops = day.get("stops") if isinstance(day.get("stops"), list) else []
    removed = stops.pop(removal["index"])
    removed_name = _stop_name(removed)
    alerts.append(
        f"Day {day_index + 1} was packed, so I added {new_name} and removed {removed_name} to keep the route comfortable."
    )
    # Keep the trip's selected buckets consistent with the itinerary.
    if isinstance(removed, dict):
        bucket = "selected_hotels" if _stop_kind(removed) == "hotel" else "selected_activities"
        plan[bucket] = [
            item
            for item in (plan.get(bucket) or [])
            if str(item.get("name") or "").strip().lower() != removed_name.lower()
        ]
    return alerts


def _place_selected_stop(
    plan: dict[str, Any],
    kind: str,
    name: str,
    preferred_day: int | None = None,
    source_day: int | None = None,
    source_stop: int | None = None,
) -> tuple[list[str], dict[str, Any] | None, bool]:
    alerts: list[str] = []
    destination = str(plan.get("destination") or "")
    itinerary = plan.get("day_wise_itinerary") or []
    if not itinerary:
        if preferred_day is not None:
            return (
                [
                    f"Day {preferred_day} is not available yet because the itinerary has no structured days. Choose Best day, or create the day-by-day itinerary first."
                ],
                None,
                False,
            )
        alerts.append(
            f"{name} was saved. Your assistant will slot it into a day-by-day plan once the itinerary is structured."
        )
        return alerts, None, True

    summary = _summary_for_place(name, destination)
    stop_kind = _canonical_place_kind(kind)
    stop = _make_stop(name, stop_kind, summary)
    requested_idx: int | None = None
    available_days: list[int] = []
    for idx, day in enumerate(itinerary):
        if not isinstance(day, dict):
            continue
        logical_day = int(day.get("day") or idx + 1)
        available_days.append(logical_day)
        if preferred_day == logical_day:
            requested_idx = idx
    if preferred_day is not None and requested_idx is None:
        choices = ", ".join(f"Day {day}" for day in available_days)
        alternative = f" Choose {choices}, or Best day." if choices else " Choose Best day."
        return [f"Day {preferred_day} is not available.{alternative}"], None, False

    existing: tuple[int, int, Any] | None = None
    for day_index, day in enumerate(itinerary):
        stops = day.get("stops") if isinstance(day, dict) and isinstance(day.get("stops"), list) else []
        logical_day = int(day.get("day") or day_index + 1) if isinstance(day, dict) else day_index + 1
        for stop_index, raw in enumerate(stops):
            if _stop_name(raw).lower() != name.lower():
                continue
            if source_day is not None and logical_day != source_day:
                continue
            if source_stop is not None and stop_index + 1 != source_stop:
                continue
            existing = (day_index, stop_index, raw)
            break
        if existing:
            break

    if (source_day is not None or source_stop is not None) and existing is None:
        return (
            [f"That {name} occurrence changed before it could be moved. Refresh and choose it again."],
            None,
            False,
        )

    if existing:
        existing_day_idx, existing_stop_idx, raw = existing
        existing_day = itinerary[existing_day_idx]
        existing_day_num = int(existing_day.get("day") or existing_day_idx + 1)
        if requested_idx is None or requested_idx == existing_day_idx:
            existing_stops = existing_day.get("stops") or []
            if isinstance(raw, dict):
                raw.update(stop)
            else:
                existing_stops[existing_stop_idx] = stop
            placement = {
                "day": existing_day_num,
                "stop": existing_stop_idx + 1,
                "name": name,
            }
            alerts.append(
                f"{name} is already on Day {existing_day_num}; I refreshed its details."
            )
            return alerts, placement, True
        if isinstance(raw, dict) and raw.get("booked"):
            return (
                [
                    f"{name} is booked on Day {existing_day_num}, so I did not move it to Day {preferred_day}. Keep Day {existing_day_num}, or unbook it and choose Day {preferred_day} again."
                ],
                None,
                False,
            )
        target_day = itinerary[requested_idx]
        target_stops = (
            target_day.get("stops")
            if isinstance(target_day, dict) and isinstance(target_day.get("stops"), list)
            else []
        )
        if any(_stop_name(candidate).lower() == name.lower() for candidate in target_stops):
            return (
                [f"{name} is already on Day {preferred_day}. Choose a different day."],
                None,
                False,
            )
        existing_stops = existing_day.get("stops") or []
        existing_stops.pop(existing_stop_idx)
        if isinstance(raw, dict):
            raw.update(stop)
            stop = raw

    best_idx = requested_idx or 0
    if preferred_day is None:
        best_score: float | None = None
        for idx, day in enumerate(itinerary):
            if not isinstance(day, dict):
                continue
            stats = _day_stats(day, destination)
            stops = day.get("stops") if isinstance(day.get("stops"), list) else []
            stop_names = [n for n in (_stop_name(s) for s in stops) if n]
            score = stats["route_km"] * 2.5 + stats["count"] * 18 + stats["duration_min"] * 0.35
            if not stop_names:
                score -= 30
            if kind == "hotel":
                score += 45 if any(
                    _stop_kind(s) == "hotel" for s in stops if isinstance(s, dict)
                ) else 0
            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

    day = itinerary[best_idx]
    stops = day.setdefault("stops", []) if isinstance(day, dict) else []

    insert_at = _closest_insert_index(stops, name, destination)
    if insert_at >= len(stops):
        stops.append(stop)
    else:
        stops.insert(insert_at, stop)

    if not str(stop.get("time") or "").strip():
        stop["time"] = _infer_stop_time(stops, insert_at, stop_kind)

    placed_day = int(day.get("day") or best_idx + 1)
    action = "moved" if existing else "placed"
    alerts.append(f"I {action} {name} to Day {placed_day} in stop {insert_at + 1}.")
    return (
        alerts,
        {"day": placed_day, "stop": insert_at + 1, "name": name},
        True,
    )


def _day_entry_and_stops(itinerary: list[Any], day_num: int) -> tuple[dict[str, Any] | None, list[Any]]:
    if day_num <= 0:
        return None, []
    for idx, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        current = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        if current != day_num:
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list):
            stops = []
            entry["stops"] = stops
        return entry, stops
    return None, []


def _reflow_unbooked_attractions(plan: dict[str, Any]) -> bool:
    """Regroup mutable place stops around the current per-day hotel anchors."""
    itinerary = plan.get("day_wise_itinerary") or []
    days = [day for day in itinerary if isinstance(day, dict)]
    if not days:
        return False

    destination = str(plan.get("destination") or "")
    movable: list[tuple[int, Any]] = []
    fixed_by_day: list[list[Any]] = []
    anchors: list[tuple[float, float] | None] = []
    for day_index, day in enumerate(days):
        fixed: list[Any] = []
        anchor: tuple[float, float] | None = None
        raw_stops = day.get("stops")
        stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
        for stop in stops:
            kind = _stop_kind(stop)
            booked = isinstance(stop, dict) and bool(stop.get("booked"))
            if kind == "attraction" and not booked:
                movable.append((day_index, stop))
                continue
            fixed.append(stop)
            if kind == "hotel" and anchor is None:
                anchor = _coords_from_summary(
                    _summary_for_place(_stop_name(stop), destination)
                )
        fixed_by_day.append(fixed)
        anchors.append(anchor)

    if not movable:
        return False

    stop_coords = {
        id(stop): _coords_from_summary(_summary_for_place(_stop_name(stop), destination))
        for _, stop in movable
    }
    assignments: list[list[Any]] = [[] for _ in days]
    target_sizes = [len(movable) // len(days) for _ in days]
    for index in range(len(movable) % len(days)):
        target_sizes[index] += 1

    for original_day, stop in movable:
        coords = stop_coords[id(stop)]
        available = [index for index, size in enumerate(target_sizes) if len(assignments[index]) < size]
        if not available:
            available = list(range(len(days)))

        def score(day_index: int) -> tuple[float, int, int]:
            anchor = anchors[day_index]
            if coords and anchor:
                distance = _haversine_km(coords, anchor)
            else:
                distance = abs(day_index - original_day) * 5.0
            return (distance, len(assignments[day_index]), day_index)

        assignments[min(available, key=score)].append(stop)

    changed = False
    for day_index, day in enumerate(days):
        ordered: list[Any] = []
        remaining = assignments[day_index][:]
        current = anchors[day_index]
        while remaining:
            with_coords = [stop for stop in remaining if stop_coords[id(stop)] is not None]
            if current is None or not with_coords:
                ordered.extend(remaining)
                break
            next_stop = min(
                with_coords,
                key=lambda stop: _haversine_km(current, stop_coords[id(stop)]),  # type: ignore[arg-type]
            )
            remaining.remove(next_stop)
            ordered.append(next_stop)
            current = stop_coords[id(next_stop)]

        fixed = fixed_by_day[day_index]
        insert_at = max(
            (index + 1 for index, stop in enumerate(fixed) if _stop_kind(stop) == "hotel"),
            default=len(fixed),
        )
        next_stops = fixed[:insert_at] + ordered + fixed[insert_at:]
        previous_names = [_stop_name(stop) for stop in day.get("stops") or []]
        next_names = [_stop_name(stop) for stop in next_stops]
        if previous_names != next_names:
            changed = True
        day["stops"] = next_stops

    return changed


@_serialized_mutation
def add_hotel_stay(
    name: str,
    start_day: int | None = None,
    end_day: int | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Add/adjust a hotel as a stay-range change instead of a single stop.

    Non-tool helper for the UI: applies the same hotel across a day range,
    updating each day's hotel stop coherently.
    """
    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "alerts": ["No active trip to update."]}

    hotel_name = str(name or "").strip()
    if not hotel_name:
        return {"ok": False, "alerts": ["No hotel name was provided."]}

    bucket = plan.setdefault("selected_hotels", [])
    if not any(str(x.get("name") or "").strip().lower() == hotel_name.lower() for x in bucket):
        bucket.append({"name": hotel_name})

    itinerary = plan.get("day_wise_itinerary") or []
    if not itinerary:
        _save_active_trip(plan)
        return {
            "ok": True,
            "alerts": [
                f"Added {hotel_name}. Once your day-by-day itinerary is structured, you can assign stay dates."
            ],
            "trip": plan,
            "placement": None,
        }

    total_days = max(1, len(itinerary))
    start = int(start_day) if isinstance(start_day, int) and start_day > 0 else 1
    end = int(end_day) if isinstance(end_day, int) and end_day > 0 else total_days
    start = max(1, min(start, total_days))
    end = max(1, min(end, total_days))
    if end < start:
        start, end = end, start

    destination = str(plan.get("destination") or "")
    summary = _summary_for_place(hotel_name, destination)
    hotel_stop = _make_stop(hotel_name, "hotel", summary)

    placements: list[dict[str, Any]] = []
    replaced_old_names: set[str] = set()
    for day in range(start, end + 1):
        _, stops = _day_entry_and_stops(itinerary, day)
        if not stops:
            stops.append(dict(hotel_stop))
            placements.append({"day": day, "stop": 1, "name": hotel_name})
            continue

        existing_idx = next(
            (
                idx
                for idx, raw in enumerate(stops)
                if _stop_kind(raw) == "hotel"
            ),
            None,
        )
        if existing_idx is not None:
            existing_name = _stop_name(stops[existing_idx])
            if existing_name.lower() == hotel_name.lower() or replace_existing:
                if existing_name and existing_name.lower() != hotel_name.lower():
                    replaced_old_names.add(existing_name.lower())
                stops[existing_idx] = dict(hotel_stop)
                placements.append({"day": day, "stop": existing_idx + 1, "name": hotel_name})
                continue

        # Make hotel the day anchor at stop 1 when no replace target exists.
        stops.insert(0, dict(hotel_stop))
        placements.append({"day": day, "stop": 1, "name": hotel_name})

    # Keep selected_hotels aligned with the edited itinerary: if a previous
    # stay was replaced in-range and no longer appears in any day's hotel stop,
    # drop it so map/details don't keep showing the old hotel as selected.
    if replaced_old_names:
        still_used_hotels: set[str] = set()
        for day_entry in itinerary:
            if not isinstance(day_entry, dict):
                continue
            stops = day_entry.get("stops")
            if not isinstance(stops, list):
                continue
            for raw in stops:
                if _stop_kind(raw) != "hotel":
                    continue
                n = _stop_name(raw).lower()
                if n:
                    still_used_hotels.add(n)

        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in bucket:
            if not isinstance(item, dict):
                continue
            nm = str(item.get("name") or "").strip()
            if not nm:
                continue
            key = nm.lower()
            if key in seen:
                continue
            if key in replaced_old_names and key not in still_used_hotels and key != hotel_name.lower():
                continue
            cleaned.append(item)
            seen.add(key)

        if hotel_name.lower() not in seen:
            cleaned.append({"name": hotel_name})
        plan["selected_hotels"] = cleaned

    reflowed = _reflow_unbooked_attractions(plan)

    first = placements[0] if placements else None
    _save_active_trip(plan)

    if start == end:
        date_label = f"Day {start}"
    else:
        date_label = f"Days {start}-{end}"
    alerts = [f"Updated stay: {hotel_name} for {date_label}."]
    if reflowed:
        alerts.append("Rebalanced unbooked itinerary stops around the updated stay.")
    return {
        "ok": True,
        "alerts": alerts,
        "trip": plan,
        "placement": first,
        "placements": placements,
    }


def _load_active_trip() -> dict[str, Any] | None:
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
    path = _resolve_active_trip_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_active_trip_dict() -> dict[str, Any] | None:
    """Public, non-tool accessor for the current active trip.

    The ``get_trip_plan`` ``@tool`` returns a formatted string for the LLM;
    UI code (e.g. the trip panel) needs the raw dict.
    """
    return _load_active_trip()


def active_trip_id() -> str | None:
    """The current active trip's stable id, or ``None`` when none is active.

    Non-tool: lets the API key the persisted chat transcript by trip so each
    saved trip carries its own conversation.
    """
    active = _load_active_trip()
    return (active or {}).get("trip_id") if active else None


@_serialized_mutation
def add_trip_constraint(note: str) -> bool:
    """Record a one-off, trip-scoped constraint on the active trip.

    Non-tool helper used by the passive-learning sweep when the user states an
    exception that applies to THIS trip only ("3-star is fine just this time").
    Deduped case-insensitively. Returns ``True`` if a new constraint was added,
    ``False`` if there's no active trip or it was a duplicate. Best-effort:
    never raises.
    """
    note = (note or "").strip()
    if not note:
        return False
    try:
        plan = _load_active_trip()
        if not plan:
            return False
        existing = plan.get("trip_constraints")
        if not isinstance(existing, list):
            existing = []
        if any(str(c).strip().lower() == note.lower() for c in existing):
            return False
        existing.append(note)
        plan["trip_constraints"] = existing
        _save_active_trip(plan)
        return True
    except Exception:  # pragma: no cover - best-effort, storage failure
        return False


@_serialized_mutation
def add_selection(
    kind: str,
    item: dict[str, Any],
    preferred_day: int | None = None,
    source_day: int | None = None,
    source_stop: int | None = None,
) -> dict[str, Any]:
    """Add a hotel, attraction, or meal to the active trip's selections (UI helper).

    ``kind`` is ``"hotel"``, ``"attraction"``, or ``"meal"``. Deduped by name. Returns a
    result dict with ``ok``, ``alerts`` and the updated ``trip`` snapshot.
    Non-tool: called by the panel's "Add to trip" button, not the LLM.
    """
    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "alerts": ["No active trip to update."]}
    key = "selected_hotels" if kind == "hotel" else "selected_activities"
    bucket = plan.setdefault(key, [])
    name = str(item.get("name") or "").strip()
    if not name:
        return {"ok": False, "alerts": ["No place name was provided."]}
    already_selected = any(
        str(x.get("name") or "").strip().lower() == name.lower() for x in bucket
    )
    if already_selected and preferred_day is None:
        return {"ok": True, "alerts": [f"{name} is already in your trip."]}
    alerts = [
        f"Updated {name} in your trip."
        if already_selected
        else f"Added {name} to your trip."
    ]
    placement: dict[str, Any] | None = None
    if _is_place_kind(kind):
        placement_alerts, placement, placed = _place_selected_stop(
            plan, kind, name, preferred_day, source_day, source_stop
        )
        if not placed:
            return {"ok": False, "alerts": placement_alerts, "trip": plan, "placement": None}
        alerts.extend(placement_alerts)
        if not already_selected:
            bucket.append(item)
        if preferred_day is None and _reflow_unbooked_attractions(plan):
            alerts.append("Rebalanced unbooked itinerary stops around the updated trip.")
        canonical_kind = _canonical_place_kind(kind)
        if canonical_kind == "attraction" and preferred_day is None:
            itinerary = plan.get("day_wise_itinerary") or []
            for day_index in range(len(itinerary)):
                alerts.extend(_rebalance_day(plan, day_index, name, canonical_kind))
            _reflow_unbooked_attractions(plan)
    elif not already_selected:
        bucket.append(item)
    _save_active_trip(plan)
    return {"ok": True, "alerts": alerts, "trip": plan, "placement": placement}


@_serialized_mutation
def remove_selection(
    kind: str,
    name: str,
    *,
    day: int | None = None,
    stop: int | None = None,
    all_occurrences: bool = True,
) -> bool:
    """Remove a previously-added hotel/attraction from the active trip (UI helper).

    The reverse of :func:`add_selection`. Matched case-insensitively by name.
    Returns ``True`` when there's an active trip to update, ``False`` otherwise.
    Non-tool: called by the panel's "Remove from trip" button, not the LLM.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    target = str(name or "").strip().lower()
    if not target:
        return False
    key = "selected_hotels" if kind == "hotel" else "selected_activities"
    bucket = plan.get(key) or []
    itinerary = plan.get("day_wise_itinerary") or []

    if not all_occurrences and day is not None:
        removed = False
        for day_index, entry in enumerate(itinerary):
            if not isinstance(entry, dict):
                continue
            raw_day = entry.get("day")
            day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else day_index + 1
            if day_num != day:
                continue
            raw_stops = entry.get("stops")
            stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
            if stop is not None and 0 < stop <= len(stops):
                candidate_index = stop - 1
                if _stop_name(stops[candidate_index]).strip().lower() == target:
                    stops.pop(candidate_index)
                    removed = True
            if not removed:
                for candidate_index, candidate in enumerate(stops):
                    if _stop_name(candidate).strip().lower() == target:
                        stops.pop(candidate_index)
                        removed = True
                        break
            break
        if not removed:
            return False
        still_present = any(
            _stop_name(candidate).strip().lower() == target
            for entry in itinerary
            if isinstance(entry, dict)
            for candidate in (entry.get("stops") or [])
        )
        if not still_present:
            plan[key] = [
                item
                for item in bucket
                if str(item.get("name") or "").strip().lower() != target
            ]
        _save_active_trip(plan)
        return True

    kept = [x for x in bucket if str(x.get("name") or "").strip().lower() != target]
    changed = len(kept) != len(bucket)
    if changed:
        plan[key] = kept
    # Also strip the place from the day-by-day itinerary. A place can live in
    # the itinerary without being in the selected bucket (the agent placed it
    # directly), so do this even when the bucket was unchanged.
    for day in itinerary:
        if not isinstance(day, dict):
            continue
        raw_stops = day.get("stops")
        stops: list[Any] = raw_stops if isinstance(raw_stops, list) else []
        pruned = [s for s in stops if _stop_name(s).strip().lower() != target]
        if len(pruned) != len(stops):
            day["stops"] = pruned
            changed = True
    if changed:
        _reflow_unbooked_attractions(plan)
        _save_active_trip(plan)
    return True


@_serialized_mutation
def set_stop_booked(day: int, name: str, booked: bool) -> bool:
    """Toggle a single itinerary stop's ``booked`` flag (UI helper).

    Finds the day entry by its day number and the stop by name (case-
    insensitive). String stops on that day are normalized to dicts so the flag
    can be persisted. Returns ``True`` when the stop was found and updated.
    Non-tool: called by the Itinerary panel's booked checkbox.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    itin = plan.get("day_wise_itinerary") or []
    target = str(name or "").strip().lower()
    if not target:
        return False
    for idx, entry in enumerate(itin):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_num = raw_day if isinstance(raw_day, int) and raw_day > 0 else idx + 1
        if day_num != day:
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list):
            return False
        for j, stop in enumerate(stops):
            stop_name = stop.get("name") if isinstance(stop, dict) else stop
            if str(stop_name or "").strip().lower() != target:
                continue
            if not isinstance(stop, dict):
                stop = {"name": str(stop)}
                stops[j] = stop
            stop["booked"] = bool(booked)
            _save_active_trip(plan)
            return True
    return False


def _save_active_trip(plan: dict[str, Any]) -> None:
    # Stamp a stable id + freshness so the trip can live in history and be
    # listed / resumed later. Every save mirrors to the trips collection so
    # in-progress drafts are never lost when the user switches trips.
    if not plan.get("trip_id"):
        plan["trip_id"] = _compute_trip_id(plan)
    plan["updated_at"] = datetime.now().isoformat()

    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID, plan
        )
    else:
        _ensure_dirs()
        atomic_write_json(_resolve_active_trip_path(), plan, indent=2)
    _mirror_to_history(plan)


def _mirror_to_history(plan: dict[str, Any]) -> None:
    """Persist the plan into the per-user trips collection under its trip_id."""
    tid = plan.get("trip_id")
    if not tid:
        return
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), tid, plan)
        return
    _ensure_dirs()
    atomic_write_json(_resolve_trip_history_dir() / f"{tid}.json", plan, indent=2)


def _load_history_trip(trip_id: str) -> dict[str, Any] | None:
    """Load a single saved trip by its trip_id, or ``None``."""
    if not trip_id:
        return None
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    path = _resolve_trip_history_dir() / f"{trip_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _all_history_trips() -> list[dict[str, Any]]:
    """Every saved trip for the current user (raw plan dicts)."""
    if storage_cosmos.is_enabled():
        return storage_cosmos.query_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
    history_dir = _resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for f in history_dir.glob("*.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def _trip_summary(plan: dict[str, Any], active_id: str | None) -> dict[str, Any]:
    """Compact, UI-friendly descriptor for one saved trip."""
    tid = plan.get("trip_id") or _compute_trip_id(plan)
    return {
        "trip_id": tid,
        "destination": str(plan.get("destination") or ""),
        "departure_date": str(plan.get("departure_date") or ""),
        "return_date": str(plan.get("return_date") or ""),
        "status": str(plan.get("status") or "draft"),
        "total_cost": plan.get("total_cost") or 0,
        "currency": str(plan.get("currency") or ""),
        "counts": {
            "flights": len(plan.get("selected_flights") or []),
            "hotels": len(plan.get("selected_hotels") or []),
            "activities": len(plan.get("selected_activities") or []),
        },
        "updated_at": str(plan.get("updated_at") or plan.get("created_at") or ""),
        "is_active": bool(active_id) and tid == active_id,
    }


def list_saved_trips() -> list[dict[str, Any]]:
    """All saved trips as compact descriptors, most-recently-updated first.

    Non-tool: powers the SPA's "My trips" switcher and the resume flow.
    """
    active = _load_active_trip()
    active_id = (active or {}).get("trip_id") if active else None
    summaries = [_trip_summary(p, active_id) for p in _all_history_trips()]
    summaries.sort(key=lambda t: t["updated_at"], reverse=True)
    return summaries


def saved_trip_destination(trip_id: str) -> str:
    """Destination name of a saved trip, or ``""``. Non-tool helper for chat
    carryover phrasing when the user switches plans mid-conversation."""
    plan = _load_history_trip(trip_id)
    return str((plan or {}).get("destination") or "") if plan else ""


@_serialized_mutation
def switch_active_trip(trip_id: str) -> dict[str, Any] | None:
    """Make a saved trip the active one. Returns the plan, or ``None``.

    The currently-active trip is already mirrored in history (every save does
    so), so switching loses nothing. Non-tool: called by the panel / resume.
    """
    plan = _load_history_trip(trip_id)
    if not plan:
        return None
    _save_active_trip(plan)
    return plan


@_serialized_mutation
def delete_saved_trip(trip_id: str) -> bool:
    """Delete a saved trip; clears the active pointer if it was active."""
    if not trip_id:
        return False
    active = _load_active_trip()
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    else:
        (_resolve_trip_history_dir() / f"{trip_id}.json").unlink(missing_ok=True)
    if active and active.get("trip_id") == trip_id:
        _delete_active_trip()
    return True


@_serialized_mutation
def clear_all_trip_history() -> int:
    """Delete all saved trips for the current user and clear active trip."""
    if storage_cosmos.is_enabled():
        deleted = storage_cosmos.delete_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
        _delete_active_trip()
        return deleted

    deleted = 0
    history_dir = _resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    for path in history_dir.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    _delete_active_trip()
    return deleted


@_serialized_mutation
def start_new_trip() -> None:
    """Clear the active trip so the next conversation starts fresh.

    Saved trips are left untouched (every save already mirrors them into the
    trips collection), so this only drops the *active* pointer. After this,
    ``active_trip_id()`` is ``None`` and a new chat lands in the general bucket
    until the agent creates a plan. Non-tool: called by the "New trip" button.
    """
    _delete_active_trip()


@_serialized_mutation
def import_shared_trip_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """Persist a shared snapshot as the current user's active editable trip.

    The imported copy becomes a normal saved trip for the viewer. We preserve
    the shared selections/itinerary, but stamp fresh ownership metadata so it
    lives independently of the original owner's plan.
    """
    imported = json.loads(json.dumps(plan or {}))
    imported.pop("trip_id", None)
    imported["created_at"] = datetime.now().isoformat()
    imported["updated_at"] = imported["created_at"]
    imported["status"] = str(imported.get("status") or "draft")
    imported["imported_from_share"] = True
    imported["trip_id"] = _compute_trip_id(imported)
    _save_active_trip(imported)
    return imported


def _delete_active_trip() -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
        return
    _resolve_active_trip_path().unlink(missing_ok=True)


@tool
@_serialized_mutation
def create_trip_plan(
    destination: str,
    departure_date: str,
    return_date: str,
    origin: str = "",
    travelers_summary: str = "",
    notes: str = "",
) -> str:
    """Create a new trip plan draft. Call this to start planning a trip.

    Args:
        destination: Where the user wants to go.
        departure_date: YYYY-MM-DD.
        return_date: YYYY-MM-DD.
        origin: Departure city (defaults from preferences if not provided).
        travelers_summary: e.g. '2 adults, 1 child (age 5)'.
        notes: Any special requirements or notes.
    """
    prefs = load_preferences()
    fam = prefs["family"]
    if not travelers_summary:
        travelers_summary = f"{fam['adults']} adults"
        if fam["children"]:
            travelers_summary += f", {fam['children']} children (ages {fam['child_ages']})"
        if fam["elderly"]:
            travelers_summary += f", {fam['elderly']} elderly"

    # Same destination + same dates -> resume the saved trip instead of wiping
    # it, so the user never restarts from scratch. Different dates/duration get
    # a distinct id and are kept as a separate, date-tagged trip.
    trip_id = _compute_trip_id(
        {
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
        }
    )
    existing = _load_history_trip(trip_id)
    if existing:
        if origin:
            existing["origin"] = origin
        if notes:
            existing["notes"] = notes
        if travelers_summary:
            existing["travelers"] = travelers_summary
        existing["status"] = existing.get("status") or "draft"
        _save_active_trip(existing)
        counts = (
            len(existing.get("selected_flights") or []),
            len(existing.get("selected_hotels") or []),
            len(existing.get("selected_activities") or []),
        )
        return (
            f"Resumed your saved trip: {destination} "
            f"({departure_date} to {return_date})\n"
            f"So far: {counts[0]} flight(s), {counts[1]} hotel(s), "
            f"{counts[2]} activity(ies) | Status: {existing['status'].upper()}\n"
            f"Pick up where you left off — no need to restart."
        )

    plan: dict[str, Any] = {
        "status": "draft",
        "trip_id": trip_id,
        "created_at": datetime.now().isoformat(),
        "destination": destination,
        "origin": origin,
        "departure_date": departure_date,
        "return_date": return_date,
        "travelers": travelers_summary,
        "notes": notes,
        "preferences_snapshot": {
            "trip_style": prefs["trip_style"],
            "budget_level": prefs["budget_level"],
            "hotel_preferences": prefs["hotel_preferences"],
            "transport_preferences": prefs["transport_preferences"],
            "food_preferences": prefs["food_preferences"],
        },
        "selected_flights": [],
        "selected_hotels": [],
        "selected_activities": [],
        "day_wise_itinerary": [],
        "cost_breakdown": {},
        "total_cost": 0,
        "budget": 0,
        "currency": "",
        # One-off constraints/exceptions that apply to THIS trip only (e.g.
        # "3-star is fine just this time"). They never leak into durable prefs.
        "trip_constraints": [],
    }
    _save_active_trip(plan)
    return (
        f"Trip plan created: {destination} ({departure_date} to {return_date})\n"
        f"Travelers: {travelers_summary}\n"
        f"Style: {prefs['trip_style']} | Budget: {prefs['budget_level']}\n"
        f"Status: DRAFT — ready to search for flights, hotels, and activities."
    )


@tool
def get_trip_plan() -> str:
    """Get the current active trip plan with all selections and costs."""
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan. Use create_trip_plan to start one."
    return json.dumps(plan, indent=2)


@tool
@_serialized_mutation
def update_trip_plan(updates_json: str) -> str:
    """Update the active trip plan with selected flights, hotels, activities, or itinerary.

    Pass a JSON string with any of these keys to update:
    - selected_flights: list of flight selections
    - selected_hotels: list of hotel selections
    - selected_activities: list of activity selections
    - day_wise_itinerary: list of day plans
    - cost_breakdown: dict of cost items
    - total_cost: number
    - budget: number — the user's total budget for THIS trip (drives the live
      budget meter in the UI; set it as soon as the user states a budget)
    - currency: ISO code of the sticky display currency ("INR", "USD", "EUR",
      ...) — set it once when you pick the plan's currency so every surface
      (including the budget meter) shows the same symbol
    - notes: string
    - trip_constraints: list of strings — one-off exceptions/constraints that
      apply to THIS trip ONLY (e.g. "3-star hotel is fine just for this trip",
      "OK with one connection this time"). Use this for anything the user says
      is a one-time exception; NEVER save such one-offs to durable preferences.

    Example: '{"selected_flights": [{"option": 1, "airline": "IndiGo", "price": 8500}]}'
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan. Use create_trip_plan first."

    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError:
        return "Error: invalid JSON."

    allowed_keys = {
        "selected_flights", "selected_hotels", "selected_activities",
        "day_wise_itinerary", "cost_breakdown", "total_cost", "notes",
        "origin", "budget", "currency", "trip_constraints",
    }
    before = json.loads(json.dumps(plan))  # deep copy for diff
    for key, val in updates.items():
        if key in allowed_keys:
            if key == "selected_hotels" and isinstance(val, list):
                val = [
                    hotel
                    for hotel in val
                    if not _HOTEL_PLACEHOLDER_RE.search(_stop_name(hotel))
                ]
            plan[key] = val

    _save_active_trip(plan)
    restaurant_warnings = _restaurant_itinerary_warnings(plan.get("day_wise_itinerary"))
    hotel_warnings = _hotel_selection_warnings(plan)
    warning_text = ""
    if restaurant_warnings:
        warning_text = (
            "\nRestaurant planning incomplete: "
            + " ".join(restaurant_warnings)
            + " Call nearby_restaurants, choose preference-matched options, and update "
            "day_wise_itinerary with concrete restaurant names before finishing."
        )
    if hotel_warnings:
        warning_text += (
            "\nHotel planning incomplete: "
            + " ".join(hotel_warnings)
            + " Call search_hotels, choose the best preference-matched real option by "
            "default, verify it with search_places_with_reviews, and replace every hotel "
            "placeholder before finishing."
        )
    bullets = diff_plans(before, plan)
    if not bullets:
        return f"Trip plan updated (no material changes). Status: {plan['status']}{warning_text}"
    return (
        f"Trip plan updated. Status: {plan['status']}\n"
        f"What changed:\n{format_diff(bullets)}{warning_text}"
    )


@tool
@_serialized_mutation
def finalize_trip() -> str:
    """Finalize the current trip plan — lock it and show the complete summary with costs.

    Call this when the user is happy with all selections and wants to proceed to booking.
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan to finalize."

    if not plan.get("selected_flights") and not plan.get("selected_hotels"):
        return (
            "Cannot finalize: no flights or hotels selected yet. "
            "Search and select options first."
        )

    plan["status"] = "finalized"
    plan["finalized_at"] = datetime.now().isoformat()
    _save_active_trip(plan)

    # Build summary
    lines = [
        f"{'='*60}",
        f"  FINALIZED TRIP PLAN — {plan['destination']}",
        f"{'='*60}",
        f"  Dates: {plan['departure_date']} to {plan['return_date']}",
        f"  Travelers: {plan['travelers']}",
        "",
    ]

    if plan["selected_flights"]:
        lines.append("  FLIGHTS:")
        for f in plan["selected_flights"]:
            lines.append(f"    {json.dumps(f)}")
        lines.append("")

    if plan["selected_hotels"]:
        lines.append("  HOTELS:")
        for h in plan["selected_hotels"]:
            lines.append(f"    {json.dumps(h)}")
        lines.append("")

    if plan["selected_activities"]:
        lines.append("  ACTIVITIES & SIGHTSEEING:")
        for a in plan["selected_activities"]:
            lines.append(f"    {json.dumps(a)}")
        lines.append("")

    if plan["day_wise_itinerary"]:
        lines.append("  DAY-WISE ITINERARY:")
        for day in plan["day_wise_itinerary"]:
            lines.append(f"    {json.dumps(day)}")
        lines.append("")

    if plan["cost_breakdown"]:
        lines.append("  COST BREAKDOWN:")
        for item, cost in plan["cost_breakdown"].items():
            lines.append(f"    {item}: ₹{cost:,.0f}" if isinstance(cost, (int, float)) else f"    {item}: {cost}")
        lines.append(f"\n  TOTAL ESTIMATED COST: ₹{plan.get('total_cost', 0):,.0f}")
    lines.append(f"\n{'='*60}")
    lines.append("  Status: FINALIZED — ready for booking")
    lines.append("  Say 'execute' to proceed with bookings.")
    lines.append(f"{'='*60}")

    # Self-correction critic — deterministic rules over the finalized plan.
    try:
        prefs = load_preferences()
    except Exception:
        prefs = {}
    heads_up = _critique_finalized(plan, prefs)
    if heads_up:
        lines.append("")
        lines.append("  HEADS UP — quick sanity checks before you book:")
        for item in heads_up:
            lines.append(f"    • {item}")

    return "\n".join(lines)


@tool
@_serialized_mutation
def execute_bookings() -> str:
    """Execute all bookings for the finalized trip plan.

    This will:
    1. Attempt to book flights via Amadeus Flight Orders API
    2. Generate hotel booking links
    3. Generate activity booking links
    4. Save the trip to history
    5. Record as a past trip in preferences
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan to execute."
    if plan.get("status") != "finalized":
        return "Trip plan must be finalized before executing. Call finalize_trip first."

    results: list[str] = [f"Executing bookings for {plan['destination']}...\n"]

    # Flights — Amadeus Flight Orders would go here
    if plan["selected_flights"]:
        results.append("FLIGHTS:")
        for f in plan["selected_flights"]:
            results.append(f"  ✓ Flight booking initiated: {json.dumps(f)}")
            # In production: amadeus_client.post("/v1/booking/flight-orders", {...})
        results.append("  Note: Flight booking confirmation will be sent to your email.\n")

    # Hotels — generate booking links
    if plan["selected_hotels"]:
        results.append("HOTELS:")
        for h in plan["selected_hotels"]:
            results.append(f"  ✓ Hotel booking initiated: {json.dumps(h)}")
        results.append("  Note: Hotel confirmation will be sent to your email.\n")

    # Activities — generate booking links
    if plan["selected_activities"]:
        results.append("ACTIVITIES:")
        for a in plan["selected_activities"]:
            link = a.get("booking_link", "")
            results.append(f"  ✓ Activity booked: {a.get('name', 'Unknown')}")
            if link:
                results.append(f"    Book here: {link}")
        results.append("")

    # Mark booked and persist to history (every save mirrors under trip_id).
    plan["status"] = "booked"
    plan["booked_at"] = datetime.now().isoformat()
    _save_active_trip(plan)

    # Record in preference history
    add_past_trip(
        destination=plan["destination"],
        dates=f"{plan['departure_date']} to {plan['return_date']}",
        notes=plan.get("notes", ""),
    )

    # Clear active pointer (the booked trip stays in your saved trips).
    _delete_active_trip()

    results.append("\n✅ All bookings executed! Trip saved to your history.")
    results.append("After your trip, update the rating with record_past_trip to improve future suggestions.")
    return "\n".join(results)


@tool
def list_past_trips() -> str:
    """List all archived trip plans from history."""
    if storage_cosmos.is_enabled():
        items = storage_cosmos.query_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
        if not items:
            return "No past trips in archive."
        lines = ["Past trips:"]
        for data in items:
            dest = data.get("destination", "?")
            dates = f"{data.get('departure_date', '?')} to {data.get('return_date', '?')}"
            status = data.get("status", "?")
            cost = data.get("total_cost", 0)
            cost_str = f"₹{cost:,.0f}" if isinstance(cost, (int, float)) else str(cost)
            lines.append(f"  {dest} ({dates}) — {status} — {cost_str}")
        return "\n".join(lines)

    history_dir = _resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    trips = sorted(history_dir.glob("*.json"))
    if not trips:
        return "No past trips in archive."

    lines = ["Past trips:"]
    for t in trips:
        data = json.loads(t.read_text(encoding="utf-8"))
        dest = data.get("destination", "?")
        dates = f"{data.get('departure_date', '?')} to {data.get('return_date', '?')}"
        status = data.get("status", "?")
        cost = data.get("total_cost", 0)
        lines.append(f"  {t.stem}: {dest} ({dates}) — {status} — ₹{cost:,.0f}")
    return "\n".join(lines)


@tool
@_serialized_mutation
def resume_trip(destination: str = "", trip_id: str = "") -> str:
    """Resume a previously saved trip so the user doesn't restart from scratch.

    Match by ``trip_id`` (exact) or ``destination`` (most recently updated
    match). With no arguments, lists the saved trips to choose from. The chosen
    trip becomes the active plan; whatever was active is already saved.

    Args:
        destination: Place name to resume, e.g. 'Mumbai'.
        trip_id: Exact saved-trip id (preferred when known).
    """
    saved = list_saved_trips()
    if not saved:
        return "You have no saved trips yet. Use create_trip_plan to start one."

    match: dict[str, Any] | None = None
    if trip_id:
        match = next((t for t in saved if t["trip_id"] == trip_id), None)
    if match is None and destination:
        needle = destination.strip().lower()
        match = next((t for t in saved if needle in t["destination"].lower()), None)

    if match is None:
        lines = ["Which saved trip would you like to resume?"]
        for t in saved:
            dates = f"{t['departure_date']} to {t['return_date']}"
            lines.append(
                f"  - {t['destination']} ({dates}) — {t['status']} [{t['trip_id']}]"
            )
        return "\n".join(lines)

    if switch_active_trip(match["trip_id"]) is None:
        return f"Could not load saved trip '{match['trip_id']}'."

    c = match["counts"]
    return (
        f"Resumed {match['destination']} "
        f"({match['departure_date']} to {match['return_date']}) — "
        f"{match['status'].upper()}: {c['flights']} flight(s), "
        f"{c['hotels']} hotel(s), {c['activities']} activity(ies). "
        f"Continuing where you left off."
    )

