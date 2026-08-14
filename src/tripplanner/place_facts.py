"""The one reading of what the system already knows about a place.

A fact the planner paid to fetch was being stored in one shape and checked in
another: the cache wrote ``weekday_descriptions`` while the guard looked for an
``opening_hours`` string that nothing produced, so the opening-hours invariant
could not fire and a museum closed on Tuesdays was scheduled on a Tuesday. The
cure is structural rather than a patched key name — every consumer reads place
facts through this module, and :data:`REQUIRED_SUMMARY_KEYS` is asserted against
what the cache actually emits, so the two halves cannot drift apart again.

Everything here is pure and tri-state on purpose. A schedule that was never
fetched, or written in wording we do not parse, is *unknown* and stays silent.
Only a fact we actually read is allowed to contradict the itinerary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

#: Keys this module reads out of a cached place summary. The cache is tested
#: against this set, so deleting or renaming one of them fails loudly.
REQUIRED_SUMMARY_KEYS = frozenset(
    {"business_status", "open_now", "weekday_descriptions", "lat", "lng"}
)

#: Google business statuses that mean the place cannot be visited at all.
CLOSED_STATUSES = frozenset({"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"})

#: Indexed to match :meth:`datetime.date.weekday` — Monday is 0.
WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_WEEKDAY_INDEX = {name.casefold(): index for index, name in enumerate(WEEKDAY_NAMES)}

# Google separates a range with an en dash and pads it with narrow spaces.
_SPACE_RE = re.compile(r"[\s\u00a0\u2009\u202f]+")
_DASH_RE = re.compile(r"[\u2010-\u2015\u2212]")
_LINE_RE = re.compile(r"^([A-Za-z]+)\s*:\s*(.+)$")
_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.I,
)

#: A window covering the whole day, for "Open 24 hours".
_ALL_DAY: tuple[tuple[int, int], ...] = ((0, 1440),)

Window = tuple[int, int]


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", _DASH_RE.sub("-", text)).strip()


def _minutes(hour: str, minute: str | None, meridiem: str | None) -> int | None:
    value = int(hour)
    if meridiem:
        if value > 12:
            return None
        lowered = meridiem.casefold()
        if lowered == "pm" and value != 12:
            value += 12
        elif lowered == "am" and value == 12:
            value = 0
    elif value > 23:
        return None
    return value * 60 + int(minute or 0)


def _window(match: tuple[str, ...]) -> Window | None:
    open_h, open_m, open_ap, close_h, close_m, close_ap = match
    closes = _minutes(close_h, close_m, close_ap)
    if closes is None:
        return None
    # "1:00 - 6:00 PM" leaves the opening half unqualified; borrow the closing
    # meridiem and flip it when that would put the open after the close.
    opens = _minutes(open_h, open_m, open_ap or close_ap)
    if opens is None:
        return None
    if not open_ap and close_ap and opens >= closes:
        flipped = "am" if close_ap.casefold() == "pm" else "pm"
        alternative = _minutes(open_h, open_m, flipped)
        if alternative is not None and alternative < closes:
            opens = alternative
    if closes <= opens:
        closes += 1440  # closes after midnight
    return opens, closes


def parse_weekly_hours(lines: Any) -> dict[int, tuple[Window, ...]]:
    """Weekday (Monday 0) to open windows, for the days we could actually read.

    An empty tuple means the source says closed all day. A weekday missing from
    the result means we do not know, which is not the same answer.
    """
    out: dict[int, tuple[Window, ...]] = {}
    if not isinstance(lines, (list, tuple)):
        return out
    for raw in lines:
        line = _clean(str(raw or ""))
        match = _LINE_RE.match(line)
        if not match:
            continue
        weekday = _WEEKDAY_INDEX.get(match.group(1).casefold())
        if weekday is None:
            continue
        body = match.group(2).strip()
        lowered = body.casefold()
        if "closed" in lowered:
            out[weekday] = ()
            continue
        if "24 hours" in lowered:
            out[weekday] = _ALL_DAY
            continue
        windows = [_window(found) for found in _RANGE_RE.findall(body)]
        parsed = tuple(window for window in windows if window is not None)
        if parsed and len(parsed) == len(windows):
            out[weekday] = parsed
    return out


def weekday_of(day_iso: str) -> int | None:
    try:
        return date.fromisoformat(str(day_iso or "").strip()).weekday()
    except ValueError:
        return None


@dataclass(frozen=True)
class PlaceFacts:
    """What is known about one place, with unknown kept distinct from false."""

    business_status: str = ""
    open_now: bool | None = None
    weekly_hours: dict[int, tuple[Window, ...]] = field(default_factory=dict)

    @property
    def unavailable(self) -> bool:
        """True only when the source states the place no longer operates."""
        return self.business_status.strip().upper() in CLOSED_STATUSES

    def hours_on(self, day_iso: str) -> tuple[Window, ...] | None:
        """Open windows for that date, ``()`` when closed, ``None`` when unknown."""
        weekday = weekday_of(day_iso)
        if weekday is None:
            return None
        return self.weekly_hours.get(weekday)

    def closed_on(self, day_iso: str) -> bool:
        """True only when the schedule we read says closed for the whole day."""
        return self.hours_on(day_iso) == ()

    def fits(self, day_iso: str, start_min: int, end_min: int) -> bool | None:
        """Whether a visit sits inside an open window; ``None`` when unknown."""
        windows = self.hours_on(day_iso)
        if windows is None:
            return None
        if not windows:
            return False
        return any(start_min >= opens and end_min <= closes for opens, closes in windows)

    def window_text(self, day_iso: str) -> str:
        windows = self.hours_on(day_iso)
        if not windows:
            return ""
        return ", ".join(f"{_hhmm(opens)}-{_hhmm(closes % 1440)}" for opens, closes in windows)


def _hhmm(minute: int) -> str:
    return f"{(minute // 60) % 24:02d}:{minute % 60:02d}"


#: Nothing is known. Shared so callers never have to invent an empty summary.
UNKNOWN = PlaceFacts()


def facts_from_summary(summary: Any) -> PlaceFacts:
    """Read a cached place summary into checkable facts."""
    if not isinstance(summary, dict):
        return UNKNOWN
    open_now = summary.get("open_now")
    return PlaceFacts(
        business_status=str(summary.get("business_status") or ""),
        open_now=open_now if isinstance(open_now, bool) else None,
        weekly_hours=parse_weekly_hours(summary.get("weekday_descriptions")),
    )
