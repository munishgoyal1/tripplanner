"""Route-metric and stop-timing helpers for the trip-panel view-model.

Pure computation (no network, no UI): great-circle distances, coarse route
estimates, clock math, and per-stop timing enrichment. Split out of
``trip_view`` (tech-debt #7) as a leaf module; ``trip_view`` re-exports these
names so existing callers and tests are unaffected.
"""

from __future__ import annotations

import math
import re
from typing import Any

from tripplanner.tools.trip_common import MAX_GROUND_LEG_KM as MAX_GROUND_LEG_KM
from tripplanner.web.transport import _intercity_transfer_mode

_INTERCITY_SPEED_KMH = {
    "Flight": 650.0,
    "Train": 80.0,
    "Bus": 50.0,
    "Drive": 65.0,
}


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _route_stats_for_day(
    pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Estimate day route metrics from ordered pins.

    We avoid billed routing calls in this view-model. Distances are straight-
    line totals along the day path; durations are coarse estimates by likely
    local transfer mode.
    """
    coords: list[tuple[float, float]] = []
    for pid in pin_ids:
        p = pin_by_id.get(pid)
        if not p:
            continue
        lat, lng = p.get("lat"), p.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            coords.append((float(lat), float(lng)))

    return _route_stats_for_coords(coords)


def _route_stats_for_distance(
    distance: float, *, from_name: str = "", to_name: str = ""
) -> dict[str, Any]:
    if distance <= 1.5:
        mode, speed = "Walk", 4.5
    elif distance <= 20:
        mode, speed = "Taxi", 25.0
    else:
        mode, speed = "Taxi", 35.0

    duration_min = int(round((distance / speed) * 60)) if speed > 0 else 0
    distance_1 = round(distance, 1)
    result = {
        "distance_km": distance_1,
        "duration_min": duration_min,
        "mode": mode,
        "distance_display": f"{distance_1:.1f} km",
        "duration_display": _route_duration_display(duration_min),
    }
    if from_name and to_name:
        if mode == "Walk":
            result["detail"] = f"Walk from {from_name} to {to_name}."
        elif mode == "Metro":
            result["detail"] = (
                f"Take the Metro from near {from_name} toward {to_name}; "
                "walk to and from the nearest stations."
            )
        else:
            result["detail"] = f"Take a taxi from {from_name} to {to_name}."
    return result


def _route_duration_display(duration_min: int) -> str:
    if duration_min < 60:
        return f"{duration_min} min"
    hours, minutes = divmod(duration_min, 60)
    return f"{hours} hr" + (f" {minutes} min" if minutes else "")


def _stop_duration_display(duration_min: int) -> str:
    if duration_min < 60:
        return f"{duration_min} min"
    hours, minutes = divmod(duration_min, 60)
    unit = "hr" if hours == 1 else "hrs"
    return f"{hours} {unit}" + (f" {minutes} min" if minutes else "")


def _clock_minutes(value: Any) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?:\s*([ap]m))?\s*", str(value or ""), re.I)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    meridiem = (match.group(3) or "").lower()
    if minutes > 59 or hours > (12 if meridiem else 23):
        return None
    if meridiem:
        hours %= 12
        if meridiem == "pm":
            hours += 12
    return hours * 60 + minutes


def _clock_display(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _day_schedule(stops: list[dict[str, Any]], route: dict[str, Any]) -> dict[str, Any]:
    timed = [
        (index, minutes)
        for index, stop in enumerate(stops)
        if (minutes := _clock_minutes(stop.get("time"))) is not None
    ]
    travel_minutes = int(route.get("duration_min") or 0)
    if not timed:
        visit_minutes = sum(
            int(stop.get("duration_min") or 0)
            for stop in stops
            if stop.get("kind") != "hotel"
        )
        total = visit_minutes + travel_minutes
        return {
            "start": "",
            "end": "",
            "duration_min": total,
            "duration_display": _route_duration_display(total),
            "travel_duration_min": travel_minutes,
            "travel_duration_display": _route_duration_display(travel_minutes),
            "estimated": True,
        }

    first_index, first_time = timed[0]
    last_index, last_time = timed[-1]
    start = first_time - int(
        (stops[first_index].get("travel_from_previous") or {}).get("duration_min") or 0
    )
    end = last_time
    if end < first_time:
        end += 24 * 60
    end += sum(
        int(stop.get("duration_min") or 0)
        for stop in stops[last_index:]
        if stop.get("kind") not in {"hotel", "flight", "transport"}
    )
    end += sum(
        int((stop.get("travel_from_previous") or {}).get("duration_min") or 0)
        for stop in stops[last_index + 1 :]
    )
    return {
        "start": _clock_display(start),
        "end": _clock_display(end),
        "duration_min": max(0, end - start),
        "duration_display": _route_duration_display(max(0, end - start)),
        "travel_duration_min": travel_minutes,
        "travel_duration_display": _route_duration_display(travel_minutes),
        "estimated": any(stop.get("kind") == "hotel" and not stop.get("time") for stop in stops),
    }


def _enrich_stop_timing(stops: list[dict[str, Any]]) -> None:
    for index, stop in enumerate(stops):
        arrival = _clock_minutes(stop.get("time"))
        if arrival is None:
            continue

        duration = int(stop.get("duration_min") or 0)
        if stop.get("kind") == "flight" and stop.get("arrival_time"):
            stop["departure_time"] = str(stop["arrival_time"])
        elif duration > 0 and stop.get("kind") not in {"hotel", "flight"}:
            stop["departure_time"] = _clock_display(arrival + duration)

        if index == 0:
            continue
        previous = stops[index - 1]
        previous_arrival = _clock_minutes(previous.get("time"))
        if previous_arrival is None:
            continue
        previous_duration = int(previous.get("duration_min") or 0)
        if previous.get("kind") == "hotel":
            previous_duration = 0
        travel_minutes = int(
            (stop.get("travel_from_previous") or {}).get("duration_min") or 0
        )
        expected_arrival = previous_arrival + previous_duration + travel_minutes
        actual_arrival = arrival
        while actual_arrival < previous_arrival:
            actual_arrival += 24 * 60
        buffer_minutes = actual_arrival - expected_arrival
        stop["expected_arrival_time"] = _clock_display(expected_arrival)
        if buffer_minutes > 0:
            stop["buffer_before_min"] = buffer_minutes
            stop["buffer_before_display"] = _route_duration_display(buffer_minutes)
        elif buffer_minutes < 0:
            stop["timing_conflict_min"] = abs(buffer_minutes)
            stop["timing_conflict_display"] = _route_duration_display(abs(buffer_minutes))


def _enrich_drive_transfer_timing(
    stops: list[dict[str, Any]],
    place_coords_map: dict[str, tuple[float, float]],
    transport_preferences: dict[str, Any] | None = None,
) -> None:
    preferences = transport_preferences or {}
    max_continuous_min = int(preferences.get("max_continuous_drive_min") or 180)
    break_duration_min = int(preferences.get("road_break_duration_min") or 30)
    break_preferences = [
        str(value).strip()
        for value in preferences.get("road_break_preferences") or ["snack", "rest"]
        if str(value).strip()
    ]
    for index in range(1, len(stops) - 1):
        stop = stops[index]
        if _intercity_transfer_mode(
            str(stop.get("name") or ""), str(stop.get("kind") or "")
        ) != "Drive":
            continue

        previous = stops[index - 1]
        destination_index = next(
            (
                candidate_index
                for candidate_index in range(index + 1, len(stops))
                if stops[candidate_index].get("kind") == "hotel"
            ),
            -1,
        )
        if previous.get("kind") not in {"hotel", "origin"} or destination_index < 0:
            continue
        following = stops[destination_index]
        waypoints = [
            candidate
            for candidate in stops[index + 1 : destination_index]
            if candidate.get("kind") in {"attraction", "meal", "restaurant"}
        ]
        duration = stop.get("duration_min")
        duration_estimated = False
        if not isinstance(duration, (int, float)) or duration <= 0:
            route_stops = [previous, *waypoints, following]
            route_coords = [
                place_coords_map.get(str(candidate.get("name") or "").strip().lower())
                for candidate in route_stops
            ]
            if all(route_coords):
                distance = sum(
                    _haversine_km(route_coords[leg_index - 1], route_coords[leg_index])
                    for leg_index in range(1, len(route_coords))
                )
                speed = _INTERCITY_SPEED_KMH["Drive"]
                duration = max(1, int(round((distance / speed) * 60)))
                stop["duration_min"] = duration
                stop["duration_estimated"] = True
                duration_estimated = True

        route_stops = [previous, *waypoints, following]
        drive_legs: list[dict[str, Any]] = []
        for leg_index in range(1, len(route_stops)):
            leg_start = route_stops[leg_index - 1]
            leg_end = route_stops[leg_index]
            start_coords = place_coords_map.get(
                str(leg_start.get("name") or "").strip().lower()
            )
            end_coords = place_coords_map.get(
                str(leg_end.get("name") or "").strip().lower()
            )
            if not start_coords or not end_coords:
                continue
            distance = _haversine_km(start_coords, end_coords)
            duration_min = int(round((distance / _INTERCITY_SPEED_KMH["Drive"]) * 60))
            leg = {
                "distance_km": round(distance, 1),
                "duration_min": duration_min,
                "mode": "Drive",
                "distance_display": f"{distance:.1f} km",
                "duration_display": _route_duration_display(duration_min),
            }
            leg["detail"] = (
                f"Continue in the same vehicle from {leg_start['name']} to {leg_end['name']}."
            )
            leg_end["travel_from_previous"] = leg
            drive_legs.append(leg)

        _apply_saved_transfer_metrics(
            drive_legs,
            {
                metric: float(stop[metric])
                for metric in ("distance_km", "duration_min")
                if isinstance(stop.get(metric), (int, float)) and stop[metric] > 0
            },
        )

        duration = stop.get("duration_min")
        if isinstance(duration, (int, float)) and duration > 0:
            break_count = max(0, (int(duration) - 1) // max(60, max_continuous_min))
            if break_count:
                if duration_estimated:
                    duration = int(duration) + break_count * max(10, break_duration_min)
                    stop["duration_min"] = duration
                break_kind = "/".join(break_preferences[:2]) or "rest"
                break_text = (
                    f"one {break_duration_min} min {break_kind} break"
                    if break_count == 1
                    else f"{break_count} x {break_duration_min} min {break_kind} breaks"
                )
                stop["operational_time_display"] = (
                    f"{_stop_duration_display(int(duration))} drive incl. {break_text}"
                )

        scenic_names = [
            str(waypoint.get("name") or "").strip()
            for waypoint in waypoints
            if waypoint.get("kind") == "attraction"
            and str(waypoint.get("name") or "").strip()
        ]
        meal_names = [
            str(waypoint.get("name") or "").strip()
            for waypoint in waypoints
            if waypoint.get("kind") in {"meal", "restaurant"}
            and str(waypoint.get("name") or "").strip()
        ]
        guidance = [
            "Keep the same taxi or self-drive vehicle through the route stops "
            f"and continue to {following['name']}."
        ]
        if scenic_names:
            guidance.append(
                "Use " + ", ".join(scenic_names) + " as short scenic breaks on the way."
            )
        if meal_names:
            guidance.append("The planned meal stop is " + ", ".join(meal_names) + ".")
        elif isinstance(duration, (int, float)) and duration >= 240:
            guidance.append(
                "Plan a lunch or substantial snack stop on the way; add a preferred venue "
                "as a separate meal stop when timing or dietary needs matter."
            )
        existing_insight = str(stop.get("insight") or "").strip()
        stop["insight"] = " ".join(
            [text for text in [existing_insight, *guidance] if text]
        )

        if (
            not stop.get("time")
            and previous.get("kind") == "hotel"
            and _clock_minutes(previous.get("time")) is not None
        ):
            stop["time"] = str(previous["time"])
            stop["time_estimated"] = True


def _apply_hotel_endpoint_times(
    stops: list[dict[str, Any]], schedule: dict[str, Any]
) -> None:
    if not stops:
        return
    endpoints = ((stops[0], schedule.get("start")), (stops[-1], schedule.get("end")))
    for stop, endpoint_time in endpoints:
        if (
            stop is stops[-1]
            and len(stops) > 1
            and stops[-2].get("kind") == "airport"
            and not (stop.get("travel_from_previous") or {}).get("duration_min")
        ):
            continue
        if stop.get("kind") == "hotel" and not stop.get("time") and endpoint_time:
            stop["time"] = str(endpoint_time)
            stop["time_estimated"] = True


def _route_stats_for_coords(coords: list[tuple[float, float]]) -> dict[str, Any]:
    legs = [
        _route_stats_for_distance(_haversine_km(coords[i - 1], coords[i]))
        for i in range(1, len(coords))
    ]
    if not legs:
        return _route_stats_for_distance(0.0)
    distance = round(sum(float(leg["distance_km"]) for leg in legs), 1)
    duration = sum(int(leg["duration_min"]) for leg in legs)
    modes = list(dict.fromkeys(str(leg["mode"]) for leg in legs))
    mode = modes[0] if len(modes) == 1 else " + ".join(modes)
    return {
        "distance_km": distance,
        "duration_min": duration,
        "mode": mode,
        "distance_display": f"{distance:.1f} km",
        "duration_display": _route_duration_display(duration),
    }


def _apply_saved_transfer_metrics(
    legs: list[dict[str, Any]], transfer_metrics: dict[str, float] | None
) -> None:
    if not legs:
        return
    saved_distance = (transfer_metrics or {}).get("distance_km")
    saved_duration = (transfer_metrics or {}).get("duration_min")
    if not isinstance(saved_distance, (int, float)) and not isinstance(
        saved_duration, (int, float)
    ):
        return

    weights = [max(float(leg["distance_km"]), 0.001) for leg in legs]
    weight_total = sum(weights)
    for metric_name, saved_total in (
        ("distance_km", saved_distance),
        ("duration_min", saved_duration),
    ):
        if not isinstance(saved_total, (int, float)) or saved_total <= 0:
            continue
        allocated = 0.0
        for index, (leg, weight) in enumerate(zip(legs, weights)):
            if index == len(legs) - 1:
                value = saved_total - allocated
            else:
                value = saved_total * weight / weight_total
                value = round(value, 1) if metric_name == "distance_km" else round(value)
                allocated += value
            leg[metric_name] = round(value, 1) if metric_name == "distance_km" else int(value)
    for leg in legs:
        leg["distance_display"] = f'{leg["distance_km"]:.1f} km'
        leg["duration_display"] = _route_duration_display(leg["duration_min"])
        leg["metrics_source"] = "saved"
