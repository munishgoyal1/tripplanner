"""Save-time repairs for itinerary facts that must follow from the day's journeys.

Pure over a plan dict. Two repairs are safe to make without asking the agent:

* A stay listed *after* the day's first departing journey, when it is the stay
  being left (a check-out, a "start from hotel", or the morning hotel again
  before any return journey). It moves to just before that journey. Measured on
  the corpus: 47 of 178 trips listed the morning hotel after the train, drive or
  ferry that had already left it.
* A selected stay whose checkout falls after the last planned day, when that
  day ends with the journey home. Checkout becomes that day, so no night is paid
  after the traveller has gone (20 of 178 corpus trips).

Times that run backwards are *not* re-sorted here: sorting a day whose times are
wrong produces a different wrong order. ``out_of_order`` reports them so the
completion gate can hand the exact conflict back to the agent.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_MOVE_KINDS = frozenset({"transport", "flight", "train", "drive", "transfer", "ferry"})
_MOVE_NAME = re.compile(r"(?:drive|train|flight|transfer|shinkansen|ferry|bus)\b", re.IGNORECASE)
_LEAVING_NOTE = re.compile(r"check[\s-]?out|\bstart\b|\bdepart", re.IGNORECASE)
_RETURN_NOTE = re.compile(r"\breturn|\bback\b|\brest\b|\bovernight|\bunwind", re.IGNORECASE)


def _stops(day: dict[str, Any]) -> list[Any]:
    stops = day.get("stops")
    return stops if isinstance(stops, list) else []


def _kind(stop: Any) -> str:
    return str(stop.get("kind") or "").strip().lower() if isinstance(stop, dict) else ""


def _name(stop: Any) -> str:
    return str(stop.get("name") or "").strip() if isinstance(stop, dict) else ""


def minutes(value: Any) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def is_move(stop: Any) -> bool:
    return _kind(stop) in _MOVE_KINDS or bool(_MOVE_NAME.match(_name(stop)))


def _misplaced_stays(stops: list[Any], prior_stay: str = "") -> list[int]:
    """Indexes of stays listed after the first departure although they are being left.

    The stay being left is the one the day explicitly starts from, or else the
    previous night's. An arrival check-in is never misplaced, and a morning
    hotel reached again after a later journey is a day trip's return.
    """
    first = next((index for index, stop in enumerate(stops) if is_move(stop)), None)
    if first is None:
        return []
    started_at = {_name(stop).casefold() for stop in stops[:first] if _kind(stop) == "hotel"}
    leaving = started_at | ({prior_stay.casefold()} if prior_stay else set())
    misplaced: list[int] = []
    for index in range(first + 1, len(stops)):
        stop = stops[index]
        if _kind(stop) != "hotel":
            continue
        note = str(stop.get("note") or "")
        if _LEAVING_NOTE.search(note):
            misplaced.append(index)
            continue
        name = _name(stop).casefold()
        if name not in leaving or _RETURN_NOTE.search(note) or index == len(stops) - 1:
            continue
        returned = any(is_move(other) for other in stops[first + 1 : index])
        if name in started_at and returned:
            continue  # a day trip back to the hotel it set out from
        misplaced.append(index)
    return misplaced


def _days_with_prior_stay(plan: dict[str, Any]):
    prior = ""
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        yield day, prior
        hotels = [_name(stop) for stop in _stops(day) if _kind(stop) == "hotel"]
        if hotels:
            prior = hotels[-1]


def misplaced_stays(plan: dict[str, Any]) -> list[str]:
    """Human-readable descriptions of stays listed after the journey that left them."""
    found = []
    for day, prior in _days_with_prior_stay(plan):
        stops = _stops(day)
        first = next((index for index, stop in enumerate(stops) if is_move(stop)), None)
        for index in _misplaced_stays(stops, prior):
            stop = stops[index]
            found.append(
                f"Day {day.get('day')}: {_name(stop)} ({stop.get('note') or 'stay'})"
                f" after {_name(stops[first])}"
            )
    return found


def move_stays_before_departure(plan: dict[str, Any]) -> bool:
    """Move each misplaced stay to just before the day's first departing journey."""
    changed = False
    for day, prior in list(_days_with_prior_stay(plan)):
        stops = _stops(day)
        misplaced = _misplaced_stays(stops, prior)
        if not misplaced:
            continue
        first = next(index for index, stop in enumerate(stops) if is_move(stop))
        departure = minutes(stops[first].get("time")) if isinstance(stops[first], dict) else None
        moved = [stops[index] for index in misplaced]
        for stop in moved:
            stop_time = minutes(stop.get("time"))
            if departure is not None and stop_time is not None and stop_time > departure:
                stop.pop("time", None)  # a checkout cannot happen after leaving
        kept = [stop for index, stop in enumerate(stops) if index not in set(misplaced)]
        day["stops"] = kept[:first] + moved + kept[first:]
        changed = True
    return changed


def out_of_order(plan: dict[str, Any]) -> list[str]:
    """Timed stops listed after a later-timed stop on the same day."""
    found = []
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        latest, latest_label = -1, ""
        for stop in _stops(day):
            if not isinstance(stop, dict):
                continue
            value = minutes(stop.get("time"))
            if value is None:
                continue
            if value < latest:
                found.append(
                    f"Day {day.get('day')}: {_name(stop)} at {stop.get('time')} is listed after"
                    f" {latest_label}"
                )
            else:
                latest, latest_label = value, f"{_name(stop)} at {stop.get('time')}"
    return found


def _last_day(plan: dict[str, Any]) -> tuple[date, dict[str, Any]] | None:
    dated = []
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        try:
            dated.append((date.fromisoformat(str(day.get("date"))), day))
        except ValueError:
            continue
    return max(dated, key=lambda item: item[0]) if dated else None


def unused_nights(plan: dict[str, Any]) -> list[str]:
    """Selected stays that check out after the traveller's journey home."""
    last = _last_day(plan)
    if last is None:
        return []
    last_date, day = last
    stops = [stop for stop in _stops(day) if isinstance(stop, dict)]
    if not stops or not is_move(stops[-1]):
        return []
    found = []
    for hotel in plan.get("selected_hotels") or []:
        if not isinstance(hotel, dict):
            continue
        try:
            checkout = date.fromisoformat(str(hotel.get("checkout")))
        except ValueError:
            continue
        if checkout > last_date:
            found.append(f"{hotel.get('name')} checks out {checkout} after leaving on {last_date}")
    return found


def trim_unused_nights(plan: dict[str, Any]) -> bool:
    """Check out on the day the trip ends with the journey home."""
    if not unused_nights(plan):
        return False
    last_date, _day = _last_day(plan)  # type: ignore[misc]
    changed = False
    for hotel in plan.get("selected_hotels") or []:
        if not isinstance(hotel, dict):
            continue
        try:
            checkin = date.fromisoformat(str(hotel.get("checkin")))
            checkout = date.fromisoformat(str(hotel.get("checkout")))
        except ValueError:
            continue
        if checkout <= last_date or checkin >= last_date:
            continue
        hotel["checkout"] = last_date.isoformat()
        nights = (last_date - checkin).days
        try:
            per_night = float(hotel.get("price_per_night"))
        except (TypeError, ValueError):
            per_night = 0.0
        if per_night > 0 and hotel.get("total_price") not in (None, ""):
            hotel["total_price"] = round(per_night * nights, 2)
        if "nights" in hotel:
            hotel["nights"] = nights
        changed = True
    return changed


def normalize(plan: dict[str, Any]) -> bool:
    """Apply every safe save-time repair; True when the plan changed."""
    moved = move_stays_before_departure(plan)
    trimmed = trim_unused_nights(plan)
    return moved or trimmed
