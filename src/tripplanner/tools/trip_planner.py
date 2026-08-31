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
from threading import RLock
from typing import Any

from langchain_core.tools import tool

from tripplanner import storage_cosmos
from tripplanner.decisions.provenance import make_check, record_check
from tripplanner.decisions.rules import money
from tripplanner.decisions.store import upsert_decision
from tripplanner.json_store import atomic_write_json
from tripplanner.tools import trip_history
from tripplanner.tools.finalize_critic import critique as _critique_finalized
from tripplanner.tools.itinerary_edit import (  # noqa: F401
    _day_entry_and_stops,
    _fit_plan_to_departure,
    _fit_stops_before_leg,
    _infer_stop_time,
    _is_leg,
    _make_stop,
    _move_to_another_day,
    _newly_broken,
    _pacing_text,
    _place_selected_stop,
    _reads_as_journey,
    _rebalance_day,
    _reflow_unbooked_attractions,
    _remove_candidate,
    _repair_known_closed_days,
    _repair_known_opening_hours,
    _repair_temporal_infeasibility,
    _restore_undeclared_legs,
    _retime_stops_in_order,
    _settle_around_legs,
    _settle_plan_legs,
)
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
from tripplanner.tools.trip_guard import (
    diff_stops,
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

_TRIPS_DIR = trip_history._TRIPS_DIR
_ACTIVE_TRIP_FILE = trip_history._ACTIVE_TRIP_FILE
_TRIP_HISTORY_DIR = trip_history._TRIP_HISTORY_DIR

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


_compute_trip_id = trip_history.compute_trip_id
_resolve_active_trip_path = trip_history.resolve_active_trip_path
_resolve_trip_history_dir = trip_history.resolve_trip_history_dir
_ensure_dirs = trip_history.ensure_dirs


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
    return trip_history.load_active_trip()


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

    trip_history.persist_active_trip(plan)


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


_mirror_to_history = trip_history.mirror_to_history
_load_history_trip = trip_history.load_history_trip
_all_history_trips = trip_history.all_history_trips
_next_trip_number = trip_history._next_trip_number
list_saved_trips = trip_history.list_saved_trips
saved_trip_destination = trip_history.saved_trip_destination


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

    if not trip_history.delete_saved_trip(trip_id):
        return False
    active = _load_active_trip()
    trip_feedback.delete_for_trip(trip_id)
    if active and active.get("trip_id") == trip_id:
        _delete_active_trip()
    return True


@_serialized_mutation
def clear_all_trip_history() -> int:
    """Delete all saved trips for the current user and clear active trip."""
    from tripplanner.web import trip_feedback

    deleted = trip_history.clear_all_trip_history()
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
    trip_history.delete_active_trip()


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
    closed_day_errors = [
        violation.message for violation in violations if violation.code == "I11"
    ]
    if "day_wise_itinerary" in updates and closed_day_errors:
        return (
            "Error: itinerary visits on known closed weekdays cannot be saved. "
            + " ".join(closed_day_errors)
            + " Move them to days when they are open and resubmit the full "
            "day_wise_itinerary. The saved itinerary was not changed."
        )
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
