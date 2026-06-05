"""Google Places API (New) — opening-hours & closure checks.

Catches mistakes like "the Louvre on Tuesday" or "Sistine Chapel before 9am"
before they land in the user's itinerary.

Uses the SAME Places API New as google_places.py — no new key, just an extra
field-mask. The `regularOpeningHours.weekdayDescriptions` returned by Google
is already human-readable ("Monday: 9:00 AM – 6:00 PM"); we also do our own
period scan when the user asks about a specific datetime.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx
from langchain_core.tools import tool

from multiagent.config import get_settings

_BASE = "https://places.googleapis.com/v1"

_WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def is_configured() -> bool:
    return bool(get_settings().google_places_api_key)


def _parse_when(when_iso: str) -> datetime | None:
    """Accept '2026-07-14', '2026-07-14T15:30', or '2026-07-14 15:30'.

    Treats the value as LOCAL TIME AT THE PLACE — we don't convert across
    timezones; we just compare weekday + hour:minute against Google's periods
    (which are also expressed in the place's local time).
    """
    if not when_iso:
        return None
    s = when_iso.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _minute_of_week(weekday_sun0: int, hour: int, minute: int) -> int:
    """Convert (weekday, h, m) to a single 0..10079 integer for easy interval math."""
    return weekday_sun0 * 24 * 60 + hour * 60 + minute


def _is_open_at(periods: list[dict], when: datetime) -> bool:
    """Check Google Places API New `regularOpeningHours.periods` for a moment.

    Each period: {open: {day, hour, minute}, close: {day, hour, minute}}.
    `day` is 0..6 where 0 = Sunday. Periods can cross midnight (close day > open day).
    A missing `close` means 24/7 from that open time.
    """
    if not periods:
        return False
    # Python: Monday=0..Sunday=6 → convert to Google's Sunday=0..Saturday=6
    google_weekday = (when.weekday() + 1) % 7
    target = _minute_of_week(google_weekday, when.hour, when.minute)
    week_minutes = 7 * 24 * 60

    for p in periods:
        op = p.get("open")
        if not op:
            continue
        op_min = _minute_of_week(op.get("day", 0), op.get("hour", 0), op.get("minute", 0))
        cl = p.get("close")
        if not cl:
            # No close = 24/7 (Google convention).
            return True
        cl_min = _minute_of_week(cl.get("day", 0), cl.get("hour", 0), cl.get("minute", 0))
        if cl_min <= op_min:
            # Crosses midnight / week boundary — wrap.
            cl_min += week_minutes
            # If target is before open, also shift it into the next week for comparison
            target_eff = target + week_minutes if target < op_min else target
            if op_min <= target_eff < cl_min:
                return True
        else:
            if op_min <= target < cl_min:
                return True
    return False


@tool
def check_place_hours(place_id: str, when_iso: str = "") -> str:
    """Check whether a place is open at a given local time, or just get the weekly schedule.

    Use this BEFORE adding an attraction or restaurant to the itinerary on a
    specific day/time — catches "Louvre on Tuesday" type mistakes.

    Args:
        place_id: A Google place_id (get one from search_places_with_reviews).
        when_iso: Optional. Local date or datetime AT THE PLACE.
            Accepts "2026-07-14", "2026-07-14T15:30", or "2026-07-14 15:30".
            If omitted, returns only the weekly schedule + permanent-closure
            status without an open/closed verdict for a specific moment.

    Returns JSON: name, business_status, weekday_schedule (human-readable list),
    and (if when_iso supplied) open_at_requested_time (bool) + requested_local_time.
    """
    if not is_configured():
        return (
            "Google Places API not configured. "
            "Set GOOGLE_PLACES_API_KEY in .env (Places API New). "
            "See https://console.cloud.google.com."
        )

    field_mask = (
        "id,displayName,businessStatus,utcOffsetMinutes,"
        "regularOpeningHours.weekdayDescriptions,regularOpeningHours.periods,"
        "currentOpeningHours.weekdayDescriptions,currentOpeningHours.periods"
    )
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_settings().google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }
    try:
        resp = httpx.get(f"{_BASE}/places/{place_id}", headers=headers, timeout=20)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"Failed to fetch place hours: {e}"

    p = resp.json()
    # currentOpeningHours reflects the next 7 days (holidays, special hours).
    # Prefer it; fall back to regularOpeningHours.
    hours = p.get("currentOpeningHours") or p.get("regularOpeningHours") or {}
    weekday_text = hours.get("weekdayDescriptions") or []
    periods = hours.get("periods") or []
    business_status = p.get("businessStatus") or "UNKNOWN"

    out: dict = {
        "name": p.get("displayName", {}).get("text", ""),
        "place_id": p.get("id", place_id),
        "business_status": business_status,
        "weekday_schedule": weekday_text,
    }
    if business_status in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
        out["warning"] = (
            f"This place is reported as {business_status} by Google — pick an alternative."
        )

    when = _parse_when(when_iso)
    if when_iso and when is None:
        out["error"] = (
            f"Could not parse when_iso='{when_iso}'. Use YYYY-MM-DD or "
            "YYYY-MM-DDTHH:MM (local time at the place)."
        )
        return json.dumps(out, indent=2)

    if when is not None:
        out["requested_local_time"] = when.strftime("%a %Y-%m-%d %H:%M")
        out["requested_weekday"] = _WEEKDAY_NAMES[(when.weekday() + 1) % 7]
        if business_status in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
            out["open_at_requested_time"] = False
        elif not periods:
            out["open_at_requested_time"] = None
            out["note"] = "Hours unknown — Google didn't return period data."
        else:
            out["open_at_requested_time"] = _is_open_at(periods, when)

    return json.dumps(out, indent=2)
