"""Compare every sensible way to cover one hop, and keep the losers.

The planner used to price a single mode and throw the alternatives away, so the
itinerary could state a choice but never defend it. This tool fans out across
road, rail/transit and air for one origin → destination hop, prices whatever has
a real fare source, ranks them under one documented rule, and writes the whole
comparison onto the trip as a decision the user can inspect and overrule.

Modes with no fare source come back with their time and their effect on the day
and no price at all. That is the designed behaviour, not a failure.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool

from tripplanner.decisions.models import (
    Decision,
    DecisionKind,
    DecisionScope,
    Effect,
    Option,
    Price,
    Rule,
    Source,
    TransportMode,
    UnpricedReason,
    make_decision_id,
    priced_state,
)
from tripplanner.decisions.rules import TransportPrefs, party_total, rank
from tripplanner.decisions.store import list_decisions
from tripplanner.providers.fares import FareRequest, quote_fare
from tripplanner.tools.routing import route_metrics

# Below this, there is nothing to compare: you walk, drive or take the metro,
# and burning three provider calls on it helps nobody.
MIN_COMPARE_KM = 40.0
# Air only becomes a candidate once the ground alternative is long enough that
# the airport overhead can be repaid.
MIN_AIR_KM = 250.0

# Modelled air timings. Ground overhead is the airport run, bag drop, security,
# boarding, arrival and the transfer into the destination city.
_AIR_GROUND_OVERHEAD_MIN = 210
_AIR_TAXI_CLIMB_MIN = 45
_AIR_CRUISE_KMH = 750.0

_CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_COMPARISONS_PER_TRIP = 6
MAX_COMPARISONS_PER_TURN = 3

_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_turn_count = 0


def reset_turn_budget() -> None:
    """Called at the start of each agent turn so the per-turn ceiling is per turn."""
    global _turn_count
    _turn_count = 0


def _day_cost(door_to_door_min: int | None, mode: TransportMode) -> float:
    """Fraction of a usable day the option destroys around itself.

    Time in the vehicle is already counted separately; this is the fragmentation
    a mode adds on top — a mid-day flight leaves two half-days, a train leaves
    you in the centre and ready to go.
    """
    if door_to_door_min is None:
        return 0.0
    fragmentation = {
        TransportMode.FLIGHT: 0.25,
        TransportMode.ROAD: 0.10,
        TransportMode.TRAIN: 0.05,
        TransportMode.COACH: 0.10,
    }.get(mode, 0.10)
    return round(min(1.0, door_to_door_min / 600.0) * fragmentation + fragmentation / 2, 3)


def _air_minutes(distance_km: float) -> int:
    return int(round(_AIR_TAXI_CLIMB_MIN + distance_km / _AIR_CRUISE_KMH * 60))


def _prefs_from_trip(plan: dict[str, Any] | None, travellers: int) -> TransportPrefs:
    snapshot = (plan or {}).get("preferences_snapshot") or {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    budget_level = str(snapshot.get("budget_level") or snapshot.get("budget") or "moderate")
    disliked = _modes(snapshot.get("disliked_transport") or snapshot.get("avoid_transport"))
    preferred = _modes(snapshot.get("preferred_transport") or snapshot.get("transport_preferences"))
    return TransportPrefs(
        budget_level=budget_level,
        travellers=travellers,
        disliked_modes=disliked,
        preferred_modes=preferred,
    )


def _modes(raw: Any) -> frozenset[TransportMode]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return frozenset()
    found = set()
    for item in raw:
        text = str(item).strip().lower()
        for mode in TransportMode:
            if mode.value in text:
                found.add(mode)
    return frozenset(found)


def _travellers_from_trip(plan: dict[str, Any] | None, fallback: int) -> int:
    travelers = (plan or {}).get("travelers")
    if isinstance(travelers, dict):
        count = int(travelers.get("adults") or 0) + int(travelers.get("children") or 0)
        if count > 0:
            return count
    return max(1, fallback)


def _build_option(
    mode: TransportMode,
    label: str,
    duration_min: int | None,
    door_to_door_min: int | None,
    request: FareRequest,
    *,
    duration_estimated: bool = False,
    detail: str = "",
) -> Option:
    quote, reason = quote_fare(request)
    price = None
    source = Source()
    if quote is not None:
        price = Price(
            amount=quote.amount,
            currency=quote.currency,
            basis=quote.basis,
            amount_max=quote.amount_max,
        )
        source = Source(
            provider=quote.provider,
            url=quote.url,
            checked_at=quote.checked_at,
            confidence=quote.confidence,
        )
    return Option(
        id=mode.value,
        mode=mode,
        label=label,
        detail=detail,
        price=price,
        unpriced_reason=None if price else (reason or UnpricedReason.NO_SOURCE),
        duration_min=duration_min,
        door_to_door_min=door_to_door_min,
        duration_estimated=duration_estimated,
        day_cost=_day_cost(door_to_door_min, mode),
        source=source,
    )


def _collect_options(
    from_place: str, to_place: str, date: str, travellers: int, currency: str
) -> tuple[list[Option], float | None, list[str]]:
    warnings: list[str] = []
    drive = route_metrics(from_place, to_place, "DRIVE")
    if drive is None:
        return [], None, ["Could not measure the ground route for this hop."]

    distance_km = drive.get("distance_km")
    options: list[Option] = []

    def fare(mode: TransportMode) -> FareRequest:
        return FareRequest(
            mode=mode,
            from_place=from_place,
            to_place=to_place,
            date=date,
            travellers=travellers,
            currency=currency,
        )

    options.append(
        _build_option(
            TransportMode.ROAD,
            "Drive",
            drive["duration_min"],
            drive["duration_min"] + 20,
            fare(TransportMode.ROAD),
            detail=f"{distance_km} km door to door" if distance_km else "",
        )
    )

    transit = route_metrics(from_place, to_place, "TRANSIT")
    if transit is not None:
        options.append(
            _build_option(
                TransportMode.TRAIN,
                "Train or coach",
                transit["duration_min"],
                transit["duration_min"] + 40,
                fare(TransportMode.TRAIN),
                detail="Station to station, plus the transfer at each end",
            )
        )
    else:
        warnings.append("No scheduled ground service found for this hop.")

    if distance_km and distance_km >= MIN_AIR_KM:
        air_min = _air_minutes(distance_km)
        options.append(
            _build_option(
                TransportMode.FLIGHT,
                "Fly",
                air_min,
                air_min + _AIR_GROUND_OVERHEAD_MIN,
                fare(TransportMode.FLIGHT),
                duration_estimated=True,
                detail="Includes the airport run, security and the transfer in",
            )
        )

    return options, distance_km, warnings


def _summarise(decision: Decision, warnings: list[str]) -> str:
    chosen = decision.chosen
    payload = {
        "decision_id": decision.id,
        "subject": decision.subject,
        "chosen": chosen.label if chosen else "",
        "rule": decision.rule.text,
        "priced": decision.priced.value,
        "options": [
            {
                "mode": option.mode.value,
                "label": option.label,
                "door_to_door_min": option.door_to_door_min,
                "price": (
                    {"amount": option.price.amount, "currency": option.price.currency}
                    if option.price
                    else None
                ),
                "unpriced_reason": option.unpriced_reason.value
                if option.unpriced_reason
                else None,
                "rejected_because": option.rejected_because,
            }
            for option in decision.options
        ],
        "warnings": warnings,
        "note": (
            "Options without a price have no reliable fare source. State the time "
            "and the trade-off, and do not invent or estimate a fare for them."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def compare_transport_options(
    from_place: str,
    to_place: str,
    date: str = "",
    travellers: int = 1,
    day: int = 0,
) -> str:
    """Compare road, rail and air for one hop and record why one wins.

    Call this once for each intercity transfer in the itinerary, before you write
    that transfer into a day. The comparison, the rejected options and the rule
    are saved onto the trip, so the user can see the reasoning and change it.

    Options with no fare source come back unpriced. Report them with their time
    and their effect on the day; never fill in a price of your own.

    Args:
        from_place: Where the hop starts, e.g. 'Lisbon'.
        to_place: Where the hop ends, e.g. 'Porto'.
        date: Travel date YYYY-MM-DD. Needed for any live fare.
        travellers: People travelling this hop.
        day: Day number in the itinerary this hop belongs to.
    """
    global _turn_count
    from tripplanner.tools import trip_planner

    plan = trip_planner.load_active_trip_dict()
    if _turn_count >= MAX_COMPARISONS_PER_TURN:
        return "Comparison budget for this turn is used up. Reuse the comparisons already recorded."
    if plan is not None and len(list_decisions(plan)) >= MAX_COMPARISONS_PER_TRIP:
        return "This trip already holds the maximum number of recorded comparisons."

    travellers = _travellers_from_trip(plan, travellers)
    currency = str((plan or {}).get("currency") or "EUR").upper()
    key = (from_place.strip().lower(), to_place.strip().lower(), date, travellers, currency)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return json.dumps(cached[1], ensure_ascii=False, indent=2)

    _turn_count += 1
    options, distance_km, warnings = _collect_options(
        from_place, to_place, date, travellers, currency
    )
    if not options:
        return "Could not compare this hop: " + (warnings[0] if warnings else "no routes found.")
    if distance_km is not None and distance_km < MIN_COMPARE_KM:
        return (
            f"{from_place} to {to_place} is only {distance_km} km — too short to be worth "
            "comparing modes. Use local transport and move on."
        )

    prefs = _prefs_from_trip(plan, travellers)
    result = rank(options, prefs)
    if result is None:
        return "Could not rank the options for this hop."
    for option in options:
        option.rejected_because = result.rejected_because.get(option.id)

    chosen = next(o for o in options if o.id == result.chosen_option_id)
    total = party_total(chosen, travellers)
    decision = Decision(
        id=make_decision_id("transport", from_place, to_place, date or day),
        kind=DecisionKind.TRANSPORT_MODE,
        created_at=datetime.now(UTC),
        scope=DecisionScope(day=day or None, from_place=from_place, to_place=to_place, date=date),
        subject=f"{from_place} → {to_place}",
        rule=Rule(code=result.rule_code, text=result.rule_text),
        chosen_option_id=result.chosen_option_id,
        options=options,
        effect=Effect(
            total_cost=total,
            currency=(chosen.price.currency if chosen.price else currency),
        ),
        priced=priced_state(options),
    )
    trip_planner.record_trip_decision(decision)

    summary = _summarise(decision, warnings)
    _cache[key] = (time.time(), json.loads(summary))
    return summary
