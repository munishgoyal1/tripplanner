"""Turning a finished tool call into one honest line a traveller can read.

A receipt says what the planner actually did. It is derived from the tool's own
output, never written by the model, so it cannot claim work that did not happen.
A tool with nothing verifiable to report produces no receipt at all — silence is
better than a line that only sounds like evidence.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tripplanner.providers.models import PRICED_QUOTE_STATUSES

MAX_TEXT = 90
MAX_DETAIL = 60


@dataclass(frozen=True)
class Receipt:
    kind: str
    text: str
    detail: str = ""
    decision_id: str = ""
    source: str = ""
    priced: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind, "text": self.text}
        if self.detail:
            payload["detail"] = self.detail
        if self.decision_id:
            payload["decision_id"] = self.decision_id
        if self.source:
            payload["source"] = self.source
        if self.priced:
            payload["priced"] = self.priced
        return payload


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _comparison(output: str) -> Receipt | None:
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        # The tool refused the hop and said so in prose. Nothing was compared.
        return None
    if not isinstance(payload, dict) or not payload.get("decision_id"):
        return None
    options = payload.get("options") or []
    subject = str(payload.get("subject") or "").strip()
    chosen = str(payload.get("chosen") or "").strip()
    rejected = max(len(options) - 1, 0)
    text = f"Compared {len(options)} ways" + (f" from {subject}" if subject else "")
    detail = ", ".join(
        part
        for part in (
            f"{chosen.lower()} picked" if chosen else "",
            f"{rejected} rejected" if rejected else "",
        )
        if part
    )
    return Receipt(
        kind="transport",
        text=_clip(text, MAX_TEXT),
        detail=_clip(detail, MAX_DETAIL),
        decision_id=str(payload["decision_id"]),
        priced=str(payload.get("priced") or ""),
    )


def _fixed(kind: str, text: str, source: str = "") -> Callable[[str], Receipt | None]:
    return lambda _output: Receipt(kind=kind, text=text, source=source)


def _payload(output: str) -> Any:
    """The JSON a tool returned, even when it put a status line in front of it."""
    try:
        return json.loads(output)
    except (TypeError, ValueError):
        pass
    starts = [index for index in (output.find("["), output.find("{")) if index >= 0]
    if not starts:
        return None
    try:
        return json.loads(output[min(starts) :])
    except (TypeError, ValueError):
        return None


def _results(output: str) -> list[Any]:
    """The result list a search tool returned, or nothing we are sure about."""
    payload = _payload(output)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("offers", "results", "places", "activities"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _name_of(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("name", "title", "hotel_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    display = item.get("displayName")
    if isinstance(display, dict):
        return str(display.get("text") or "").strip()
    return ""


def _provider_of(output: str, fallback: str = "") -> str:
    """The provider that actually answered, so a receipt never credits the wrong one."""
    payload = _payload(output)
    if isinstance(payload, dict):
        provider = payload.get("provider")
        if isinstance(provider, str) and provider.strip() and provider.strip() != "none":
            return provider.strip()
    return fallback


_PRICED_STATUS_VALUES = {status.value for status in PRICED_QUOTE_STATUSES}


def _is_priced(output: str) -> bool:
    payload = _payload(output)
    if not isinstance(payload, dict):
        return False
    status = payload.get("quote_status")
    return isinstance(status, str) and status in _PRICED_STATUS_VALUES


def _counted(
    kind: str, text: str, nouns: tuple[str, str], source: str = ""
) -> Callable[[str], Receipt | None]:
    """A search receipt that says how much it found, taken from the output itself.

    Four searches in one turn all reading "Searched bookable stays" tell a
    traveller nothing about which four. The count and the first name come from
    what the tool returned, so the line stays evidence rather than decoration.
    """

    def build(output: str) -> Receipt | None:
        found = _results(output)
        if not found:
            return Receipt(kind=kind, text=text, source=source)
        first = _name_of(found[0])
        rest = len(found) - 1
        detail = f"{len(found)} {nouns[0] if len(found) == 1 else nouns[1]}"
        if first:
            detail += f" · {first}" + (f" +{rest}" if rest > 0 else "")
        return Receipt(kind=kind, text=text, detail=_clip(detail, MAX_DETAIL), source=source)

    return build


def _stays(output: str) -> Receipt | None:
    """A stay search, told apart by whether a room was actually priced.

    With no hotel rate provider configured the tool falls back to property
    metadata, which is worth showing but is not a bookable rate. Saying so is
    the difference between evidence and a claim.
    """

    if _is_priced(output):
        return _counted(
            "lodging",
            "Searched bookable stays",
            ("stay", "stays"),
            _provider_of(output),
        )(output)
    return _counted(
        "lodging",
        "Looked up stays, no live room rate",
        ("stay", "stays"),
        _provider_of(output, "Google Places"),
    )(output)


def _live_flights(text: str, fallback: str) -> Callable[[str], Receipt | None]:
    """Flight receipts credit whichever provider in the chain answered."""
    return lambda output: Receipt(
        kind="flights", text=text, source=_provider_of(output, fallback)
    )


# One entry per tool whose work a traveller would recognise. Everything absent
# from this table is bookkeeping, and bookkeeping is not evidence.
_BUILDERS: dict[str, Callable[[str], Receipt | None]] = {
    "compare_transport_options": _comparison,
    "search_flights_duffel": _live_flights("Searched live flight inventory", "Duffel"),
    "search_flights": _live_flights("Searched live flight inventory", ""),
    "verify_flight_offer": _live_flights("Re-checked the fare was still live", "Duffel"),
    "search_hotels": _stays,
    "search_activities": _counted(
        "places", "Searched things to do", ("activity", "activities"), ""
    ),
    "search_points_of_interest": _counted(
        "places", "Searched points of interest", ("place", "places"), ""
    ),
    "search_places_with_reviews": _counted(
        "places", "Checked ratings and reviews", ("place", "places"), "Google Places"
    ),
    "get_place_reviews": _fixed("places", "Read what visitors said", "Google Places"),
    "nearby_restaurants": _counted(
        "places", "Looked for places to eat nearby", ("place", "places"), "Google Places"
    ),
    "check_place_hours": _fixed("places", "Checked opening hours", "Google Places"),
    "compute_route": _fixed("routing", "Measured real travel time", "Google Routes"),
    "optimize_day_route": _fixed("routing", "Reordered the day to cut travel", "Google Routes"),
    "get_weather_forecast": _fixed("weather", "Pulled the forecast for your dates", "Open-Meteo"),
    "check_visa_requirements": _fixed("entry", "Checked entry requirements", "Tavily"),
    "find_local_events": _fixed("events", "Looked for events on your dates", "Tavily"),
    "web_search": _fixed("web", "Searched the web", "Tavily"),
}


def receipt_for(name: str, output: Any) -> Receipt | None:
    """Project one finished tool call onto a receipt, or onto nothing."""
    builder = _BUILDERS.get(name)
    if builder is None:
        return None
    return builder(output if isinstance(output, str) else "")


class ReceiptLog:
    """The receipts for one turn, numbered, in order, and without repeats.

    A single tool call can surface twice in the event stream because the cache
    wrapper re-enters the tool, and the second event carries the same output as
    the first. Same output means the same look at the world, so it describes no
    further work and earns no second line.
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self.count = 0

    def add(self, name: str, output: Any) -> Receipt | None:
        text = output if isinstance(output, str) else ""
        key = (name, text)
        if key in self._seen:
            return None
        receipt = receipt_for(name, text)
        if receipt is None:
            return None
        self._seen.add(key)
        self.count += 1
        return receipt
