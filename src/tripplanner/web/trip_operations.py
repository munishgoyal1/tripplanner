from __future__ import annotations

from typing import Any

from tripplanner.tools import trip_planner
from tripplanner.web import trip_view
from tripplanner.web.workspace_payload import build_workspace_payload


def _stop_name(stop: Any) -> str:
    return str(stop.get("name") or "").strip() if isinstance(stop, dict) else str(stop).strip()


def _placements_for_name(trip: dict[str, Any], name: str) -> list[dict[str, Any]]:
    target = name.strip().lower()
    placements: list[dict[str, Any]] = []
    for day_index, entry in enumerate(trip.get("day_wise_itinerary") or []):
        if not isinstance(entry, dict):
            continue
        day = int(entry.get("day") or day_index + 1)
        for stop_index, stop in enumerate(entry.get("stops") or []):
            if _stop_name(stop).lower() == target:
                placements.append({"day": day, "stop": stop_index + 1, "name": name})
    return placements


def _occurrence_days(trip: dict[str, Any], name: str) -> list[int]:
    return [placement["day"] for placement in _placements_for_name(trip, name)]


def _format_days(days: list[int]) -> str:
    labels = [f"Day {day}" for day in sorted(set(days))]
    if len(labels) < 2:
        return labels[0] if labels else "the trip"
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def build_view(focus: dict[str, str] | None = None) -> dict[str, Any]:
    return trip_view.build_view(trip_planner.load_active_trip_dict(), focus)


def warm_guide() -> None:
    """Background warm of the destination-guide dataset for the active trip."""
    trip_view.warm_guide(trip_planner.load_active_trip_dict())


def warm_view_items() -> None:
    """Background warm of the trip-panel gallery for the active trip."""
    trip_view.warm_view_items(trip_planner.load_active_trip_dict())


def paged_places(
    *,
    city: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    cursor: str | None = None,
    limit: int = 6,
    focus_name: str | None = None,
    focus_kind: str | None = None,
) -> dict[str, Any]:
    return trip_view.paged_places(
        trip_planner.load_active_trip_dict(),
        city=city,
        kind=kind,
        query=query,
        cursor=cursor,
        limit=limit,
        focus_name=focus_name,
        focus_kind=focus_kind,
    )


def build_map() -> dict[str, Any]:
    return trip_view.build_map_view(trip_planner.load_active_trip_dict())


def build_itinerary() -> dict[str, Any]:
    return trip_view.build_itinerary(trip_planner.load_active_trip_dict())


def select(
    kind: str,
    name: str,
    *,
    start_day: int | None = None,
    end_day: int | None = None,
    day: int | None = None,
    source_day: int | None = None,
    source_stop: int | None = None,
    replace_stay: bool = False,
) -> dict[str, Any]:
    if kind == "hotel" and (start_day is not None or end_day is not None):
        result = trip_planner.add_hotel_stay(
            name,
            start_day=start_day,
            end_day=end_day,
            replace_existing=replace_stay,
        )
    else:
        result = trip_planner.add_selection(
            kind,
            {"name": name},
            preferred_day=day,
            source_day=source_day,
            source_stop=source_stop,
        )
    trip = result.get("trip") or trip_planner.load_active_trip_dict()
    placement = result.get("placement")
    placements = result.get("placements", [])
    final_placements = _placements_for_name(trip, name) if result.get("ok") else []
    if kind != "hotel" and final_placements:
        if day is None:
            placement = final_placements[0]
        elif placement:
            placement = next(
                (candidate for candidate in final_placements if candidate["day"] == day),
                placement,
            )
    affected_days = [
        int(item["day"])
        for item in ([placement] if placement else placements)
        if isinstance(item, dict) and isinstance(item.get("day"), int)
    ]
    alerts = list(result.get("alerts", []))
    if result.get("ok") and affected_days:
        action = "Moved" if source_day is not None else "Added"
        if kind == "hotel":
            action = "Updated stay at"
            primary = f"{action} {name} for {_format_days(affected_days)}."
        else:
            primary = f"{action} {name} to {_format_days(affected_days)}."
        alerts = [primary, *alerts]
    focus_kind = "hotel" if kind == "hotel" else "attraction"
    view = trip_view.build_view(trip, {"kind": focus_kind, "name": name})
    if alerts:
        view["alerts"] = alerts
    planner_review = trip_planner.assess_itinerary_change(
        trip,
        action="moved" if source_day is not None else "added",
        name=name,
        days=affected_days,
    ) if result.get("ok") else None
    return {
        "ok": result.get("ok", False),
        "alerts": alerts,
        "view": view,
        "placement": placement,
        "placements": placements,
        "planner_review": planner_review,
    }


def deselect(
    kind: str,
    name: str,
    *,
    day: int | None = None,
    stop: int | None = None,
    all_occurrences: bool = True,
) -> dict[str, Any]:
    before = trip_planner.load_active_trip_dict()
    affected_days = [day] if day is not None else _occurrence_days(before, name)
    ok = trip_planner.remove_selection(
        kind,
        name,
        day=day,
        stop=stop,
        all_occurrences=all_occurrences,
    )
    if not ok:
        alerts: list[str] = []
    else:
        alerts = [f"Removed {name} from {_format_days(affected_days)}."]
    trip = trip_planner.load_active_trip_dict()
    planner_review = trip_planner.assess_itinerary_change(
        trip,
        action="removed",
        name=name,
        days=affected_days,
    ) if ok else None
    focus_kind = "hotel" if kind == "hotel" else "attraction"
    return {
        "ok": ok,
        "alerts": alerts,
        "view": build_view({"kind": focus_kind, "name": name}),
        "planner_review": planner_review,
    }


def set_stop_booked(day: int, name: str, booked: bool) -> dict[str, Any]:
    ok = trip_planner.set_stop_booked(day, name, booked)
    return {"ok": ok, "itinerary": build_itinerary()}


def override_decision(
    decision_id: str,
    option_id: str | None,
    *,
    expected_updated_at: str = "",
) -> dict[str, Any]:
    """Overrule a recorded comparison, or undo that overrule.

    Returns the whole trip in one response so the workspace takes a single
    coherent update rather than re-fetching each panel.
    """
    outcome = trip_planner.apply_decision_override(
        decision_id, option_id, expected_updated_at=expected_updated_at
    )
    plan = trip_planner.load_active_trip_dict()
    return {
        **outcome,
        "view": trip_view.build_view(plan, None),
        "itinerary": trip_view.build_itinerary(plan),
    }


def activate_trip(trip_id: str) -> Any:
    """Flip the active trip. Kept minimal so the workspace lock is held briefly."""
    return trip_planner.switch_active_trip(trip_id)


def workspace_payload(plan: Any) -> dict[str, Any]:
    # One payload for every panel. The plan is already loaded here, so the map
    # and itinerary cost no extra reads and all three panels swap together
    # instead of each fetching its own copy and settling one after another.
    return build_workspace_payload(plan)


def switch_trip(trip_id: str) -> dict[str, Any]:
    plan = activate_trip(trip_id)
    if plan is None:
        return {"ok": False, "error": "trip not found"}
    return workspace_payload(plan)
