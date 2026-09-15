"""Reconcile reported stay dates without manufacturing overnight coverage."""

from copy import deepcopy
from datetime import date


def reconcile_stay(plan, item_id, targets):
    from tripplanner.tools.trip_guard import day_dates

    selected = next((stop for path, stop in targets if path[0] == "selected_hotels"), None)
    if selected is None:
        selected = next((stop for _, stop in targets), {})
    selected = deepcopy(selected)
    try:
        start = date.fromisoformat(selected.get("checkin", ""))
        end = date.fromisoformat(selected.get("checkout", ""))
    except (ValueError, TypeError):
        return ["Confirm check-in and checkout dates before reconciling hotel nights."]
    dates = day_dates(plan)
    linked = {id(stop) for path, stop in targets if path[0] == "day_wise_itinerary"}
    warnings = []
    for index, day in enumerate(plan.get("day_wise_itinerary") or []):
        if not isinstance(day, dict):
            continue
        text = dates.get(day.get("day", index + 1), day.get("date", ""))
        try:
            night = date.fromisoformat(text)
        except (ValueError, TypeError):
            continue
        stops = day.get("stops") or []
        affected = [
            stop
            for stop in stops
            if isinstance(stop, dict)
            and (
                id(stop) in linked
                or (
                    stop.get("uncovered_booking_item_id") == item_id
                    and stop.get("name") == "Hotel TBD"
                    and not stop.get("booking_item_id")
                )
            )
        ]
        for stop in affected:
            if start <= night < end:
                if stop.get("uncovered_booking_item_id"):
                    timing = {key: stop[key] for key in ("time", "duration_min") if key in stop}
                    stop.clear()
                    stop.update(deepcopy(selected), kind="hotel", **timing)
                stop.pop("uncovered_booking_item_id", None)
                if stop.pop("stay_role", None) == "checkout":
                    stop.pop("note", None)
            elif night == end and id(stop) in linked and stop is affected[0]:
                stop["stay_role"] = "checkout"
                stop.pop("time", None)
                stop.pop("duration_min", None)
                stop["note"] = (
                    "Checkout from the reported stay; this booking does not cover tonight."
                )
            else:
                city = stop.get("city") or selected.get("city")
                stop.clear()
                stop.update(
                    kind="hotel",
                    name="Hotel TBD",
                    booked=False,
                    uncovered_booking_item_id=item_id,
                    note=f"No stay booked for {text} after the reported hotel date change.",
                )
                if city:
                    stop["city"] = city
        # A checkout anchor describes the morning, never the following night.
        needs_night = text < str(plan.get("return_date") or "")
        hotels = [s for s in stops if isinstance(s, dict) and s.get("kind") == "hotel"]
        if (
            affected
            and night == end
            and needs_night
            and hotels
            and hotels[-1].get("stay_role") == "checkout"
        ):
            stops.append(
                {
                    "kind": "hotel",
                    "name": "Hotel TBD",
                    "booked": False,
                    "uncovered_booking_item_id": item_id,
                    "note": f"No stay booked for {text} after checkout.",
                }
            )
        if any(
            s.get("uncovered_booking_item_id") == item_id and s.get("name") == "Hotel TBD"
            for s in stops
            if isinstance(s, dict)
        ):
            warnings.append(
                f"Hotel night {text} is uncovered after the booking date change; select a stay."
            )
        elif start <= night < end and not affected:
            warnings.append(
                f"Reported hotel covers {text}, but its itinerary anchor is not linked. Review this night's stay and transfers; other stays were preserved."
            )
    return warnings
