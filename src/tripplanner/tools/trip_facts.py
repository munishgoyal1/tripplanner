"""Trip-wide facts the itinerary must agree with everywhere.

A fact the traveller gives once ("we will drive our own car") is about the whole
trip, but the itinerary stores it as dozens of separate rows, notes and day
summaries written before anyone knew. Saving the fact changed nothing else: the
Rameshwaram trip kept "take a taxi from the temple to the beach" on every day
after the traveller said they were driving.

This module reads the fact from the plan and lists every place that still
contradicts it. It never rewrites prose itself; the agent owns the words and is
handed the exact rows to fix. Pure over a plan dict.
"""

from __future__ import annotations

import re
from typing import Any

OWN_CAR = "own_car"

#: The traveller's own vehicle. "Private car" is left out on purpose: in India it
#: usually means a hired car with a driver.
OWN_CAR_RE = re.compile(
    r"\b(?:(?:our|my|own|personal)\s+(?:own\s+)?(?:personal\s+)?(?:car|vehicle|suv|jeep)"
    r"|self[- ]?driv(?:e|ing)"
    r"|(?:we|i)(?:'ll|\s+will|\s+are|'re|\s+am|'m)?\s+(?:be\s+)?driving"
    r"|driv(?:e|ing)\s+(?:ourselves|myself|our\s+own|my\s+own))\b",
    re.I,
)
_TAXI_RE = re.compile(
    r"\b(?:taxi|taxis|cab|cabs|uber|ola|auto[- ]?rickshaws?|rickshaws?|tuk[- ]?tuks?"
    r"|car\s+with\s+(?:a\s+)?driver|chauffeur(?:ed)?)\b",
    re.I,
)
_NEGATED_RE = re.compile(
    r"\b(?:no|not|without|instead\s+of|rather\s+than|skip)\s+(?:\w+\s+){0,2}$", re.I
)
_TEXT_FIELDS = ("name", "note", "insight", "summary", "title")


def local_road_mode(plan: dict[str, Any]) -> str:
    """How the traveller gets around by road on this trip, when the plan says so."""
    explicit = str(plan.get("local_transport") or "").strip().lower()
    if explicit:
        return explicit
    statements = [
        *(str(item) for item in plan.get("trip_constraints") or []),
        str(plan.get("notes") or ""),
    ]
    if any(OWN_CAR_RE.search(text) for text in statements):
        return OWN_CAR
    transport = ((plan.get("preferences_snapshot") or {}).get("transport_preferences")) or {}
    if str(transport.get("preferred_road_transport") or "").strip().lower() == OWN_CAR:
        return OWN_CAR
    return ""


def _mentions_taxi(text: str) -> str:
    for match in _TAXI_RE.finditer(text):
        if not _NEGATED_RE.search(text[: match.start()]):
            return match.group(0)
    return ""


def fact_conflicts(plan: dict[str, Any], *, limit: int = 6) -> list[str]:
    """Rows, notes and summaries that still contradict a trip-wide fact."""
    if local_road_mode(plan) != OWN_CAR:
        return []
    found: list[str] = []
    for index, day in enumerate(plan.get("day_wise_itinerary") or []):
        if not isinstance(day, dict):
            continue
        label = f"Day {day.get('day') or index + 1}"
        for field in ("title", "summary"):
            word = _mentions_taxi(str(day.get(field) or ""))
            if word:
                found.append(f"{label} {field} still says '{word}'")
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            for field in _TEXT_FIELDS:
                word = _mentions_taxi(str(stop.get(field) or ""))
                if word:
                    name = stop.get("name") or "a stop"
                    found.append(f"{label}: {name} ({field}) still says '{word}'")
                    break
    if not found:
        return []
    shown = found[:limit]
    more = f" and {len(found) - limit} more" if len(found) > limit else ""
    return [
        "This trip travels in the traveller's own car, but the itinerary still plans "
        "taxis: " + "; ".join(shown) + more + ". Rewrite every affected day as driving "
        "in their own car: drop local taxi rows (the itinerary shows the drive between "
        "stops itself), keep inter-city journeys as 'Drive: A to B', add parking where "
        "it matters, and resubmit the full day_wise_itinerary."
    ]
