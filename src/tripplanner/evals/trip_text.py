"""Readable, pointer-annotated trip text for whole-itinerary judging.

A judge must cite an exact JSON Pointer and a quote present at that pointer
(see ``evals.judge.validate``). A raw trip JSON makes that hard for a reader, so
this renders every meaningful scalar as ``<pointer>: <value>`` under day
headings. The text is a view of the evidence, never a second source of truth.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Keys that carry provider plumbing rather than anything a traveller would read.
_SKIP_KEYS = frozenset(
    {
        "place_id",
        "lat",
        "lng",
        "latitude",
        "longitude",
        "photo",
        "photos",
        "photo_url",
        "photo_reference",
        "url",
        "website",
        "maps_url",
        "google_maps_uri",
        "icon",
        "user_id",
        "id",
        "trip_number",
        "created_at",
        "updated_at",
        "polyline",
    }
)
_MAX_VALUE = 400
#: Place facts a judge can cite; reviews and photo references are bulk, not evidence.
_JUDGED_FIELDS = (
    "name",
    "address",
    "rating",
    "review_count",
    "price_level",
    "business_status",
    "editorial_summary",
    "weekday_descriptions",
)


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _lines(value: Any, path: str, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _SKIP_KEYS:
                continue
            _lines(item, f"{path}/{_escape(str(key))}", out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _lines(item, f"{path}/{index}", out)
    elif value not in (None, "", [], {}):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        out.append(f"{path}: {text[:_MAX_VALUE]}")


def places_for(plan: dict[str, Any], places: dict[str, Any]) -> dict[str, Any]:
    """Only the place facts this plan names; the full cache is megabytes."""
    names = {
        str(stop.get("name") or "").strip().casefold()
        for day in plan.get("day_wise_itinerary") or []
        if isinstance(day, dict)
        for stop in day.get("stops") or []
        if isinstance(stop, dict)
    }
    names.discard("")
    # Lookups are keyed by the destination or by one day's own locality.
    contexts = {str(plan.get("destination") or "").strip().casefold()}
    for day in plan.get("day_wise_itinerary") or []:
        if isinstance(day, dict):
            contexts |= {
                str(day.get(field) or "").strip().casefold()
                for field in ("city", "location", "title")
            }
    picked = {}
    for key, value in places.items():
        name, _, city = str(key).partition("|")
        city = city.strip().casefold()
        if name.strip().casefold() in names and (
            not city or any(city in context for context in contexts if context)
        ):
            picked[key] = (
                {field: value[field] for field in _JUDGED_FIELDS if field in value}
                if isinstance(value, dict)
                else value
            )
    return picked


def render(evidence: dict[str, Any]) -> str:
    """Render ``evals.judge.evidence_for`` output as pointer-annotated text."""
    out: list[str] = []
    request = evidence.get("request") or ""
    out.append("# User request")
    out.append(f"/request: {request}" if request else "(no request recorded)")
    out.append("\n# Preferences")
    _lines(evidence.get("preferences") or {}, "/preferences", out)
    plan = evidence.get("plan") or {}
    out.append("\n# Trip")
    header = {k: v for k, v in plan.items() if k != "day_wise_itinerary"}
    _lines(header, "/plan", out)
    for index, day in enumerate(plan.get("day_wise_itinerary") or []):
        if not isinstance(day, dict):
            continue
        out.append(f"\n## Day {day.get('day', index + 1)} · {day.get('date', '')}")
        _lines(day, f"/plan/day_wise_itinerary/{index}", out)
    if evidence.get("final_reply"):
        out.append("\n# Final reply")
        out.append(f"/final_reply: {evidence['final_reply']}")
    places = evidence.get("places") or {}
    if places:
        out.append("\n# Place facts")
        for key, fact in places.items():
            if not isinstance(fact, dict):
                continue
            base = f"/places/{_escape(str(key))}"
            for field in ("name", "rating", "review_count", "business_status", "editorial_summary"):
                if fact.get(field) not in (None, ""):
                    out.append(f"{base}/{field}: {fact[field]}")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)) + "\n"
