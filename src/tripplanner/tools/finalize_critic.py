"""Deterministic self-correction critic for finalized trip plans.

Runs over the finalized plan + the user's preferences and surfaces a short
"Heads up" list when something obvious is off (wrong city, hotel that doesn't
match the destination, kid-unfriendly choices, etc.). No LLM call — the rules
are cheap, predictable, and easy to extend without changing the agent loop.

Each rule returns a single short bullet OR an empty string when the rule
doesn't fire. `critique(plan, prefs)` collects all non-empty bullets.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any


def _str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _all_fields(blob: Any) -> str:
    """Flatten any nested dict/list/string into a lowercase searchable string."""
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob.lower()
    if isinstance(blob, (int, float)):
        return str(blob)
    if isinstance(blob, dict):
        return " ".join(_all_fields(v) for v in blob.values())
    if isinstance(blob, (list, tuple)):
        return " ".join(_all_fields(v) for v in blob)
    try:
        return json.dumps(blob, ensure_ascii=False, default=str).lower()
    except Exception:
        return str(blob).lower()


def _check_dates(plan: dict[str, Any]) -> str:
    dep = _str(plan.get("departure_date"))
    ret = _str(plan.get("return_date"))
    if not dep or not ret:
        return "Trip is missing a departure or return date."
    try:
        d = date.fromisoformat(dep)
        r = date.fromisoformat(ret)
    except ValueError:
        return "Departure/return date is not in YYYY-MM-DD format."
    if r < d:
        return f"Return date {ret} is before departure {dep}."
    return ""


def _check_hotels_match_destination(plan: dict[str, Any]) -> str:
    dest = _str(plan.get("destination")).lower().strip()
    hotels = plan.get("selected_hotels") or []
    if not dest or not hotels:
        return ""
    # Take just the first city token from "Paris, France" → "paris".
    dest_token = re.split(r"[,;/]", dest, maxsplit=1)[0].strip()
    if not dest_token:
        return ""
    for h in hotels:
        text = _all_fields(h)
        if dest_token not in text:
            return (
                f"Selected hotel doesn't mention '{dest_token.title()}' — "
                "double-check the city before booking."
            )
    return ""


def _check_flight_missing_for_long_trip(plan: dict[str, Any]) -> str:
    flights = plan.get("selected_flights") or []
    if flights:
        return ""
    dep = _str(plan.get("departure_date"))
    ret = _str(plan.get("return_date"))
    if not dep or not ret:
        return ""
    try:
        nights = (date.fromisoformat(ret) - date.fromisoformat(dep)).days
    except ValueError:
        return ""
    if nights >= 2:
        return "No flights selected — add a flight before finalizing a multi-day trip."
    return ""


def _kid_ages_in(prefs: dict[str, Any]) -> list[int]:
    ages: list[int] = []
    for fam in prefs.get("family_members", []) or []:
        if not isinstance(fam, dict):
            continue
        rel = _str(fam.get("relationship")).lower()
        age = fam.get("age")
        if rel in {"child", "son", "daughter", "kid"} and isinstance(age, int) and age < 13:
            ages.append(age)
    return ages


def _check_kid_friendly(plan: dict[str, Any], prefs: dict[str, Any]) -> str:
    kid_ages = _kid_ages_in(prefs)
    if not kid_ages:
        return ""
    activities = plan.get("selected_activities") or []
    if not activities:
        return f"Trip is for kids (ages {','.join(str(a) for a in kid_ages)}) but no activities are selected yet."
    blob = _all_fields(activities)
    kid_keywords = ("kid", "family", "child", "zoo", "park", "playground", "aquarium", "museum", "beach")
    if not any(k in blob for k in kid_keywords):
        return f"Kids on this trip (ages {','.join(str(a) for a in kid_ages)}) — none of the selected activities look obviously kid-friendly."
    return ""


def _check_mobility(plan: dict[str, Any], prefs: dict[str, Any]) -> str:
    mobility_notes: list[str] = []
    for fam in prefs.get("family_members", []) or []:
        if isinstance(fam, dict) and _str(fam.get("mobility")).strip():
            mobility_notes.append(_str(fam.get("mobility")))
    if not mobility_notes and not (prefs.get("accessibility_needs") or []):
        return ""
    blob = _all_fields((plan.get("selected_hotels") or []) + (plan.get("selected_activities") or []))
    if not any(k in blob for k in ("accessible", "wheelchair", "elevator", "lift", "step-free", "ada")):
        return "Mobility needs on file but no selected hotel/activity mentions accessibility — verify before booking."
    return ""


def _check_dietary(plan: dict[str, Any], prefs: dict[str, Any]) -> str:
    diets: list[str] = []
    for fam in prefs.get("family_members", []) or []:
        if isinstance(fam, dict) and _str(fam.get("dietary")).strip():
            diets.append(_str(fam.get("dietary")).lower())
    food = prefs.get("food_preferences") or {}
    if isinstance(food, dict):
        d = food.get("dietary")
        if isinstance(d, str) and d.strip():
            diets.append(d.lower())
        elif isinstance(d, list):
            diets.extend(str(x).lower() for x in d if x)
    diets = [d for d in diets if d not in {"", "none", "no", "any"}]
    if not diets:
        return ""
    # If the user has dietary needs, the day-wise itinerary should at least
    # mention them somewhere — restaurant pick, meal note, etc.
    blob = _all_fields(plan.get("day_wise_itinerary") or [])
    keywords = set()
    for d in diets:
        for token in re.split(r"[\s,;/]+", d):
            if len(token) >= 4:
                keywords.add(token)
    if keywords and not any(k in blob for k in keywords):
        return (
            f"Dietary needs ({', '.join(sorted(set(diets)))}) aren't reflected "
            "anywhere in the day-wise itinerary — add restaurant picks or meal notes."
        )
    return ""


def _check_past_dislikes(plan: dict[str, Any], prefs: dict[str, Any]) -> str:
    """Surface a heads-up if a previously disliked aspect shows up again.

    Looks at `learned_notes` whose `note` starts with "Disliked on" (the
    convention used by `record_trip_postmortem`) and matches any keyword from
    the dislike against the current plan.
    """
    notes = prefs.get("learned_notes") or []
    if not notes:
        return ""
    plan_blob = _all_fields({
        "flights": plan.get("selected_flights"),
        "hotels": plan.get("selected_hotels"),
        "activities": plan.get("selected_activities"),
        "itinerary": plan.get("day_wise_itinerary"),
    })
    for n in notes:
        if not isinstance(n, dict):
            continue
        note = _str(n.get("note"))
        if not note.lower().startswith("disliked on"):
            continue
        # "Disliked on Goa trip: morning flight" → "morning flight"
        if ":" not in note:
            continue
        tail = note.split(":", 1)[1].strip().lower()
        # Match if any 4+ char content word from the tail shows up in the plan.
        for token in re.split(r"[\s,;/]+", tail):
            if len(token) >= 5 and token in plan_blob:
                return f"You previously disliked '{tail}' — this plan still includes it."
    return ""


def critique(plan: dict[str, Any], prefs: dict[str, Any] | None = None) -> list[str]:
    """Return a list of short "heads up" bullets, or [] when the plan looks clean."""
    if not plan:
        return []
    prefs = prefs or {}
    rules = [
        _check_dates(plan),
        _check_hotels_match_destination(plan),
        _check_flight_missing_for_long_trip(plan),
        _check_kid_friendly(plan, prefs),
        _check_mobility(plan, prefs),
        _check_dietary(plan, prefs),
        _check_past_dislikes(plan, prefs),
    ]
    return [r for r in rules if r]
