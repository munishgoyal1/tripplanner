"""Ranking is pure, so these are real assertions on real numbers — no mocks."""

from __future__ import annotations

from tripplanner.decisions.models import FareBasis, Option, Price, TransportMode
from tripplanner.decisions.rules import TransportPrefs, party_total, rank


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
