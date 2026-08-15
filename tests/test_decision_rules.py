"""Ranking is pure, so these are real assertions on real numbers — no mocks."""

from __future__ import annotations

from datetime import UTC, datetime

from tripplanner.decisions.flights import build_flight_decision
from tripplanner.decisions.lodging import build_lodging_decision, reconcile_selected_lodging
from tripplanner.decisions.models import (
    FareBasis,
    FlightFacts,
    LodgingFacts,
    Option,
    Price,
    TransportMode,
)
from tripplanner.decisions.rules import TransportPrefs, party_total, rank
from tripplanner.providers.models import FlightOffer, HotelOffer, Money


def option(
    mode: TransportMode,
    *,
    door: int,
    amount: float | None = None,
    currency: str = "EUR",
    basis: FareBasis = FareBasis.PER_PARTY,
    day_cost: float = 0.1,
) -> Option:
    return Option(
        id=mode.value,
        mode=mode,
        label=mode.value,
        price=Price(amount=amount, currency=currency, basis=basis) if amount is not None else None,
        door_to_door_min=door,
        day_cost=day_cost,
    )


def test_cheaper_and_quicker_option_wins():
    train = option(TransportMode.TRAIN, door=200, amount=120)
    fly = option(TransportMode.FLIGHT, door=330, amount=280, day_cost=0.3)
    result = rank([train, fly], TransportPrefs(travellers=2))
    assert result is not None
    assert result.chosen_option_id == "train"
    assert "costs" in result.rejected_because["flight"].lower()
    assert "longer door to door" in result.rejected_because["flight"]


def test_unpriced_option_is_not_rewarded_for_having_no_price():
    """A missing fare must not read as a fare of zero."""
    train = option(TransportMode.TRAIN, door=200)
    fly = option(TransportMode.FLIGHT, door=195, amount=280)
    result = rank([train, fly], TransportPrefs(travellers=1))
    assert result is not None
    assert result.chosen_option_id == "flight"
    assert result.rule_code == "known_total_preferred"
    assert "no fare we can verify" in result.rejected_because["train"]


def test_unpriced_option_wins_when_it_is_clearly_quicker():
    train = option(TransportMode.TRAIN, door=150)
    fly = option(TransportMode.FLIGHT, door=330, amount=280, day_cost=0.3)
    result = rank([train, fly], TransportPrefs(travellers=1))
    assert result is not None
    assert result.chosen_option_id == "train"
    assert result.rule_code == "door_to_door_time_unpriced"


def test_no_option_is_priced_falls_back_to_time_alone():
    train = option(TransportMode.TRAIN, door=200)
    coach = option(TransportMode.COACH, door=320)
    result = rank([train, coach], TransportPrefs())
    assert result is not None
    assert result.chosen_option_id == "train"
    assert result.rule_code == "door_to_door_time_unpriced"
    assert "no fare source" in result.rule_text


def test_budget_level_changes_the_money_for_time_trade():
    slow_cheap = option(TransportMode.TRAIN, door=700, amount=60)
    fast_dear = option(TransportMode.FLIGHT, door=240, amount=320, day_cost=0.1)
    shoestring = rank([slow_cheap, fast_dear], TransportPrefs(budget_level="shoestring"))
    luxury = rank([slow_cheap, fast_dear], TransportPrefs(budget_level="luxury"))
    assert shoestring is not None and luxury is not None
    assert shoestring.chosen_option_id == "train"
    assert luxury.chosen_option_id == "flight"


def test_disliked_mode_is_penalised():
    fly = option(TransportMode.FLIGHT, door=200, amount=100)
    train = option(TransportMode.TRAIN, door=250, amount=100)
    neutral = rank([fly, train], TransportPrefs())
    biased = rank(
        [fly, train],
        TransportPrefs(disliked_modes=frozenset({TransportMode.FLIGHT})),
    )
    assert neutral is not None and biased is not None
    assert neutral.chosen_option_id == "flight"
    assert biased.chosen_option_id == "train"
    assert "would rather not travel" in biased.rejected_because["flight"]


def test_near_identical_options_are_called_a_close_call():
    a = option(TransportMode.TRAIN, door=200, amount=100)
    b = option(TransportMode.COACH, door=203, amount=101)
    result = rank([a, b], TransportPrefs())
    assert result is not None
    assert result.rule_code == "close_call"


def test_per_traveller_and_per_party_fares_compare_on_the_same_basis():
    per_head = option(
        TransportMode.TRAIN, door=200, amount=50, basis=FareBasis.PER_TRAVELLER
    )
    whole_party = option(TransportMode.FLIGHT, door=200, amount=160, basis=FareBasis.PER_PARTY)
    assert party_total(per_head, 4) == 200
    assert party_total(whole_party, 4) == 160
    result = rank([per_head, whole_party], TransportPrefs(travellers=4))
    assert result is not None
    assert result.chosen_option_id == "flight"


def test_empty_comparison_returns_nothing():
    assert rank([], TransportPrefs()) is None


def test_lodging_option_does_not_require_transport_fields():
    stay = Option(
        id="liteapi:hotel-42:rate-7",
        label="Memmo Alfama",
        price=Price(amount=640, currency="EUR", basis=FareBasis.PER_PARTY),
        lodging=LodgingFacts(
            checkin="2026-10-02",
            checkout="2026-10-05",
            room_name="River view king",
            refundable=True,
            rating=4.7,
            provider_ref={"hotel_id": "hotel-42", "rate_id": "rate-7"},
        ),
    )

    payload = stay.model_dump(mode="json")
    assert payload["mode"] is None
    assert payload["lodging"]["rating"] == 4.7
    assert payload["lodging"]["provider_ref"]["rate_id"] == "rate-7"


def hotel(name: str, amount: float, *, rating: float | None, refundable: bool) -> HotelOffer:
    slug = name.lower().replace(" ", "-")
    return HotelOffer(
        provider="liteapi",
        provider_ref={"hotel_id": slug, "offer_id": f"offer-{slug}", "rate_id": "rate-1"},
        hotel_name=name,
        search_destination="Lisbon",
        room_name="King room",
        total=Money(amount=amount, currency="EUR"),
        refundable=refundable,
        quoted_at=datetime.now(UTC),
        rating=rating,
    )


def test_lodging_decision_keeps_the_exact_candidates_and_verified_rule():
    decision = build_lodging_decision(
        [
            hotel("Memmo Alfama", 640, rating=4.7, refundable=True),
            hotel("Hotel Mundial", 520, rating=4.5, refundable=True),
            hotel("Bairro Alto Hotel", 900, rating=None, refundable=False),
        ],
        destination="Lisbon",
        checkin="2026-10-02",
        checkout="2026-10-05",
        cached=False,
    )

    assert decision is not None
    assert decision.kind.value == "lodging"
    assert len(decision.options) == 3
    assert decision.chosen is not None and decision.chosen.label == "Hotel Mundial"
    assert decision.rule.code == "verified_stay_total"
    assert decision.option(decision.chosen_option_id).source.provider == "liteapi"


def test_lodging_decision_follows_the_property_the_agent_persisted():
    decision = build_lodging_decision(
        [
            hotel("Memmo Alfama", 640, rating=4.7, refundable=True),
            hotel("Hotel Mundial", 520, rating=4.5, refundable=True),
        ],
        destination="Lisbon",
        checkin="2026-10-02",
        checkout="2026-10-05",
        cached=False,
    )
    assert decision is not None and decision.chosen.label == "Hotel Mundial"
    plan = {
        "selected_hotels": [{"name": "Memmo Alfama"}],
        "decisions": [decision.model_dump(mode="json")],
    }

    reconcile_selected_lodging(plan)

    reconciled = plan["decisions"][0]
    chosen = next(
        option
        for option in reconciled["options"]
        if option["id"] == reconciled["chosen_option_id"]
    )
    assert chosen["label"] == "Memmo Alfama"


def _flight_offer(*, offer_id: str, amount: float, segments: list[dict]) -> FlightOffer:
    return FlightOffer(
        provider="stub-flights",
        provider_ref={"offer_id": offer_id},
        total=Money(amount=amount, currency="USD"),
        segments=segments,
        quoted_at=datetime.now(UTC),
    )


def _flight_decision(offers: list[FlightOffer]):
    return build_flight_decision(
        offers,
        origin="Delhi",
        destination="London",
        departure_date="2026-10-02",
        return_date="",
        cabin_class="ECONOMY",
        cached=False,
    )


def test_flight_decision_prefers_fewer_stops_before_price() -> None:
    direct = _flight_offer(
        offer_id="direct",
        amount=900,
        segments=[{"origin": "DEL", "destination": "LHR", "carrier": "Air India"}],
    )
    connecting = _flight_offer(
        offer_id="connecting",
        amount=650,
        segments=[
            {"origin": "DEL", "destination": "DXB", "carrier": "Emirates"},
            {"origin": "DXB", "destination": "LHR", "carrier": "Emirates"},
        ],
    )

    decision = _flight_decision([connecting, direct])

    assert decision is not None
    chosen = decision.option(decision.chosen_option_id)
    assert chosen is not None
    assert chosen.flight == FlightFacts(
        origin="Delhi",
        destination="London",
        departure_date="2026-10-02",
        cabin_class="ECONOMY",
        segments=[{"origin": "DEL", "destination": "LHR", "carrier": "Air India"}],
        stops=0,
        provider_ref={"offer_id": "direct"},
    )
    assert decision.rule.code == "flight_stops_then_total"
    rejected = next(option for option in decision.options if option.flight.stops == 1)
    assert "Adds 1 stop" in rejected.rejected_because


def test_flight_decision_uses_verified_total_to_break_stop_ties() -> None:
    decision = _flight_decision(
        [
            _flight_offer(
                offer_id="expensive",
                amount=900,
                segments=[{"origin": "DEL", "destination": "LHR", "carrier": "A"}],
            ),
            _flight_offer(
                offer_id="cheaper",
                amount=700,
                segments=[{"origin": "DEL", "destination": "LHR", "carrier": "B"}],
            ),
        ]
    )

    assert decision is not None
    chosen = decision.option(decision.chosen_option_id)
    assert chosen is not None and chosen.price is not None
    assert chosen.price.amount == 700
    assert chosen.source.provider == "stub-flights"
