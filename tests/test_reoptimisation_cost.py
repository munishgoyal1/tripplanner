"""How long a whole-trip re-optimisation would actually take.

Not a test of behaviour; a measurement to answer "how slow?" with a number.
Runs a bounded local search over the real shape of a trip: every movable stop
tried against every legal slot on every day, scored on cached facts alone.
"""

from __future__ import annotations

import time

from tripplanner.tools import trip_common, trip_effort, trip_guard

_PLACES = {
    f"Place {index}": (48.85 + index * 0.004, 2.29 + index * 0.006) for index in range(24)
}


def _summary(name: str, _destination: str = "") -> dict[str, object]:
    coords = _PLACES.get(name)
    if not coords:
        return {}
    return {
        "name": name,
        "lat": coords[0],
        "lng": coords[1],
        "business_status": "OPERATIONAL",
        "weekday_descriptions": [
            f"{day}: 9:00 AM - 6:00 PM"
            for day in (
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            )
        ],
    }


def _trip(days: int, per_day: int) -> dict[str, object]:
    itinerary = []
    counter = 0
    for day in range(1, days + 1):
        stops = []
        for slot in range(per_day):
            stops.append(
                {
                    "name": f"Place {counter % len(_PLACES)}",
                    "kind": "attraction",
                    "time": f"{9 + slot * 2:02d}:00",
                    "duration_min": 90,
                }
            )
            counter += 1
        itinerary.append({"day": day, "stops": stops})
    return {
        "origin": "Bengaluru",
        "destination": "Paris",
        "departure_date": "2026-09-07",
        "day_wise_itinerary": itinerary,
    }


def test_measure_whole_trip_reoptimisation(monkeypatch) -> None:
    for module in (trip_common, trip_guard, trip_effort):
        monkeypatch.setattr(module, "_summary_for_place", _summary, raising=False)

    for days, per_day in ((6, 4), (10, 5), (14, 6)):
        plan = _trip(days, per_day)
        movable = [
            (day, index, stop)
            for day, _entry, stops in trip_guard.days_of(plan)
            for index, stop in enumerate(stops)
        ]

        started = time.perf_counter()
        candidates = 0
        for _day, _index, stop in movable:
            placement, rejections = trip_guard.choose_placement(
                plan, stop["name"], "attraction", duration_min=90
            )
            candidates += 1 + len(rejections)
        placement_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        for _ in range(len(movable)):
            trip_effort.day_efforts(plan)
            trip_guard.validate_plan(plan)
        score_ms = (time.perf_counter() - started) * 1000

        print(
            f"{days:>3} days x {per_day} stops = {len(movable):>3} movable | "
            f"placement search {placement_ms:8.1f} ms over {candidates:>4} slots | "
            f"rescore+revalidate {score_ms:8.1f} ms"
        )
