"""Build and rank flight decisions from the exact offers already searched."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from tripplanner.decisions.models import (
    Confidence,
    Decision,
    DecisionKind,
    DecisionScope,
    Effect,
    FareBasis,
    FlightFacts,
    Option,
    Price,
    Rule,
    Source,
    TransportMode,
    make_decision_id,
    priced_state,
)
from tripplanner.decisions.rules import money, party_total
from tripplanner.providers.models import FlightOffer


def _option_id(offer: FlightOffer) -> str:
    references = sorted(f"{key}:{value}" for key, value in offer.provider_ref.items())
    identity = "|".join([offer.provider, *references])
    return f"opt_flight_{hashlib.sha256(identity.encode()).hexdigest()[:12]}"


def _segment_endpoint(segment: dict[str, Any], side: str) -> str:
    value = segment.get(side)
    if isinstance(value, dict):
        return str(value.get("iataCode") or value.get("airport") or value.get("code") or "")
    return str(value or "")


def _carrier(segment: dict[str, Any]) -> str:
    return str(
        segment.get("carrierName")
        or segment.get("carrier")
        or segment.get("airline")
        or segment.get("carrierCode")
        or "Flight"
    )


def options_from_offers(
    offers: list[FlightOffer],
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    cabin_class: str,
    cached: bool,
) -> list[Option]:
    options: list[Option] = []
    for offer in offers:
        segments = [dict(segment) for segment in offer.segments if isinstance(segment, dict)]
        carriers = list(dict.fromkeys(_carrier(segment) for segment in segments))
        stop_count = max(0, len(segments) - 1)
        route_start = _segment_endpoint(segments[0], "origin") if segments else origin
        route_end = _segment_endpoint(segments[-1], "destination") if segments else destination
        options.append(
            Option(
                id=_option_id(offer),
                mode=TransportMode.FLIGHT,
                label=" + ".join(carriers) or "Flight",
                detail=(
                    f"{route_start or origin} to {route_end or destination} · "
                    f"{'Direct' if stop_count == 0 else f'{stop_count} stop(s)'}"
                ),
                price=Price(
                    amount=offer.total.amount,
                    currency=offer.total.currency,
                    basis=FareBasis.PER_PARTY,
                ),
                flight=FlightFacts(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    return_date=return_date,
                    cabin_class=cabin_class,
                    segments=segments,
                    stops=stop_count,
                    seats_remaining=offer.seats_remaining,
                    baggage=offer.baggage,
                    terms=offer.terms,
                    provider_ref=dict(offer.provider_ref),
                ),
                source=Source(
                    provider=offer.provider,
                    checked_at=offer.quoted_at,
                    expires_at=offer.expires_at,
                    confidence=Confidence.CACHED if cached else Confidence.LIVE,
                ),
            )
        )
    return options


def rank_flights(options: list[Option]) -> tuple[str, Rule, dict[str, str]] | None:
    usable = [option for option in options if option.flight is not None]
    if not usable:
        return None
    winner = min(
        usable,
        key=lambda option: (
            option.flight.stops,
            party_total(option, 1) if party_total(option, 1) is not None else float("inf"),
        ),
    )
    rule = Rule(
        code="flight_stops_then_total",
        text="Fewest stops first; lowest verified party total breaks ties",
    )
    rejected: dict[str, str] = {}
    winner_total = party_total(winner, 1)
    for option in usable:
        if option.id == winner.id:
            continue
        reasons: list[str] = []
        if option.flight.stops > winner.flight.stops:
            difference = option.flight.stops - winner.flight.stops
            reasons.append(f"adds {difference} stop{'s' if difference != 1 else ''}")
        option_total = party_total(option, 1)
        if option_total is not None and winner_total is not None and option_total > winner_total:
            reasons.append(
                f"costs {money(option_total - winner_total, option.price.currency)} more"
            )
        rejected[option.id] = (
            ", and ".join(reasons).capitalize() + "."
            if reasons
            else "Close on the verified facts available."
        )
    return winner.id, rule, rejected


def build_flight_decision(
    offers: list[FlightOffer],
    *,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    cabin_class: str,
    cached: bool,
) -> Decision | None:
    options = options_from_offers(
        offers,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        cabin_class=cabin_class,
        cached=cached,
    )
    ranked = rank_flights(options)
    if ranked is None or len(options) < 2:
        return None
    chosen_id, rule, rejected = ranked
    for option in options:
        option.rejected_because = rejected.get(option.id)
    chosen = next(option for option in options if option.id == chosen_id)
    return Decision(
        id=make_decision_id("flight", origin, destination, departure_date, return_date),
        kind=DecisionKind.FLIGHT,
        created_at=datetime.now(UTC),
        scope=DecisionScope(from_place=origin, to_place=destination, date=departure_date),
        subject=f"Flight from {origin} to {destination}",
        rule=rule,
        chosen_option_id=chosen_id,
        options=options,
        effect=Effect(
            total_cost=party_total(chosen, 1),
            currency=chosen.price.currency if chosen.price else "",
        ),
        priced=priced_state(options),
    )



def _selected_offer_ids(selected: list[Any]) -> set[str]:
    offer_ids: set[str] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        provider_ref = item.get("provider_ref")
        if isinstance(provider_ref, dict) and provider_ref.get("offer_id"):
            offer_ids.add(str(provider_ref["offer_id"]))
        if item.get("offer_id"):
            offer_ids.add(str(item["offer_id"]))
    return offer_ids


def reconcile_selected_flight(plan: dict[str, Any]) -> None:
    """Make each flight decision reflect the exact offer the planner persisted."""
    from tripplanner.decisions.store import list_decisions, upsert_decision

    selected = plan.get("selected_flights")
    if not isinstance(selected, list):
        return
    selected_offer_ids = _selected_offer_ids(selected)
    if not selected_offer_ids:
        return
    for decision in list_decisions(plan):
        if decision.kind != DecisionKind.FLIGHT or decision.override is not None:
            continue
        chosen = next(
            (
                option
                for option in decision.options
                if option.flight
                and str(option.flight.provider_ref.get("offer_id") or "")
                in selected_offer_ids
            ),
            None,
        )
        if chosen is None or chosen.id == decision.chosen_option_id:
            continue
        upsert_decision(
            plan,
            decision.model_copy(
                update={
                    "chosen_option_id": chosen.id,
                    "effect": Effect(
                        total_cost=party_total(chosen, 1),
                        currency=chosen.price.currency if chosen.price else "",
                    ),
                }
            ),
        )
