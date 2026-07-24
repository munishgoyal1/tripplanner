from __future__ import annotations

from typing import Any

from tripplanner.tools import trip_planner
from tripplanner.web import trip_view


def build_view(focus: dict[str, str] | None = None) -> dict[str, Any]:
    return trip_view.build_view(trip_planner.load_active_trip_dict(), focus)


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
        result = trip_planner.add_selection(kind, {"name": name}, preferred_day=day)
    trip = result.get("trip") or trip_planner.load_active_trip_dict()
    focus_kind = "hotel" if kind == "hotel" else "attraction"
    view = trip_view.build_view(trip, {"kind": focus_kind, "name": name})
    if result.get("alerts"):
        view["alerts"] = result["alerts"]
    return {
        "ok": result.get("ok", False),
        "alerts": result.get("alerts", []),
        "view": view,
        "placement": result.get("placement"),
        "placements": result.get("placements", []),
    }


def deselect(kind: str, name: str) -> dict[str, Any]:
    ok = trip_planner.remove_selection(kind, name)
    alerts = [f"Removed {name} and refreshed the itinerary."] if ok else []
    return {"ok": ok, "alerts": alerts, "view": build_view()}


def set_stop_booked(day: int, name: str, booked: bool) -> dict[str, Any]:
    ok = trip_planner.set_stop_booked(day, name, booked)
    return {"ok": ok, "itinerary": build_itinerary()}


def switch_trip(trip_id: str) -> dict[str, Any]:
    plan = trip_planner.switch_active_trip(trip_id)
    if plan is None:
        return {"ok": False, "error": "trip not found"}
    return {"ok": True, "view": trip_view.build_view(plan, None)}
