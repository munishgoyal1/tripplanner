"""Build and rank stay decisions from the hotel offers already searched."""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime

from tripplanner.decisions.models import (
    Confidence,
    Decision,
    DecisionKind,
    DecisionScope,
    Effect,
    FareBasis,
    LodgingFacts,
    Option,
    Price,
    Rule,
    Source,
    make_decision_id,
    priced_state,
)
from tripplanner.decisions.rules import money, party_total
from tripplanner.providers.fx import convert
from tripplanner.providers.models import HotelOffer


def _property_key(offer: HotelOffer) -> str:
    return str(offer.provider_ref.get("hotel_id") or offer.hotel_name).strip().lower()


def _option_id(offer: HotelOffer) -> str:
    identity = "|".join(
        [
            offer.provider,
            str(offer.provider_ref.get("hotel_id") or ""),
            str(offer.provider_ref.get("offer_id") or ""),
            str(offer.provider_ref.get("rate_id") or ""),
            offer.hotel_name,
        ]
    )
    return f"opt_stay_{hashlib.sha256(identity.encode()).hexdigest()[:12]}"


def options_from_offers(
    offers: list[HotelOffer], *, checkin: str, checkout: str, cached: bool
) -> list[Option]:
    """Keep the cheapest verified room rate per property from this exact response."""
    cheapest: dict[str, HotelOffer] = {}
    for offer in offers:
        key = _property_key(offer)
        current = cheapest.get(key)
        if current is None or offer.total.amount < current.total.amount:
            cheapest[key] = offer

    return [
        Option(
            id=_option_id(offer),
            label=offer.hotel_name,
            detail=offer.room_name,
            price=Price(
                amount=offer.total.amount,
                currency=offer.total.currency,
                basis=FareBasis.PER_PARTY,
                taxes=offer.total.taxes,
                fees=offer.total.fees,
                due_at_property=offer.total.due_at_property,
                all_in=offer.total.all_in,
                mandatory_costs_complete=offer.total.mandatory_costs_complete,
                excluded=[dict(component) for component in offer.total.excluded],
            ),
            lodging=LodgingFacts(
                checkin=checkin,
                checkout=checkout,
                room_name=offer.room_name,
                board_name=offer.board_name,
                refundable=offer.refundable,
                cancellation_summary=offer.cancellation_summary,
                address=offer.address,
                rating=offer.rating,
                provider_ref=dict(offer.provider_ref),
            ),
            source=Source(
                provider=offer.provider,
                checked_at=offer.quoted_at,
                expires_at=offer.expires_at,
                confidence=Confidence.CACHED if cached else Confidence.LIVE,
            ),
        )
        for offer in cheapest.values()
    ]


def _base_currency(options: list[Option]) -> str:
    currencies = [option.price.currency.upper() for option in options if option.price]
    return Counter(currencies).most_common(1)[0][0] if currencies else ""


def _totals(options: list[Option]) -> tuple[str, dict[str, float]]:
    currency = _base_currency(options)
    totals: dict[str, float] = {}
    for option in options:
        total = party_total(option, 1)
        if total is None:
            continue
        converted = convert(total, option.price.currency, currency) if option.price else None
        if converted is None:
            return "", {}
        totals[option.id] = converted
    return currency, totals


def rank_stays(options: list[Option]) -> tuple[str, Rule, dict[str, str]] | None:
    """Choose on verified total, using provider rating and refundability only as ties."""
    usable = [option for option in options if option.id]
    if not usable:
        return None
    currency, totals = _totals(usable)

    if totals:
        winner = min(
            usable,
            key=lambda option: (
                totals[option.id],
                -(option.lodging.rating or 0) if option.lodging else 0,
                option.lodging.refundable is not True if option.lodging else True,
            ),
        )
        rule = Rule(
            code="verified_stay_total",
            text="Lowest verified stay total; provider rating and refundability break ties",
        )
    else:
        winner = max(
            usable,
            key=lambda option: (
                option.lodging.rating or 0 if option.lodging else 0,
                option.lodging.refundable is True if option.lodging else False,
            ),
        )
        rule = Rule(
            code="stay_quality_unpriced",
            text="Provider rating and refundability; prices could not be compared safely",
        )

    rejected: dict[str, str] = {}
    for option in usable:
        if option.id == winner.id:
            continue
        reasons: list[str] = []
        if totals:
            difference = totals[option.id] - totals[winner.id]
            if difference >= 1:
                reasons.append(f"costs {money(difference, currency)} more for the stay")
        option_rating = option.lodging.rating if option.lodging else None
        winner_rating = winner.lodging.rating if winner.lodging else None
        if (
            option_rating is not None
            and winner_rating is not None
            and option_rating < winner_rating
        ):
            reasons.append("has a lower provider rating")
        if option.lodging and option.lodging.refundable is False:
            if winner.lodging and winner.lodging.refundable is True:
                reasons.append("is not refundable")
        rejected[option.id] = (
            ", and ".join(reasons).capitalize() + "."
            if reasons
            else "Close on the verified facts available."
        )
    return winner.id, rule, rejected


def build_lodging_decision(
    offers: list[HotelOffer],
    *,
    destination: str,
    checkin: str,
    checkout: str,
    cached: bool,
) -> Decision | None:
    options = options_from_offers(offers, checkin=checkin, checkout=checkout, cached=cached)
    ranked = rank_stays(options)
    if ranked is None or len(options) < 2:
        return None
    chosen_id, rule, rejected = ranked
    for option in options:
        option.rejected_because = rejected.get(option.id)
    chosen = next(option for option in options if option.id == chosen_id)
    return Decision(
        id=make_decision_id("lodging", destination, checkin, checkout),
        kind=DecisionKind.LODGING,
        created_at=datetime.now(UTC),
        scope=DecisionScope(to_place=destination, date=checkin),
        subject=f"Stay in {destination}",
        rule=rule,
        chosen_option_id=chosen_id,
        options=options,
        effect=Effect(
            total_cost=party_total(chosen, 1),
            currency=chosen.price.currency if chosen.price else "",
        ),
        priced=priced_state(options),
    )


def reconcile_selected_lodging(plan: dict) -> None:
    """Make each stay decision reflect the searched property actually persisted."""
    from tripplanner.decisions.store import list_decisions, upsert_decision

    selected = plan.get("selected_hotels")
    if not isinstance(selected, list):
        return
    selected_names = {
        str(item.get("name") or item.get("hotel_name") or "").strip().lower()
        for item in selected
        if isinstance(item, dict)
    }
    selected_names.discard("")
    for decision in list_decisions(plan):
        if decision.kind != DecisionKind.LODGING or decision.override is not None:
            continue
        chosen = next(
            (
                option
                for option in decision.options
                if option.label.strip().lower() in selected_names
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
