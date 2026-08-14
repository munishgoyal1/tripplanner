"""Public holidays, so the planner knows when its opening hours stop applying.

A weekly schedule says the Vatican Museums open on Thursdays. It does not say
that this particular Thursday is Assumption Day. The honest consequence is not
that the place is closed — it may well be open — but that the fact we hold no
longer answers the question, and a check that cannot be answered must say so
rather than pass.

Source is Nager.Date: keyless, quota-free, one request per country and year,
cached for the process lifetime because a past year's holidays never change. A
failed lookup returns ``None`` and is not cached, so a dropped call cannot turn
into a permanently empty calendar.
"""

from __future__ import annotations

from datetime import date
from threading import Lock

import httpx

from tripplanner import http_client

_API = "https://date.nager.at/api/v3/PublicHolidays"
_TIMEOUT_S = 8

_cache: dict[tuple[str, int], dict[str, str]] = {}
_lock = Lock()


def _fetch(country_code: str, year: int) -> dict[str, str] | None:
    try:
        response = http_client.get(f"{_API}/{year}/{country_code}", timeout=_TIMEOUT_S)
        if response.status_code == 404:
            return {}  # a country the source does not cover is a known answer
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(rows, list):
        return None

    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = str(row.get("date") or "").strip()
        if not day or row.get("global") is False:
            # A regional holiday does not tell us anything about this city.
            continue
        name = str(row.get("localName") or row.get("name") or "").strip()
        if name:
            out[day] = name
    return out


def holidays_for(country_code: str, year: int) -> dict[str, str] | None:
    """Date to holiday name for one country-year, or ``None`` when unknown."""
    code = str(country_code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    key = (code, int(year))
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached

    fetched = _fetch(code, int(year))
    if fetched is None:
        return None
    with _lock:
        _cache[key] = fetched
    return fetched


def holiday_on(country_code: str, day_iso: str) -> str | None:
    """Holiday name for that date, ``""`` when it is an ordinary day, ``None``
    when the calendar could not be read."""
    text = str(day_iso or "").strip()
    try:
        year = date.fromisoformat(text).year
    except ValueError:
        return None
    calendar = holidays_for(country_code, year)
    if calendar is None:
        return None
    return calendar.get(text, "")


def reset_cache() -> None:
    with _lock:
        _cache.clear()
