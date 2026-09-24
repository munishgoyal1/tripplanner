"""Explicit asks in the traveller's request that a finished plan must answer.

Found by whole-itinerary judging: "Include the flights" produced no flight,
"Verify current official entry requirements" produced no entry section, and a
"Char Dham route" covered two of its four temples, each without a word to the
traveller. These are detected from the request text deterministically, so the
completion gate can require each to be met or explicitly dropped with a reason
(``dropped_requests`` on the trip), never silently ignored.

Only unambiguous phrasings are recognised; anything subtler stays with the model.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_INCLUDE_FLIGHTS = re.compile(
    r"\b(?:include|including|with|book|add)\s+(?:the\s+|our\s+|return\s+|all\s+)*flights?\b"
    r"|\bflights?\s+included\b",
    re.IGNORECASE,
)
_ENTRY_RULES = re.compile(
    r"\b(?:verify|check|confirm|include)\b[^.]*"
    r"\b(?:entry requirements?|visa|travel advisor(?:y|ies))\b",
    re.IGNORECASE,
)
_COVERING = re.compile(
    r"\bcovering\s+(?P<places>[^.;!?]+?)(?=\s+(?:trip|by|with|on|in|from|for)\b|[.;!?]|$)"
    r"|\btrip to\s+(?P<route>[^.;!?]+?(?:,|\band\b)[^.;!?]+?)\s+from\b",
    re.IGNORECASE,
)
#: Named circuits whose parts a traveller expects by name.
_CIRCUITS = {
    "char dham": ("Yamunotri", "Gangotri", "Kedarnath", "Badrinath"),
    "golden triangle": ("Delhi", "Agra", "Jaipur"),
}
_REGION = re.compile(
    r"(?:the\s+)?(?:northern|southern|eastern|western|central|upper|lower|coastal)\b",
    re.IGNORECASE,
)
_FILLER = frozenset(
    {
        "the",
        "route",
        "circuit",
        "region",
        "area",
        "north",
        "south",
        "east",
        "west",
        "and",
        "nearby",
        "sites",
        "religious",
        "old",
        "city",
    }
)


def _tokens(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {token for token in re.findall(r"[a-z0-9]+", folded) if len(token) > 2}


def _named_places(request: str) -> list[str]:
    places: list[str] = []
    for match in _COVERING.finditer(request):
        phrase = match.group("places") or match.group("route") or ""
        for part in re.split(r",|\band\b|&", phrase):
            part = part.strip()
            circuit = next((name for name in _CIRCUITS if name in part.lower()), None)
            if _REGION.match(part):
                continue  # "northern Italy" is met by Milan; names cannot prove it
            if circuit:
                places.extend(_CIRCUITS[circuit])
            elif _tokens(part) - _FILLER:
                places.append(part)
    return list(dict.fromkeys(places))


def _itinerary_text(plan: dict[str, Any]) -> set[str]:
    words: set[str] = set()
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for field in ("title", "summary", "city", "location"):
            words |= _tokens(str(day.get(field) or ""))
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                for field in ("name", "city", "note"):
                    words |= _tokens(str(stop.get(field) or ""))
    return words


def _dropped(plan: dict[str, Any]) -> set[str]:
    words: set[str] = set()
    for item in plan.get("dropped_requests") or []:
        if isinstance(item, dict) and str(item.get("reason") or "").strip():
            words |= _tokens(str(item.get("ask") or ""))
    return words


def unmet_asks(request: str, plan: dict[str, Any]) -> list[str]:
    """Completion gaps for explicit asks the plan neither meets nor drops with a reason."""
    request = str(request or "")
    if not request.strip() or not plan.get("day_wise_itinerary"):
        return []
    dropped = _dropped(plan)
    gaps: list[str] = []
    if (
        _INCLUDE_FLIGHTS.search(request)
        and not plan.get("selected_flights")
        and not {"flight", "flights"} & dropped
    ):
        gaps.append(
            "The request asked to include the flights, but no flight is selected. Select "
            "the flights, or add the ask to dropped_requests with the reason you give the "
            "traveller."
        )
    if (
        _ENTRY_RULES.search(request)
        and not plan.get("visa")
        and not {"entry", "visa", "advisory", "advisories"} & dropped
    ):
        gaps.append(
            "The request asked to verify entry requirements, but the trip has no visa or entry "
            "section. Run check_visa_requirements and save its result as visa, or add the ask "
            "to dropped_requests with the reason."
        )
    covered = _itinerary_text(plan)

    def answered(place: str) -> bool:
        # "Phuket or Krabi" is a choice: either one meets it.
        options = [_tokens(option) - _FILLER for option in re.split(r"\bor\b", place)]
        return any(option and (option <= covered or option <= dropped) for option in options)

    missing = [place for place in _named_places(request) if not answered(place)]
    if missing:
        gaps.append(
            "The request named " + ", ".join(missing) + ", but the itinerary never goes there. "
            "Plan them, or add them to dropped_requests with the reason you give the traveller."
        )
    return gaps
