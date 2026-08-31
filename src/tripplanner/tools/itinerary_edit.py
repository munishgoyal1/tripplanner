"""Pure itinerary placement, timing, rebalancing, and repair helpers."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from tripplanner import place_facts
from tripplanner.tools.trip_common import (
    _canonical_place_kind,
    _coords_from_summary,
    _day_stats,
    _fmt_hhmm,
    _haversine_km,
    _parse_hhmm,
    _stop_kind,
    _stop_name,
    _style_caps,
    _summary_for_place,
)
from tripplanner.tools.trip_effort import coherence_notes, pacing_statement
from tripplanner.tools.trip_guard import (
    Envelope,
    _duration_of,
    choose_placement,
    envelope,
    validate_plan,
)


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
    next_start = _parse_hhmm(str(leg.get("time") or "")) if isinstance(leg, dict) else None
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


def _remove_candidate(
    day: dict[str, Any], destination: str, new_name: str
) -> dict[str, Any] | None:
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
            f"Day {day_index + 1} is getting full; I added {new_name} but couldn't find "
            "a safe stop to remove automatically."
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
        item.message for item in validate_plan(after) if (item.code, item.day, item.stop) not in was
    ]


def _repair_known_closed_days(plan: dict[str, Any]) -> list[str]:
    """Move planner-owned visits off weekdays structured hours say are closed."""
    closed_before = {(item.day, item.stop) for item in validate_plan(plan) if item.code == "I11"}
    if not closed_before:
        return []

    from tripplanner.web import trip_repair

    outcome = trip_repair.repair(plan, only_codes={"I11"})
    closed_after = {
        (item.day, item.stop) for item in validate_plan(outcome["plan"]) if item.code == "I11"
    }
    if not closed_after < closed_before:
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
                    f"Day {preferred_day} is not available yet because the itinerary has no "
                    "structured days. Choose Best day, or create the day-by-day itinerary first."
                ],
                None,
                False,
            )
        alerts.append(
            f"{name} was saved. Your assistant will slot it into a day-by-day plan once the "
            "itinerary is structured."
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
        stops = (
            day.get("stops") if isinstance(day, dict) and isinstance(day.get("stops"), list) else []
        )
        logical_day = (
            int(day.get("day") or day_index + 1) if isinstance(day, dict) else day_index + 1
        )
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
            [
                f"That {name} occurrence changed before it could be moved. Refresh and choose "
                "it again."
            ],
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
            alerts.append(f"{name} is already on Day {existing_day_num}; I refreshed its details.")
            return alerts, placement, True
        if isinstance(raw, dict) and raw.get("booked"):
            return (
                [
                    f"{name} is booked on Day {existing_day_num}, so I did not move it to Day "
                    f"{preferred_day}. Keep Day {existing_day_num}, or unbook it and choose Day "
                    f"{preferred_day} again."
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
                score += (
                    45 if any(_stop_kind(s) == "hotel" for s in stops if isinstance(s, dict)) else 0
                )
            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

    day = itinerary[best_idx]
    stops = day.setdefault("stops", []) if isinstance(day, dict) else []

    insert_at = (
        placement.index
        if placement is not None
        else _closest_insert_index(stops, name, destination)
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


def _day_entry_and_stops(
    itinerary: list[Any], day_num: int
) -> tuple[dict[str, Any] | None, list[Any]]:
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


def _reflow_unbooked_attractions(plan: dict[str, Any], exempt: set[str] | None = None) -> bool:
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
                anchor = _coords_from_summary(_summary_for_place(_stop_name(stop), destination))
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
            and (env.departure_day is None or int(day.get("day") or index + 1) <= env.departure_day)
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
            isinstance(stop, dict) and _parse_hhmm(str(stop.get("time") or "")) is not None
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
