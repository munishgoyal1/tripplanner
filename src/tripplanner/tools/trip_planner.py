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
from copy import deepcopy
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any

from langchain_core.tools import tool

from tripplanner import debug_store, place_facts, storage_cosmos
from tripplanner.decisions.provenance import make_check, record_check
from tripplanner.decisions.rules import money
from tripplanner.decisions.store import upsert_decision
from tripplanner.json_store import atomic_write_json
from tripplanner.tools.finalize_critic import critique as _critique_finalized
from tripplanner.tools.trip_common import (  # noqa: F401
    _HOTEL_PLACEHOLDER_RE,
    _MAX_DAY_DISTANCE_KM,
    _MAX_DAY_DURATION_MIN,
    _MAX_DAY_STOPS,
    _MEAL_PLACEHOLDER_RE,
    _canonical_place_kind,
    _coords_from_summary,
    _day_stats,
    _fmt_hhmm,
    _haversine_km,
    _is_place_kind,
    _parse_hhmm,
    _stop_kind,
    _stop_name,
    _style_caps,
    _summary_for_place,
    unnamed_lodging,
)
from tripplanner.tools.trip_diff import diff_plans, format_diff
from tripplanner.tools.trip_effort import coherence_notes, pacing_statement
from tripplanner.tools.trip_guard import (
    Envelope,
    _duration_of,
    choose_placement,
    diff_stops,
    envelope,
    receipt,
    unexpected_changes,
    validate_plan,
)
from tripplanner.tools.trip_validation import (  # noqa: F401
    _dietary_preferences,
    _empty_itinerary_day_warnings,
    _hotel_destination_errors,
    _hotel_selection_warnings,
    _itinerary_hotel_locations,
    _itinerary_time_errors,
    _restaurant_itinerary_warnings,
    _round_trip_transport_warnings,
    assess_itinerary_change,
    core_planning_completion_gaps,
    finalization_gaps,
    has_structured_itinerary,
    persistence_sanity_errors,
    planning_completion_gaps,
)
from tripplanner.tools.user_preferences import add_past_trip, load_preferences
from tripplanner.user_context import get_user_id
from tripplanner.web import places_cache  # noqa: F401  (test monkeypatch target)

_TRIPS_DIR = Path.home() / ".tripplanner"
_ACTIVE_TRIP_FILE = _TRIPS_DIR / "active_trip.json"
_TRIP_HISTORY_DIR = _TRIPS_DIR / "trips"

_COSMOS_USERS_CONTAINER = "users"
_COSMOS_TRIPS_CONTAINER = "trips"
_ACTIVE_TRIP_DOC_ID = "active_trip"
_MUTATION_LOCKS = tuple(RLock() for _ in range(64))


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


def _sync_replaced_hotel_anchors(
    plan: dict[str, Any], previous_hotels: Any, selected_hotels: Any
) -> bool:
    if not isinstance(previous_hotels, list) or not isinstance(selected_hotels, list):
        return False

    def by_name(hotels: list[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for hotel in hotels:
            if not isinstance(hotel, dict):
                continue
            name = _stop_name(hotel) or str(hotel.get("hotel_name") or "").strip()
            if name:
                result[name.lower()] = hotel
        return result

    previous = by_name(previous_hotels)
    selected = by_name(selected_hotels)
    removed = previous.keys() - selected.keys()
    added = selected.keys() - previous.keys()
    replacements: dict[str, dict[str, Any]] = {}
    if len(removed) == 1 and len(added) == 1:
        replacements[next(iter(removed))] = selected[next(iter(added))]
    selected_values = list(selected.values())
    placeholder_replacement = selected_values[0] if len(selected_values) == 1 else None
    lodging_locations = _itinerary_hotel_locations(plan)
    destination = str(plan.get("destination") or "").strip().lower()
    if destination:
        lodging_locations = lodging_locations | {destination} | {
            part.strip()
            for part in re.split(r"[,&/()]| and ", destination)
            if part.strip()
        }

    def explicit_locations(value: dict[str, Any]) -> set[str]:
        return {
            str(value.get(key) or "").strip().lower()
            for key in ("destination", "city", "location")
            if str(value.get(key) or "").strip()
        }

    def specific_locations(value: dict[str, Any]) -> set[str]:
        specific = {
            str(value.get(key) or "").strip().lower()
            for key in ("city", "location")
            if str(value.get(key) or "").strip()
        }
        return specific or explicit_locations(value)

    changed = False
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict) or not isinstance(day.get("stops"), list):
            continue
        for index, stop in enumerate(day["stops"]):
            if _stop_kind(stop) != "hotel":
                continue
            stop_name = _stop_name(stop)
            replacement = replacements.get(stop_name.lower())
            is_placeholder = _HOTEL_PLACEHOLDER_RE.search(stop_name) or unnamed_lodging(
                stop_name, lodging_locations
            )
            if replacement is None and is_placeholder:
                anchor_text = stop_name.lower()
                anchor_locations = specific_locations(day) | {
                    location
                    for location in lodging_locations
                    if re.search(rf"\b{re.escape(location)}\b", anchor_text)
                }
                location_matches = [
                    hotel
                    for hotel in selected_values
                    if any(
                        anchor in hotel_location or hotel_location in anchor
                        for anchor in anchor_locations
                        for hotel_location in specific_locations(hotel)
                    )
                ]
                if len(location_matches) == 1:
                    replacement = location_matches[0]
                elif placeholder_replacement is not None:
                    replacement_locations = explicit_locations(placeholder_replacement)
                    if (
                        not anchor_locations
                        or not replacement_locations
                        or anchor_locations & replacement_locations
                    ):
                        replacement = placeholder_replacement
            if replacement is None:
                continue
            replacement_name = _stop_name(replacement) or str(
                replacement.get("hotel_name") or ""
            ).strip()
            next_stop = dict(stop) if isinstance(stop, dict) else {}
            next_stop.update(replacement)
            next_stop["name"] = replacement_name
            next_stop["kind"] = "hotel"
            day["stops"][index] = next_stop
            changed = True
    return changed


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


def _retime_stops_in_order(stops: list[Any]) -> None:
    previous_end: int | None = None
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        current = _parse_hhmm(str(stop.get("time") or ""))
        if current is not None and _is_leg(stop):
            # A flight leaves when it leaves. The rest of the day bends around
            # a journey; the journey does not bend around the rest of the day.
            previous_end = current + (
                max(15, int(stop.get("duration_min")))
                if isinstance(stop.get("duration_min"), (int, float))
                else 90
            )
            continue
        if current is None:
            current = previous_end + 30 if previous_end is not None else 9 * 60
        elif previous_end is not None:
            current = max(current, previous_end + 30)
        stop["time"] = _fmt_hhmm(current)
        duration = stop.get("duration_min")
        previous_end = current + (
            max(15, int(duration)) if isinstance(duration, (int, float)) else 90
        )

    for leg_index, leg in enumerate(stops):
        if not isinstance(leg, dict) or not _is_leg(leg):
            continue
        _fit_stops_before_leg(stops, leg_index)


def _fit_stops_before_leg(stops: list[Any], leg_index: int) -> None:
    leg = stops[leg_index]
    next_start = (
        _parse_hhmm(str(leg.get("time") or "")) if isinstance(leg, dict) else None
    )
    if next_start is None:
        return
    for index in range(leg_index - 1, -1, -1):
        stop = stops[index]
        if not isinstance(stop, dict) or _is_leg(stop):
            break
        current = _parse_hhmm(str(stop.get("time") or ""))
        if current is None:
            continue
        turnaround = 0 if _stop_kind(stop) == "hotel" else 30
        latest_start = next_start - turnaround - _duration_of(stop)
        if current > latest_start and latest_start >= 0:
            current = latest_start
            stop["time"] = _fmt_hhmm(current)
        next_start = current


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
        # A leg mislabelled as "other" is still a leg. Rebalancing may drop a
        # sightseeing stop; it may never quietly drop the flight home.
        if _reads_as_journey(name):
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
    moved = stops[removal["index"]]
    moved_name = _stop_name(moved)
    landed = _move_to_another_day(plan, day_index, removal["index"])
    if landed is None:
        alerts.append(
            f"Day {day_index + 1} is full, and {moved_name} does not fit on any other day, "
            f"so I left it where it is."
        )
        return alerts
    alerts.append(
        f"Day {day_index + 1} was packed, so I moved {moved_name} to Day {landed} "
        f"to keep the route comfortable."
    )
    return alerts


def _move_to_another_day(plan: dict[str, Any], day_index: int, stop_index: int) -> int | None:
    """Relocate a stop the day can no longer hold, rather than deleting it.

    A place the traveller chose is not spare capacity. If no other day can take
    it the stop stays put, because a crowded day is a smaller problem than a
    choice that silently disappears.
    """
    itinerary = plan.get("day_wise_itinerary") or []
    day = itinerary[day_index]
    stops = day.get("stops") if isinstance(day.get("stops"), list) else []
    stop = stops[stop_index]
    if not isinstance(stop, dict):
        return None
    name = _stop_name(stop)
    duration = stop.get("duration_min")
    detached = stops.pop(stop_index)
    placement, _ = choose_placement(
        plan,
        name,
        _stop_kind(stop) or "attraction",
        duration_min=int(duration) if isinstance(duration, (int, float)) else None,
    )
    if placement is None or placement.day == day_index + 1:
        stops.insert(stop_index, detached)
        return None
    for entry in itinerary:
        if not isinstance(entry, dict) or entry.get("day") != placement.day:
            continue
        target = entry.setdefault("stops", [])
        detached["time"] = placement.time
        target.insert(min(placement.index, len(target)), detached)
        return placement.day
    stops.insert(stop_index, detached)
    return None


_JOURNEY_RE = re.compile(
    r"(→|->|\bto\b).*\b(flight|train|bus|drive|transfer|ferry)\b|"
    r"\b(flight|train|bus|drive|transfer|ferry)\b.*(→|->)",
    re.I,
)


def _reads_as_journey(name: str) -> bool:
    """True when a stop name describes travel between places, whatever its kind."""
    return bool(_JOURNEY_RE.search(name or ""))


def _is_leg(stop: Any) -> bool:
    return _stop_kind(stop) in {"flight", "transport"} or _reads_as_journey(_stop_name(stop))


def _restore_undeclared_legs(
    before: dict[str, Any], after: dict[str, Any], declared: set[str]
) -> list[str]:
    """I8. An operation may only remove the entities it declared.

    Swapping a hotel must not take the flight home with it. Rather than trusting
    every mutation path to be careful, the leg is put back afterwards and the
    restoration is reported, so the failure can never be silent.
    """
    allowed = {name.casefold() for name in declared}
    days = after.get("day_wise_itinerary")
    if not isinstance(days, list):
        return []
    surviving = {
        _stop_name(stop).casefold()
        for entry in days
        if isinstance(entry, dict)
        for stop in (entry.get("stops") or [])
        if _stop_name(stop)
    }
    restored: list[str] = []
    for day_index, entry in enumerate(before.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict) or day_index >= len(days):
            continue
        target = days[day_index]
        if not isinstance(target, dict):
            continue
        # A leg that was renamed rather than dropped still reads as travel on
        # the same day, so restoring here would duplicate it.
        if any(_is_leg(stop) for stop in (target.get("stops") or [])):
            continue
        for index, stop in enumerate(entry.get("stops") or []):
            name = _stop_name(stop)
            if not name or name.casefold() in surviving or name.casefold() in allowed:
                continue
            if not _is_leg(stop):
                continue
            stops = target.setdefault("stops", [])
            if not isinstance(stops, list):
                continue
            stops.insert(min(index, len(stops)), deepcopy(stop))
            surviving.add(name.casefold())
            restored.append(name)
    return restored


def _newly_broken(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Invariants this edit broke, ignoring the ones it inherited.

    Writing the invariants was not enough; nothing was reading them back after a
    rebalance, so a stop could be dropped on top of a drive and the trip would
    still report success. Only the newly-broken ones are reported, because a
    pre-existing flaw is not this edit's news.
    """
    was = {(item.code, item.day, item.stop) for item in validate_plan(before)}
    return [
        item.message
        for item in validate_plan(after)
        if (item.code, item.day, item.stop) not in was
    ]


def _repair_known_closed_days(plan: dict[str, Any]) -> list[str]:
    """Move planner-owned visits off weekdays structured hours say are closed."""
    closed_before = {
        (item.day, item.stop) for item in validate_plan(plan) if item.code == "I11"
    }
    if not closed_before:
        return []

    from tripplanner.web import trip_repair

    outcome = trip_repair.repair(plan, only_codes={"I11"})
    closed_after = {
        (item.day, item.stop)
        for item in validate_plan(outcome["plan"])
        if item.code == "I11"
    }
    if len(closed_after) >= len(closed_before):
        return []

    plan.clear()
    plan.update(outcome["plan"])
    return outcome["sentences"]


def _repair_known_opening_hours(plan: dict[str, Any]) -> list[str]:
    """Retime planner-owned visits to fit one complete structured-hours window."""
    if not any(item.code == "I3" for item in validate_plan(plan)):
        return []

    from tripplanner.web import trip_repair

    outcome = trip_repair.repair(plan, only_codes={"I3"})
    if any(item.code == "I3" for item in validate_plan(outcome["plan"])):
        return []

    plan.clear()
    plan.update(outcome["plan"])
    return outcome["sentences"]


def _repair_temporal_infeasibility(plan: dict[str, Any]) -> list[str]:
    """Retime planner-owned stops when travel makes their submitted clocks impossible."""
    if not any(item.code == "I4" for item in validate_plan(plan)):
        return []

    from tripplanner.web import trip_repair

    outcome = trip_repair.repair(plan, only_codes={"I4"})
    if any(item.code == "I4" for item in validate_plan(outcome["plan"])):
        return []

    plan.clear()
    plan.update(outcome["plan"])
    return outcome["sentences"]


def _pacing_text(plan: dict[str, Any]) -> str:
    """What the shape of the trip costs, in words the user could check.

    This is the weaker authority: it never refuses anything and never reports a
    score. Most updates produce nothing here, which is the point — a judgement
    that speaks on every change stops being read.
    """
    lines = coherence_notes(plan)[:2]
    pacing = pacing_statement(plan)
    if pacing:
        lines.append(f"{pacing['statement']} {pacing['remedy']}")
    if not lines:
        return ""
    return "\nWorth mentioning to the user: " + " ".join(lines)


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
    summary = _summary_for_place(name, destination)
    if place_facts.facts_from_summary(summary).unavailable:
        return (
            [
                f"{name} is reported closed for business, so I did not add it. "
                "Choose somewhere still operating."
            ],
            None,
            False,
        )
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

    # Ask the guard first. A day that cannot legally hold the stop is not merely
    # an expensive choice, it is not a candidate at all — which is what keeps a
    # new place off the far side of the flight home.
    placement, rejections = choose_placement(
        plan,
        name,
        stop_kind,
        duration_min=stop.get("duration_min") if isinstance(stop, dict) else None,
        preferred_day=preferred_day,
    )
    best_idx = requested_idx if requested_idx is not None else 0
    guarded_time = ""
    guarded_reason = ""
    if placement is not None:
        for idx, entry in enumerate(itinerary):
            if isinstance(entry, dict) and int(entry.get("day") or idx + 1) == placement.day:
                best_idx = idx
                break
        guarded_time = placement.time
        guarded_reason = placement.reasons[0] if placement.reasons else ""
    elif preferred_day is None:
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

    insert_at = placement.index if placement is not None else _closest_insert_index(
        stops, name, destination
    )
    insert_at = max(0, min(insert_at, len(stops)))
    if insert_at >= len(stops):
        stops.append(stop)
    else:
        stops.insert(insert_at, stop)

    if guarded_time:
        stop["time"] = guarded_time
    elif not str(stop.get("time") or "").strip():
        stop["time"] = _infer_stop_time(stops, insert_at, stop_kind)

    placed_day = int(day.get("day") or best_idx + 1)
    action = "moved" if existing else "placed"
    alerts.append(f"I {action} {name} to Day {placed_day} in stop {insert_at + 1}.")
    if guarded_reason:
        alerts.append(f"Chosen because it costs {guarded_reason}.")
    elif placement is None and rejections:
        blocked = rejections[0]
        alerts.append(
            f"No slot on Day {blocked.day} fits cleanly — the {blocked.window} gap "
            f"{blocked.message}. I placed it anyway; adjust the time if that is wrong."
        )
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


def _reflow_unbooked_attractions(
    plan: dict[str, Any], exempt: set[str] | None = None
) -> bool:
    """Regroup mutable place stops around the current per-day hotel anchors.

    ``exempt`` names stops the caller has just placed deliberately. Rebalancing
    is allowed to tidy the trip around a decision; it is not allowed to quietly
    reverse the decision and leave the explanation pointing at the wrong day.
    """
    spared = {name.lower() for name in (exempt or set())}
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
            if kind == "attraction" and not booked and _stop_name(stop).lower() not in spared:
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

    # A day the traveller has not reached, or has already left, is not a place
    # to park a spare attraction. Rebalancing may choose badly; it may not
    # choose illegally.
    env = envelope(plan)
    legal_days = [
        index
        for index, day in enumerate(days)
        if (
            (env.arrival_day is None or int(day.get("day") or index + 1) >= env.arrival_day)
            and (
                env.departure_day is None
                or int(day.get("day") or index + 1) <= env.departure_day
            )
        )
    ] or list(range(len(days)))

    stop_coords = {
        id(stop): _coords_from_summary(_summary_for_place(_stop_name(stop), destination))
        for _, stop in movable
    }
    assignments: list[list[Any]] = [[] for _ in days]
    # Capacity mirrors where the stops already are. Without that, a single
    # movable stop is handed to the first legal day and a perfectly good day is
    # emptied for no reason the traveller could name.
    legal = set(legal_days)
    target_sizes = [0 for _ in days]
    homeless = 0
    for original_day, _stop in movable:
        if original_day in legal:
            target_sizes[original_day] += 1
        else:
            homeless += 1
    for position in range(homeless):
        target_sizes[legal_days[position % len(legal_days)]] += 1

    for original_day, stop in movable:
        coords = stop_coords[id(stop)]
        available = [index for index in legal_days if len(assignments[index]) < target_sizes[index]]
        if not available:
            available = list(legal_days)

        def score(day_index: int) -> tuple[float, int, int]:
            anchor = anchors[day_index]
            if coords and anchor:
                distance = _haversine_km(coords, anchor)
            else:
                distance = abs(day_index - original_day) * 5.0
            return (distance, len(assignments[day_index]), day_index)

        chosen = min(available, key=score)
        # A time earned on another day means nothing here. Carrying it over is
        # how a stop ends up sitting on top of whatever this day already does
        # at that hour.
        if chosen != original_day and isinstance(stop, dict):
            stop["time"] = ""
        assignments[chosen].append(stop)

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
        hotels = [stop for stop in fixed if _stop_kind(stop) == "hotel"]
        fixed_middle = [stop for stop in fixed if _stop_kind(stop) != "hotel"]
        middle = ordered + fixed_middle
        if middle and all(
            isinstance(stop, dict)
            and _parse_hhmm(str(stop.get("time") or "")) is not None
            for stop in middle
        ):
            middle.sort(key=lambda stop: _parse_hhmm(str(stop.get("time") or "")) or 0)
        next_stops = ([hotels[0]] if hotels else []) + middle
        if len(hotels) > 1:
            next_stops.append(hotels[-1])
        next_stops = _settle_around_legs(next_stops, int(day.get("day") or day_index + 1), env)
        _retime_stops_in_order(next_stops)
        previous_names = [_stop_name(stop) for stop in day.get("stops") or []]
        next_names = [_stop_name(stop) for stop in next_stops]
        if previous_names != next_names:
            changed = True
        day["stops"] = next_stops

    return changed


def _settle_around_legs(stops: list[Any], day_number: int, env: Envelope) -> list[Any]:
    """Put the day's journeys back where the trip says they belong.

    Checking into a hotel before the plane lands is not a scheduling preference,
    it is a lie about where the traveller is. The arrival leg opens its day and
    the departure leg closes its day; everything else keeps the order it had.
    """
    legs = [stop for stop in stops if _is_leg(stop)]
    if not legs:
        return stops
    body = [stop for stop in stops if not _is_leg(stop)]
    lead = legs if day_number == env.arrival_day and day_number != env.departure_day else []
    trail = legs if day_number == env.departure_day and day_number != env.arrival_day else []
    if lead or trail:
        return lead + body + trail

    # A drive in the middle of the day is an anchor too. A stop that cannot
    # finish before the drive pulls away belongs on the far side of it, not on
    # top of it.
    timed_legs = sorted(
        (
            (stop, at)
            for stop in legs
            if (at := _parse_hhmm(str(stop.get("time") or ""))) is not None
        ),
        key=lambda pair: pair[1],
    )
    if not timed_legs:
        return stops

    settled: list[Any] = []
    remaining = list(body)
    for leg, departs in timed_legs:
        before: list[Any] = []
        after: list[Any] = []
        for stop in remaining:
            at = _parse_hhmm(str(stop.get("time") or "")) if isinstance(stop, dict) else None
            duration = stop.get("duration_min") if isinstance(stop, dict) else None
            length = max(15, int(duration)) if isinstance(duration, (int, float)) else 90
            (before if at is not None and at + length <= departs else after).append(stop)
        settled.extend(before)
        settled.append(leg)
        remaining = after
    return settled + remaining


def _settle_plan_legs(plan: dict[str, Any]) -> list[int]:
    """Re-seat every day's journeys against the trip envelope, and report which days moved.

    A leg added after the trip was planned must not keep the position the edit
    happened to drop it in, so this runs on the whole itinerary after any write.
    """
    env = envelope(plan)
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return []
    resettled: list[int] = []
    for index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list) or not stops:
            continue
        raw_day = entry.get("day")
        day_number = raw_day if isinstance(raw_day, int) and raw_day > 0 else index + 1
        settled = _settle_around_legs(stops, day_number, env)
        if [_stop_name(stop) for stop in settled] == [_stop_name(stop) for stop in stops]:
            continue
        _retime_stops_in_order(settled)
        entry["stops"] = settled
        resettled.append(day_number)
    return resettled


def _fit_plan_to_departure(plan: dict[str, Any]) -> list[int]:
    env = envelope(plan)
    itinerary = plan.get("day_wise_itinerary")
    if env.departure_day is None or not env.departure_name or not isinstance(itinerary, list):
        return []
    for index, entry in enumerate(itinerary):
        if not isinstance(entry, dict):
            continue
        raw_day = entry.get("day")
        day_number = raw_day if isinstance(raw_day, int) and raw_day > 0 else index + 1
        if day_number != env.departure_day:
            continue
        stops = entry.get("stops")
        if not isinstance(stops, list):
            return []
        leg_index = next(
            (
                stop_index
                for stop_index, stop in enumerate(stops)
                if _stop_name(stop) == env.departure_name
            ),
            None,
        )
        if leg_index is None:
            return []
        before = json.dumps(stops, sort_keys=True)
        _fit_stops_before_leg(stops, leg_index)
        return [day_number] if json.dumps(stops, sort_keys=True) != before else []
    return []


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


def _normalize_hotel_endpoints(plan: dict[str, Any]) -> bool:
    """Keep one meaningful return stay and make a hotel-only departure actionable."""
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list):
        return False

    changed = False
    days = [day for day in itinerary if isinstance(day, dict)]
    for day in days:
        stops = day.get("stops")
        if not isinstance(stops, list):
            continue
        normalized: list[Any] = []
        for stop in stops:
            if (
                normalized
                and _stop_kind(stop) == "hotel"
                and _stop_kind(normalized[-1]) == "hotel"
                and _stop_name(stop).casefold()
                == _stop_name(normalized[-1]).casefold()
            ):
                previous = normalized[-1]
                if isinstance(previous, dict) and not str(previous.get("note") or "").strip():
                    previous["note"] = "Return to hotel"
                changed = True
                continue
            normalized.append(stop)
        if len(normalized) != len(stops):
            day["stops"] = normalized
            stops = normalized
        if (
            len(stops) == 1
            and _stop_kind(stops[0]) == "hotel"
            and "check" in f"{day.get('title') or ''} {day.get('summary') or ''}"
            .casefold()
        ):
            stop = stops[0]
            if isinstance(stop, dict):
                if not str(stop.get("time") or "").strip():
                    stop["time"] = "11:00"
                    changed = True
                if (
                    not str(stop.get("note") or "").strip()
                    or str(stop.get("note")).casefold() == "check-out"
                ):
                    stop["note"] = (
                        "Check out by 11:00 (confirm with your hotel). "
                        "Leave bags with reception if your onward departure is later."
                    )
                    changed = True
    return changed


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
    before = deepcopy(plan)
    declared = {name}
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
        if preferred_day is None and _reflow_unbooked_attractions(plan, {name}):
            alerts.append("Rebalanced unbooked itinerary stops around the updated trip.")
        canonical_kind = _canonical_place_kind(kind)
        if canonical_kind == "attraction" and preferred_day is None:
            itinerary = plan.get("day_wise_itinerary") or []
            for day_index in range(len(itinerary)):
                alerts.extend(_rebalance_day(plan, day_index, name, canonical_kind))
            _reflow_unbooked_attractions(plan, {name})
    elif not already_selected:
        bucket.append(item)
    restored = _restore_undeclared_legs(before, plan, declared)
    if restored:
        alerts.append(
            "Kept " + ", ".join(restored) + " — that leg was not part of this change."
        )
    stray = unexpected_changes(diff_stops(before, plan), declared)
    if stray:
        alerts.append("Fitting that in also had a knock-on effect. " + receipt(stray))
    alerts.extend(_newly_broken(before, plan))
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
    if kind == "hotel" and not all_occurrences:
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


def confirm_stop_place(name: str) -> bool:
    """Bind an itinerary stop to the place the provider found for it.

    The map offers a candidate when a stop resolves to a differently-named
    place; agreeing to it is what makes that pin appear, and it stays agreed to
    on later builds. Resolution happens here rather than from the request so a
    binding can only ever be what the map actually offered.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    target = str(name or "").strip()
    if not target:
        return False
    details = places_cache.get_details(target, str(plan.get("destination") or "")) or {}
    if details.get("lat") is None or details.get("lng") is None:
        return False
    bindings = plan.get("place_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
        plan["place_bindings"] = bindings
    bindings[target.lower()] = {
        "name": str(details.get("name") or target),
        "place_id": details.get("place_id"),
        "lat": details.get("lat"),
        "lng": details.get("lng"),
        "address": details.get("address") or "",
    }
    _save_active_trip(plan)
    return True


def _save_active_trip(plan: dict[str, Any]) -> None:
    # Stamp a stable id + freshness so the trip can live in history and be
    # listed / resumed later. Every save mirrors to the trips collection so
    # in-progress drafts are never lost when the user switches trips.
    if not plan.get("trip_id"):
        plan["trip_id"] = _compute_trip_id(plan)
    _normalize_hotel_endpoints(plan)
    plan["updated_at"] = datetime.now().isoformat()

    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID, plan
        )
    else:
        _ensure_dirs()
        atomic_write_json(_resolve_active_trip_path(), plan, indent=2)
    _mirror_to_history(plan)


@_serialized_mutation
def restore_inspection_trip(plan: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Persist an audit artifact for local read-only inspection without archiving it."""
    restored = deepcopy(plan)
    restored["user_id"] = user_id
    if not restored.get("trip_id"):
        restored["trip_id"] = _compute_trip_id(restored)
    _normalize_hotel_endpoints(restored)
    restored["updated_at"] = datetime.now().isoformat()
    trip_id = str(restored["trip_id"])
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, user_id, _ACTIVE_TRIP_DOC_ID, restored
        )
        storage_cosmos.upsert_doc(_COSMOS_TRIPS_CONTAINER, user_id, trip_id, restored)
    else:
        _ensure_dirs()
        atomic_write_json(_resolve_active_trip_path(), restored, indent=2)
        atomic_write_json(_resolve_trip_history_dir() / f"{trip_id}.json", restored, indent=2)
    return restored


@_serialized_mutation
def record_trip_decision(decision) -> bool:
    """Attach a recorded comparison to the active trip.

    Non-tool: decisions ride inside the trip document so a plan and the reasoning
    behind it can never be loaded from two different writes.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    upsert_decision(plan, decision)
    _save_active_trip(plan)
    return True


@_serialized_mutation
def record_price_check(kind: str, provider: str) -> bool:
    """Note that we looked at a live source, so the plan can say when.

    Non-tool. Silently does nothing without an active trip: a search before a
    trip exists has nothing to be provenance for.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    record_check(plan, make_check(kind, provider))
    _save_active_trip(plan)
    return True


@_serialized_mutation
def apply_decision_override(
    decision_id: str, option_id: str | None, *, expected_updated_at: str = ""
) -> dict[str, Any]:
    """Switch the plan onto a traveller's chosen option, or undo that switch.

    ``option_id`` of ``None`` restores the agent's own choice. A non-empty
    ``expected_updated_at`` that no longer matches means another window already
    moved this trip, so nothing is written.
    """
    from tripplanner.decisions.apply import apply_override, restore

    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "stale": False, "message": "There is no active trip."}
    if expected_updated_at and str(plan.get("updated_at") or "") != expected_updated_at:
        return {
            "ok": False,
            "stale": True,
            "message": "This trip changed somewhere else. Reloaded it for you.",
        }
    result = (
        apply_override(plan, decision_id, option_id)
        if option_id
        else restore(plan, decision_id)
    )
    if result.ok:
        _save_active_trip(plan)
    return {"stale": False, **result.as_dict()}


@_serialized_mutation
def apply_decision_overrides(
    changes: list[dict[str, Any]], *, expected_updated_at: str = ""
) -> dict[str, Any]:
    """Apply several decision changes atomically against one trip revision."""
    from tripplanner.decisions.apply import apply_override, restore

    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "stale": False, "message": "There is no active trip."}
    if expected_updated_at and str(plan.get("updated_at") or "") != expected_updated_at:
        return {
            "ok": False,
            "stale": True,
            "message": "This trip changed somewhere else. Reloaded it for you.",
            "results": [],
        }
    if not changes:
        return {
            "ok": False,
            "stale": False,
            "message": "No budget changes were supplied.",
            "results": [],
        }

    candidate = deepcopy(plan)
    results = []
    for change in changes:
        decision_id = str(change.get("decision_id") or "")
        option_id = change.get("option_id")
        result = (
            restore(candidate, decision_id)
            if option_id in (None, "")
            else apply_override(candidate, decision_id, str(option_id))
        )
        results.append(result.as_dict())
        if not result.ok:
            return {
                "ok": False,
                "stale": False,
                "message": (
                    "No changes were saved because one or more choices could not be applied."
                ),
                "failed_change": {"decision_id": decision_id, "option_id": option_id},
                "results": results,
            }

    _save_active_trip(candidate)
    total_delta = round(sum(float(result.get("delta") or 0) for result in results), 2)
    return {
        "ok": True,
        "stale": False,
        "message": f"Applied {len(results)} budget changes together.",
        "results": results,
        "total_cost": candidate.get("total_cost"),
        "delta": total_delta,
        "currency": str(candidate.get("currency") or "EUR"),
    }


@_serialized_mutation
def repair_active_trip(*, expected_updated_at: str = "") -> dict[str, Any]:
    """Rearrange the planner's own stops until the saved trip reads correctly."""
    from tripplanner.web import trip_repair

    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "stale": False, "message": "There is no active trip."}
    if expected_updated_at and str(plan.get("updated_at") or "") != expected_updated_at:
        return {
            "ok": False,
            "stale": True,
            "message": "This trip changed somewhere else. Reloaded it for you.",
        }

    outcome = trip_repair.repair(plan)
    if outcome["changed"]:
        _save_active_trip(outcome["plan"])
    return {
        "ok": True,
        "stale": False,
        "changed": outcome["changed"],
        "message": (
            " ".join(outcome["sentences"])
            if outcome["changed"]
            else "Nothing to rearrange; the plan is already the best I can make it."
        ),
        "moves": outcome["moves"],
        "blocked": outcome["blocked"],
        "before": outcome["before"],
        "after": outcome["after"],
    }


@_serialized_mutation
def refresh_active_trip_facts(*, expected_updated_at: str = "") -> dict[str, Any]:
    """Recheck itinerary place facts and persist the resulting observation."""
    from tripplanner.web import trip_freshness

    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "stale": False, "message": "There is no active trip."}
    if expected_updated_at and str(plan.get("updated_at") or "") != expected_updated_at:
        return {
            "ok": False,
            "stale": True,
            "message": "This trip changed somewhere else. Reloaded it for you.",
        }
    outcome = trip_freshness.refresh(plan)
    _save_active_trip(outcome["plan"])
    return {
        "ok": True,
        "stale": False,
        "message": "Rechecked the itinerary's place facts.",
        **{key: value for key, value in outcome.items() if key != "plan"},
    }


@_serialized_mutation
def recheck_active_trip_prices(*, expected_updated_at: str = "") -> dict[str, Any]:
    """Explicitly refresh stale quote evidence without changing trip selections."""
    from tripplanner.decisions.price_recheck import recheck_prices

    plan = _load_active_trip()
    if not plan:
        return {"ok": False, "stale": False, "message": "There is no active trip."}
    if expected_updated_at and str(plan.get("updated_at") or "") != expected_updated_at:
        return {
            "ok": False,
            "stale": True,
            "message": "This trip changed somewhere else. Reloaded it for you.",
        }
    outcome = recheck_prices(plan)
    if outcome["results"]:
        _save_active_trip(outcome["plan"])
    return {
        "ok": True,
        "stale": False,
        "message": (
            "Rechecked the trip's stale provider prices."
            if outcome["results"]
            else "No stale finalized-trip prices need rechecking."
        ),
        "results": outcome["results"],
        "rechecked": outcome["rechecked"],
    }


def _mirror_to_history(plan: dict[str, Any]) -> None:
    """Persist the plan into the per-user trips collection under its trip_id."""
    tid = plan.get("trip_id")
    if not tid:
        return
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), tid, plan)
    else:
        _ensure_dirs()
        atomic_write_json(_resolve_trip_history_dir() / f"{tid}.json", plan, indent=2)
    debug_store.record_trip(plan, get_user_id())


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
        "trip_number": int(plan.get("trip_number") or 0),
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
        "created_at": str(plan.get("created_at") or ""),
        "updated_at": str(plan.get("updated_at") or plan.get("created_at") or ""),
        "is_active": bool(active_id) and tid == active_id,
    }


def _next_trip_number(plans: list[dict[str, Any]] | None = None) -> int:
    """Next per-user number, or 0 when history is unreadable.

    Numbering is a display aid, so a storage hiccup leaves a trip unnumbered
    rather than failing the save that carries the traveller's actual plan.
    """
    try:
        known = plans if plans is not None else _all_history_trips()
    except Exception:  # noqa: BLE001
        return 0
    return max((int(p.get("trip_number") or 0) for p in known), default=0) + 1


def _ensure_trip_numbers(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One-time numbering for trips saved before trip_number existed."""
    missing = [plan for plan in plans if not plan.get("trip_number")]
    if not missing:
        return plans
    following = _next_trip_number(plans)
    for plan in sorted(missing, key=lambda p: str(p.get("created_at") or "")):
        plan["trip_number"] = following
        # Re-read before writing: the listed snapshot must never overwrite a
        # newer version of the trip that another window already saved.
        current = _load_history_trip(str(plan.get("trip_id") or ""))
        if current and not current.get("trip_number"):
            current["trip_number"] = following
            _mirror_to_history(current)
        following += 1
    return plans


def list_saved_trips() -> list[dict[str, Any]]:
    """All saved trips as compact descriptors, most-recently-updated first.

    Non-tool: powers the SPA's "My trips" switcher and the resume flow.
    """
    active = _load_active_trip()
    active_id = (active or {}).get("trip_id") if active else None
    summaries = [
        _trip_summary(p, active_id) for p in _ensure_trip_numbers(_all_history_trips())
    ]
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
    from tripplanner.web import trip_feedback

    if not trip_id:
        return False
    active = _load_active_trip()
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    else:
        (_resolve_trip_history_dir() / f"{trip_id}.json").unlink(missing_ok=True)
    trip_feedback.delete_for_trip(trip_id)
    if active and active.get("trip_id") == trip_id:
        _delete_active_trip()
    return True


@_serialized_mutation
def clear_all_trip_history() -> int:
    """Delete all saved trips for the current user and clear active trip."""
    from tripplanner.web import trip_feedback

    if storage_cosmos.is_enabled():
        deleted = storage_cosmos.delete_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
        trip_feedback.clear()
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
    trip_feedback.clear()
    _delete_active_trip()
    return deleted


@_serialized_mutation
def record_trip_feedback(
    *,
    feedback_id: str | None,
    sentiment: str | None,
    rating: int | None,
    comment: str | None,
    surface: str,
    client: str,
) -> dict[str, Any] | None:
    """Append feedback for the active trip and update its lightweight rollup."""
    from tripplanner.web import trip_feedback

    plan = _load_active_trip()
    if not plan or not plan.get("trip_id"):
        return None
    current_rollup = plan.get("feedback")
    rollup = dict(current_rollup) if isinstance(current_rollup, dict) else {}
    submission = (
        trip_feedback.amend(
            feedback_id,
            trip_id=str(plan["trip_id"]),
            rating=rating,
            comment=comment,
        )
        if feedback_id
        else trip_feedback.append(
            trip_id=str(plan["trip_id"]),
            trip_revision=str(plan.get("updated_at") or ""),
            sentiment=sentiment,
            rating=rating,
            comment=comment,
            surface=surface,
            client=client,
            identified=get_user_id() != "local" and not get_user_id().startswith("guest-"),
        )
    )
    if submission is None:
        return None
    count = int(rollup.get("count") or 0) + (0 if feedback_id else 1)
    rollup.update(
        {
            "count": count,
            "last_at": submission["created_at"],
            "last_rating": submission.get("rating"),
            "last_sentiment": submission.get("sentiment"),
        }
    )
    plan["feedback"] = rollup
    _save_active_trip(plan)
    return {**rollup, "feedback_id": submission["feedback_id"]}


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


# What a reset keeps: where you are going, when, who with, and what you told us
# you like. Everything else is the plan, and the plan is what you are throwing
# away. Starting over should not mean typing your dates in again.
_RESET_KEEPS = frozenset(
    {
        "trip_id",
        "created_at",
        "destination",
        "origin",
        "travel_scope",
        "departure_date",
        "return_date",
        "travelers",
        "notes",
        "budget",
        "currency",
        "preferences_snapshot",
        "planning_recommendation",
        "trip_constraints",
        "visa",
    }
)


@_serialized_mutation
def reset_active_trip() -> dict[str, Any] | None:
    """Empty the active trip's plan while keeping its brief.

    Non-tool: called by the "Reset" button. Returns the emptied plan, or
    ``None`` when there is nothing active to reset.
    """
    plan = _load_active_trip()
    if not plan:
        return None
    fresh = {key: value for key, value in plan.items() if key in _RESET_KEEPS}
    fresh["status"] = "draft"
    fresh["day_wise_itinerary"] = []
    fresh["selected_flights"] = []
    fresh["selected_hotels"] = []
    fresh["selected_activities"] = []
    _save_active_trip(fresh)
    return fresh


@tool
@_serialized_mutation
def create_trip_plan(
    destination: str,
    departure_date: str,
    return_date: str,
    origin: str = "",
    travel_scope: str = "",
    travelers_summary: str = "",
    notes: str = "",
    planning_recommendation_json: str = "",
) -> str:
    """Create a new trip plan draft. Call this to start planning a trip.

    Args:
        destination: Where the user wants to go.
        departure_date: YYYY-MM-DD.
        return_date: YYYY-MM-DD.
        origin: Departure city (defaults from preferences if not provided).
        travel_scope: "round_trip" when planning travel from the origin, or
            "destination_only" when the traveller will arrange their own way there.
        travelers_summary: Name everyone travelling, e.g. 'Munish, Priya, and
            Aarav (5)'. Names matter: per-traveller passport and visa checks
            only run for people this text names. Fall back to counts
            ('2 adults, 1 child (age 5)') only when you do not know the names.
        notes: Any special requirements or notes.
        planning_recommendation_json: Complete JSON returned by recommend_trip_duration.
    """
    prefs = load_preferences()
    travel_scope = travel_scope.strip().lower()
    if travel_scope not in {"", "round_trip", "destination_only"}:
        return "Error: travel_scope must be round_trip or destination_only."
    origin_supplied = bool(origin.strip())
    profile = prefs.get("profile") or {}
    if travel_scope == "destination_only":
        origin = ""
    elif not origin_supplied:
        home_city = str(profile.get("home_city") or "").strip()
        home_area = str(profile.get("home_area") or "").strip()
        origin = (
            f"{home_area}, {home_city}"
            if home_area and home_city and home_city.casefold() not in home_area.casefold()
            else home_area or home_city
        )
    if not travel_scope and origin:
        travel_scope = "round_trip"
    planning_recommendation: dict[str, Any] | None = None
    if planning_recommendation_json:
        try:
            parsed_recommendation = json.loads(planning_recommendation_json)
        except json.JSONDecodeError:
            return "Error: planning_recommendation_json must be valid JSON."
        if not isinstance(parsed_recommendation, dict):
            return "Error: planning_recommendation_json must be a JSON object."
        planning_recommendation = parsed_recommendation
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
        if origin_supplied or not str(existing.get("origin") or "").strip():
            existing["origin"] = origin
        if travel_scope:
            existing["travel_scope"] = travel_scope
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
        "trip_number": _next_trip_number(),
        "created_at": datetime.now().isoformat(),
        "destination": destination,
        "origin": origin,
        "travel_scope": travel_scope,
        "departure_date": departure_date,
        "return_date": return_date,
        "travelers": travelers_summary,
        "notes": notes,
        "planning_recommendation": planning_recommendation,
        "preferences_snapshot": {
            "trip_style": prefs["trip_style"],
            "planning_preferences": prefs.get("planning_preferences") or {},
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
        "weather": {},
        # What check_visa_requirements found for this trip, so the answer
        # survives the conversation it was given in.
        "visa": {},
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


def _itinerary_day_number(day: Any) -> int | None:
    if not isinstance(day, dict):
        return None
    try:
        return int(day.get("day"))
    except (TypeError, ValueError):
        return None


def _merge_itinerary_days(
    existing: list[Any], incoming: list[Any]
) -> tuple[list[Any], bool]:
    """Fold a partial ``day_wise_itinerary`` update into the saved itinerary.

    The tool contract asks for the whole itinerary on every update, but a
    single-stop edit ("swap the Indore hotel") often comes back carrying only
    the day that changed. Assigning that wholesale silently deletes every other
    day, so a strict subset of already-planned day numbers is merged in place
    instead. A full resubmit, an added day, or a renumbered itinerary still
    replaces the list.
    """
    if not existing or not incoming:
        return incoming, False
    incoming_numbers = [_itinerary_day_number(day) for day in incoming]
    if any(number is None for number in incoming_numbers):
        return incoming, False
    if len(incoming) >= len(existing):
        return incoming, False
    existing_numbers = {_itinerary_day_number(day) for day in existing}
    if not set(incoming_numbers).issubset(existing_numbers):
        return incoming, False
    replacements = dict(zip(incoming_numbers, incoming))
    merged = [
        replacements.get(_itinerary_day_number(day), day) for day in existing
    ]
    return merged, True


def _journey_matches(stop: Any, origin: str, destination: str) -> bool:
    if _stop_kind(stop) not in {"flight", "transport"}:
        return False
    name = re.sub(r"[^a-z0-9]+", " ", _stop_name(stop).casefold()).strip()
    source = re.sub(r"[^a-z0-9]+", " ", origin.casefold()).strip()
    target = re.sub(r"[^a-z0-9]+", " ", destination.casefold()).strip()
    source_index = name.find(source)
    return source_index >= 0 and name.find(target, source_index + len(source)) > source_index


def _ensure_selected_flight_legs(plan: dict[str, Any], previous_origin: str = "") -> list[str]:
    if not plan.get("selected_flights"):
        return []
    origin = str(plan.get("origin") or "").strip()
    destination = str(plan.get("destination") or "").strip()
    itinerary = plan.get("day_wise_itinerary")
    if not origin or not destination or origin.casefold() == destination.casefold() or not itinerary:
        return []
    days = [day for day in itinerary if isinstance(day, dict)]
    if not days:
        return []

    added: list[str] = []
    first_stops = days[0].setdefault("stops", [])
    last_stops = days[-1].setdefault("stops", [])
    if previous_origin and previous_origin.casefold() != origin.casefold():
        for stops, source, target in (
            (first_stops, previous_origin, destination),
            (last_stops, destination, previous_origin),
        ):
            if not isinstance(stops, list):
                continue
            for stop in stops:
                if not isinstance(stop, dict) or not _journey_matches(stop, source, target):
                    continue
                stop["name"] = re.sub(
                    re.escape(previous_origin), origin, _stop_name(stop), count=1,
                    flags=re.IGNORECASE,
                )
                added.append(str(stop["name"]))
    if isinstance(first_stops, list) and not any(
        _journey_matches(stop, origin, destination) for stop in first_stops
    ):
        outbound = {"name": f"Flight: {origin} to {destination}", "kind": "flight"}
        hotel_index = next(
            (index for index, stop in enumerate(first_stops) if _stop_kind(stop) == "hotel"),
            len(first_stops),
        )
        first_stops.insert(hotel_index, outbound)
        added.append(outbound["name"])

    if isinstance(last_stops, list) and not any(
        _journey_matches(stop, destination, origin) for stop in last_stops
    ):
        inbound = {"name": f"Flight: {destination} to {origin}", "kind": "flight"}
        hotel_indexes = [
            index for index, stop in enumerate(last_stops) if _stop_kind(stop) == "hotel"
        ]
        insert_at = hotel_indexes[-1] + 1 if hotel_indexes else len(last_stops)
        last_stops.insert(insert_at, inbound)
        added.append(inbound["name"])
    return added


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
        - budget: {"amount": number, "currency": ISO code, "owner": "user"} - the
            user's total budget for THIS trip. Set only from an explicit user target.
    - currency: ISO code of the sticky display currency ("INR", "USD", "EUR",
      ...) — set it once when you pick the plan's currency so every surface
      (including the budget meter) shows the same symbol
        - weather: normalized get_weather_forecast result with source, note, days,
            and optional packing_advice. If Open-Meteo fails completely, use source
            "agent_climate_estimate" and clearly label monthly climate knowledge.
    - notes: string
    - trip_constraints: list of strings — one-off exceptions/constraints that
      apply to THIS trip ONLY (e.g. "3-star hotel is fine just for this trip",
      "OK with one connection this time"). Use this for anything the user says
      is a one-time exception; NEVER save such one-offs to durable preferences.
    - travel_scope: "round_trip" when you are planning the journey there and
      back, or "destination_only" when the user says they will arrange getting
      there themselves. Set it as soon as the user answers, so the trip stops
      being asked for an origin it does not need.
    - visa: what check_visa_requirements found, so it outlives the chat. Shape:
      {"passport_country": "Indian", "destination_country": "Mexico",
       "status": "required" | "e_visa" | "on_arrival" | "visa_free" | "unclear",
       "processing_days_typical": 21, "official_url": "https://...",
       "source_domain": "gob.mx", "checked_on": "YYYY-MM-DD", "note": "one line"}
      Use 0 for processing_days_typical when no source states one — never
      estimate it, because it drives a deadline warning.

    Example: '{"selected_flights": [{"option": 1, "airline": "IndiGo", "price": 8500}]}'
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan. Use create_trip_plan first."

    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError:
        return "Error: invalid JSON."

    if "day_wise_itinerary" in updates and not has_structured_itinerary(updates):
        return (
            "Error: day_wise_itinerary must contain the full structured itinerary "
            "with a stops list for every day. The saved itinerary was not changed."
        )

    validation_plan = dict(plan)
    if isinstance(updates.get("day_wise_itinerary"), list):
        validation_plan["day_wise_itinerary"] = [
            *(plan.get("day_wise_itinerary") or []),
            *updates["day_wise_itinerary"],
        ]
    hotel_destination_errors = _hotel_destination_errors(
        str(plan.get("destination") or ""),
        updates.get("selected_hotels"),
        _itinerary_hotel_locations(validation_plan),
    )
    if hotel_destination_errors:
        return (
            "Error: hotel location must match the active trip destination. "
            + " ".join(hotel_destination_errors)
            + " Search again using the active trip destination and resubmit the full update."
        )

    allowed_keys = {
        "selected_flights", "selected_hotels", "selected_activities",
        "day_wise_itinerary", "cost_breakdown", "total_cost", "notes",
        "origin", "budget", "currency", "weather", "trip_constraints",
        "visa", "travel_scope",
    }
    before = json.loads(json.dumps(plan))  # deep copy for diff
    merged_partial_itinerary = False
    for key, val in updates.items():
        if key in allowed_keys:
            if key == "budget":
                if isinstance(val, int | float) and not isinstance(val, bool):
                    val = {
                        "amount": val,
                        "currency": str(updates.get("currency") or plan.get("currency") or "INR"),
                        "owner": "user",
                        "updated_at": datetime.now().isoformat(),
                    }
                elif isinstance(val, dict):
                    val = {
                        **val,
                        "currency": str(
                            val.get("currency")
                            or updates.get("currency")
                            or plan.get("currency")
                            or "INR"
                        ),
                        "owner": "user",
                        "updated_at": datetime.now().isoformat(),
                    }
            if key == "selected_hotels" and isinstance(val, list):
                lodging_locations = _itinerary_hotel_locations(validation_plan)
                destination = str(plan.get("destination") or "").strip().lower()
                if destination:
                    lodging_locations = lodging_locations | {destination} | {
                        part.strip()
                        for part in re.split(r"[,&/()]| and ", destination)
                        if part.strip()
                    }
                val = [
                    hotel
                    for hotel in val
                    if not _HOTEL_PLACEHOLDER_RE.search(_stop_name(hotel))
                    and not unnamed_lodging(_stop_name(hotel), lodging_locations)
                ]
            if key == "day_wise_itinerary" and isinstance(val, list):
                val, merged_partial_itinerary = _merge_itinerary_days(
                    plan.get("day_wise_itinerary") or [], val
                )
            plan[key] = val

    resettled_days: list[int] = []
    if "day_wise_itinerary" in updates:
        resettled_days = _fit_plan_to_departure(plan)
        time_errors = _itinerary_time_errors(plan.get("day_wise_itinerary"))
        if time_errors:
            return (
                "Error: itinerary times must increase in circuit order. "
                + " ".join(time_errors)
                + " Resubmit the full corrected day_wise_itinerary."
            )

    if {"selected_hotels", "day_wise_itinerary"}.intersection(updates) and (
        _sync_replaced_hotel_anchors(
            plan,
            before.get("selected_hotels"),
            plan.get("selected_hotels"),
        )
    ):
        _reflow_unbooked_attractions(plan)
    if "selected_hotels" in updates:
        from tripplanner.decisions.lodging import reconcile_selected_lodging

        reconcile_selected_lodging(plan)
    if "selected_flights" in updates:
        from tripplanner.decisions.flights import reconcile_selected_flight

        reconcile_selected_flight(plan)

    added_flight_legs = []
    if {"origin", "selected_flights"}.intersection(updates):
        added_flight_legs = _ensure_selected_flight_legs(
            plan, str(before.get("origin") or "")
        )

    # Only a declared change to the flights may remove a leg. Swapping a hotel
    # or resubmitting one day of the itinerary may not.
    declared_legs: set[str] = set()
    if "selected_flights" in updates:
        declared_legs = {
            _stop_name(leg)
            for leg in (before.get("selected_flights") or [])
            if _stop_name(leg)
        }
    restored_legs = _restore_undeclared_legs(before, plan, declared_legs)

    resettled_days = list(dict.fromkeys([*resettled_days, *_settle_plan_legs(plan)]))
    closed_day_repairs = _repair_known_closed_days(plan)
    opening_hours_repairs = _repair_known_opening_hours(plan)
    feasibility_repairs = _repair_temporal_infeasibility(plan)
    violations = validate_plan(plan)
    availability_errors = [
        violation.message for violation in violations if violation.code == "I12"
    ]
    if availability_errors:
        return (
            "Error: itinerary places reported closed for business cannot be saved. "
            + " ".join(availability_errors)
            + " Replace them with places that are still operating and resubmit the full "
            "day_wise_itinerary. The saved itinerary was not changed."
        )
    envelope_errors = [violation.message for violation in violations if violation.code == "I1"]
    if envelope_errors:
        return (
            "Error: itinerary stops must stay within the trip arrival and departure times. "
            + " ".join(envelope_errors)
            + " Resubmit the full corrected day_wise_itinerary. "
            "The saved itinerary was not changed."
        )
    # Rejecting here discarded the turn's only copy of the itinerary, so a plan that
    # was merely incomplete ended up saved as no plan at all.
    sanity_errors = persistence_sanity_errors(plan)
    _save_active_trip(plan)
    broken_invariants = _newly_broken(before, plan)
    restaurant_warnings = _restaurant_itinerary_warnings(
        plan.get("day_wise_itinerary"),
        cities=_itinerary_hotel_locations(plan),
        dietary=_dietary_preferences(plan),
    )
    empty_day_warnings = _empty_itinerary_day_warnings(plan.get("day_wise_itinerary"))
    transport_warnings = _round_trip_transport_warnings(plan)
    hotel_warnings = _hotel_selection_warnings(plan)
    warning_text = ""
    if sanity_errors:
        warning_text += (
            "\nThe itinerary was saved but is not yet consistent: "
            + " ".join(sanity_errors[:5])
            + " Replan the affected journey or day as a whole and resubmit the full "
            "day_wise_itinerary. Do not report the trip as planned while this stands."
        )
    if restored_legs:
        warning_text += (
            "\nKept "
            + ", ".join(restored_legs)
            + ": this update did not declare a change to the flights, so the leg was "
            "restored. Send selected_flights when you mean to change travel."
        )
    if added_flight_legs:
        warning_text += "\nAdded missing trip legs: " + ", ".join(added_flight_legs) + "."
    if resettled_days:
        warning_text += (
            "\nReordered Day "
            + ", ".join(str(day) for day in resettled_days)
            + " so each journey opens or closes its day."
        )
    if closed_day_repairs:
        warning_text += "\nAdjusted known closed-day visits before saving: " + " ".join(
            closed_day_repairs
        )
    if opening_hours_repairs:
        warning_text += (
            "\nAdjusted visits to fit known opening hours before saving: "
            + " ".join(opening_hours_repairs)
        )
    if feasibility_repairs:
        warning_text += "\nAdjusted travel-infeasible visit times before saving: " + " ".join(
            feasibility_repairs
        )
    if broken_invariants:
        warning_text += (
            "\nThis change broke the itinerary: "
            + " ".join(broken_invariants)
            + " Replan the affected day or days as a whole — move, retime, or drop the "
            "stops that no longer fit — and resubmit the full day_wise_itinerary. Do not "
            "report the trip as updated while this stands."
        )
    if merged_partial_itinerary:
        warning_text += (
            "\nPartial itinerary update merged: only the days you sent were replaced, "
            "the other planned days were kept. Send the full day_wise_itinerary when "
            "you mean to change the shape of the trip."
        )
    if restaurant_warnings:
        warning_text += (
            "\nRestaurant planning incomplete: "
            + " ".join(restaurant_warnings)
            + " Call nearby_restaurants, choose preference-matched options, and update "
            "day_wise_itinerary with concrete restaurant names before finishing."
        )
    if empty_day_warnings:
        warning_text += (
            "\nItinerary planning incomplete: "
            + " ".join(empty_day_warnings)
            + " Restore concrete attractions or named restaurants on those days and "
            "resubmit the full day_wise_itinerary before finishing."
        )
    if transport_warnings:
        warning_text += (
            "\nRound-trip transport planning incomplete: "
            + " ".join(transport_warnings)
            + " Add the explicit inter-city journey stops in itinerary order and "
            "resubmit the full day_wise_itinerary before finishing."
        )
    if hotel_warnings:
        warning_text += (
            "\nHotel planning incomplete: "
            + " ".join(hotel_warnings)
            + " Call search_hotels, choose the best preference-matched real option by "
            "default, verify it with search_places_with_reviews, and replace every generic "
            "or placeholder hotel label before finishing."
        )
    bullets = diff_plans(before, plan)
    if not bullets:
        return f"Trip plan updated (no material changes). Status: {plan['status']}{warning_text}"
    return (
        f"Trip plan updated. Status: {plan['status']}\n"
        f"What changed:\n{format_diff(bullets)}{warning_text}{_pacing_text(plan)}"
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

    gaps = finalization_gaps(plan)
    if gaps:
        reasons = "\n".join(f"- {gap}" for gap in gaps)
        return (
            "Cannot finalize: this trip is not ready for booking.\n"
            f"{reasons}\n"
            "Resolve these gaps and try finalizing again."
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
        plan_currency = str(plan.get("currency") or "INR")
        lines.append("  COST BREAKDOWN:")
        for item, cost in plan["cost_breakdown"].items():
            lines.append(
                f"    {item}: {money(cost, plan_currency)}"
                if isinstance(cost, (int, float))
                else f"    {item}: {cost}"
            )
        lines.append(
            f"\n  TOTAL ESTIMATED COST: {money(plan.get('total_cost', 0) or 0, plan_currency)}"
        )
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
