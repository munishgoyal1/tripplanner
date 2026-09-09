"""Build an .ics (iCalendar) export of the active trip plan.

Pure-Python, no third-party dependency. Generates one VEVENT per:
  * outbound + return flight (selected_flights)
  * hotel stay (selected_hotels) — multi-day all-day event
  * each timed stop in day_wise_itinerary — a real timed event with its
    address, so the day shows up natively in a calendar app with reminders,
    not as one vague all-day block
  * any stops in a day that carry no time — one all-day event per day
    listing them, so nothing silently disappears

Times are best-effort: when no explicit time is present anywhere in a day we
fall back to a single all-day event for that day. Cancel-safe: an empty plan
yields an empty (but still valid) calendar so the export button never breaks.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

_PRODID = "-//tripplanner//Trip Planner//EN"
_CRLF = "\r\n"
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def _escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    """Fold long lines at 75 octets per RFC 5545 §3.1."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts = []
    while line:
        chunk = line[:74]
        parts.append(chunk)
        line = line[74:]
        if line:
            line = " " + line
    return _CRLF.join(parts)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fmt_dt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def _fmt_dt_utc(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _fmt_dt_floating(dt: datetime) -> str:
    """No trailing 'Z' and no TZID.

    We do not know the destination's IANA timezone here, so a real DTSTART
    UTC offset would be a guess dressed up as precision. RFC 5545 floating
    time is the honest choice: the wall-clock time the itinerary means,
    interpreted by whichever calendar the traveller is looking at.
    """
    return dt.strftime("%Y%m%dT%H%M%S")


def _vevent(
    *,
    uid: str,
    summary: str,
    start: date,
    end: date | None = None,
    description: str = "",
    location: str = "",
    all_day: bool = True,
    start_time: str = "",
    duration_min: int = 60,
) -> list[str]:
    now = datetime.now(timezone.utc)
    lines = ["BEGIN:VEVENT"]
    lines.append(f"UID:{uid}")
    lines.append(f"DTSTAMP:{_fmt_dt_utc(now)}")
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_dt_date(start)}")
        # iCal all-day end is exclusive — bump by 1 day.
        actual_end = (end or start) + timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{_fmt_dt_date(actual_end)}")
    else:
        match = _TIME_RE.search(start_time or "")
        hour, minute = (int(match.group(1)), int(match.group(2))) if match else (9, 0)
        start_dt = datetime.combine(start, datetime.min.time()).replace(hour=hour, minute=minute)
        end_dt = start_dt + timedelta(minutes=max(int(duration_min or 60), 15))
        lines.append(f"DTSTART:{_fmt_dt_floating(start_dt)}")
        lines.append(f"DTEND:{_fmt_dt_floating(end_dt)}")
    lines.append(f"SUMMARY:{_escape(summary)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    lines.append("END:VEVENT")
    return [_fold(line) for line in lines]


_KIND_EMOJI = {
    "attraction": "\U0001f4cd",
    "meal": "\U0001f37d️",
    "restaurant": "\U0001f37d️",
    "transport": "\U0001f697",
    "flight": "✈️",
}


def _flight_label(flight: Any) -> str:
    if isinstance(flight, str):
        return flight.strip()[:120] or "Flight"
    if not isinstance(flight, dict):
        return "Flight"
    parts: list[str] = []
    for key in ("airline", "carrier", "flight_number"):
        v = flight.get(key)
        if v:
            parts.append(str(v))
    if flight.get("from") and flight.get("to"):
        parts.append(f"{flight['from']} \u2192 {flight['to']}")
    elif flight.get("route"):
        parts.append(str(flight["route"]))
    return " ".join(parts) or "Flight"


def _hotel_label(hotel: Any) -> str:
    if isinstance(hotel, str):
        return hotel.strip()[:120] or "Hotel"
    if not isinstance(hotel, dict):
        return "Hotel"
    for key in ("name", "hotel_name", "title"):
        v = hotel.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    return "Hotel"


def _activity_label(activity: Any) -> str:
    if isinstance(activity, str):
        return activity.strip()[:120] or "Activity"
    if not isinstance(activity, dict):
        return "Activity"
    for key in ("name", "title", "activity"):
        v = activity.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    return "Activity"


def build_ics(plan: dict[str, Any] | None) -> str:
    """Build a fully-formed .ics document string for ``plan``.

    Empty/missing plan returns an empty but valid VCALENDAR — callers can
    serve the bytes unconditionally.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    if plan:
        dep = _parse_date(plan.get("departure_date"))
        ret = _parse_date(plan.get("return_date"))
        destination = str(plan.get("destination") or "").strip()
        trip_id = str(plan.get("created_at") or uuid.uuid4().hex).replace(":", "")

        # Flights — outbound on dep date, return on ret date.
        flights = plan.get("selected_flights") or []
        for i, f in enumerate(flights):
            label = _flight_label(f)
            flight_date = dep if i == 0 else (ret or dep)
            if not flight_date:
                continue
            lines.extend(
                _vevent(
                    uid=f"flight-{i}-{trip_id}@tripplanner",
                    summary=f"\u2708\ufe0f {label}",
                    start=flight_date,
                    description=str(f) if not isinstance(f, str) else f,
                )
            )

        # Hotels — span full trip range.
        hotels = plan.get("selected_hotels") or []
        for i, h in enumerate(hotels):
            label = _hotel_label(h)
            if not dep:
                continue
            check_in = _parse_date((h or {}).get("check_in")) or dep
            check_out = _parse_date((h or {}).get("check_out")) or ret or dep
            lines.extend(
                _vevent(
                    uid=f"hotel-{i}-{trip_id}@tripplanner",
                    summary=f"\U0001f3e8 {label}",
                    start=check_in,
                    end=check_out,
                    location=destination,
                )
            )

        # Day-wise itinerary — one real timed event per stop that has a time,
        # so the day shows up as an actual schedule rather than one all-day
        # block. A stop with no time, and any day with none at all, falls
        # back to a single all-day event so nothing goes missing.
        from tripplanner.web import places_cache

        itinerary = plan.get("day_wise_itinerary") or []
        for entry in itinerary:
            if not isinstance(entry, dict):
                continue
            day_offset = entry.get("day")
            day_date = _parse_date(entry.get("date"))
            if day_date is None and isinstance(day_offset, int) and dep:
                day_date = dep + timedelta(days=max(0, day_offset - 1))
            if day_date is None:
                continue

            stops = [s for s in (entry.get("stops") or []) if isinstance(s, dict)]
            if not stops:
                # No structured stops at all (legacy plans, or a free-text
                # day) -- keep the single all-day event the old export used.
                plan_text = entry.get("plan") or entry.get("summary") or ""
                lines.extend(
                    _vevent(
                        uid=f"day-{day_offset or _fmt_dt_date(day_date)}-{trip_id}@tripplanner",
                        summary=f"Day {day_offset or ''}: {destination}".strip(": "),
                        start=day_date,
                        description=str(plan_text),
                        location=destination,
                    )
                )
                continue

            timed: list[dict[str, Any]] = []
            untimed: list[dict[str, Any]] = []
            for stop in stops:
                (timed if _TIME_RE.search(str(stop.get("time") or "")) else untimed).append(stop)

            for index, stop in enumerate(timed):
                name = str(stop.get("name") or "Stop").strip()
                kind = str(stop.get("kind") or "").strip().lower()
                if kind == "hotel":
                    continue  # covered by the hotel-stay span event above
                emoji = _KIND_EMOJI.get(kind, "")
                address = ""
                if kind in {"attraction", "meal", "restaurant"} and name:
                    address = str((places_cache.get_details(name, destination) or {}).get("address") or "")
                lines.extend(
                    _vevent(
                        uid=f"stop-{day_offset}-{index}-{trip_id}@tripplanner",
                        summary=f"{emoji} {name}".strip(),
                        start=day_date,
                        description=str(stop.get("note") or ""),
                        location=address or destination,
                        all_day=False,
                        start_time=str(stop.get("time") or ""),
                        duration_min=int(stop.get("duration_min") or 60),
                    )
                )

            if untimed:
                names = [str(s.get("name") or "").strip() for s in untimed if s.get("name")]
                if names:
                    lines.extend(
                        _vevent(
                            uid=f"day-{day_offset or _fmt_dt_date(day_date)}-{trip_id}@tripplanner",
                            summary=f"Day {day_offset or ''}: {entry.get('title') or destination}".strip(": "),
                            start=day_date,
                            description=" · ".join(names),
                            location=destination,
                        )
                    )

    lines.append("END:VCALENDAR")
    return _CRLF.join(lines) + _CRLF

