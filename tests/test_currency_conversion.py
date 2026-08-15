"""Currency handling is pure once a rate table exists, so these use real numbers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tripplanner.decisions.models import FareBasis, Option, Price, TransportMode
from tripplanner.decisions.rules import TransportPrefs, rank
from tripplanner.providers import fx


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    """Never reach the rate service from a test; an unseeded currency has no rate."""
    fx.clear_cache()
    monkeypatch.setattr(fx, "_fetch", lambda base: None)
    yield
    fx.clear_cache()


def seed(base: str, rates: dict[str, float]) -> None:
    fx._cache.set(
        base,
        fx.RateTable(
            base=base, rates=rates, fetched_at=datetime.now(UTC), rate_date="2026-08-10"
        ).to_payload(),
    )


def option(
    mode: TransportMode,
    *,
    door: int,
    amount: float | None = None,
    currency: str = "EUR",
) -> Option:
    return Option(
        id=mode.value,
        mode=mode,
        label=mode.value,
        price=(
            Price(amount=amount, currency=currency, basis=FareBasis.PER_PARTY)
            if amount is not None
            else None
        ),
        door_to_door_min=door,
        day_cost=0.1,
    )


def test_same_currency_needs_no_rate():
    assert fx.convert(100.0, "EUR", "EUR") == 100.0


def test_a_missing_rate_returns_nothing_rather_than_parity():
    assert fx.convert(100.0, "EUR", "INR") is None


def test_a_known_rate_converts():
    seed("EUR", {"INR": 95.0})
    assert fx.convert(10.0, "EUR", "INR") == 950.0


def test_an_unknown_target_currency_returns_nothing():
    seed("EUR", {"USD": 1.1})
    assert fx.convert(10.0, "EUR", "INR") is None


def test_cross_currency_fares_are_compared_after_conversion():
    # 9500 INR is 100 EUR, so the slower train is genuinely the cheaper option.
    seed("EUR", {"INR": 95.0})
    seed("INR", {"EUR": 1 / 95.0})
    train = option(TransportMode.TRAIN, door=260, amount=9500, currency="INR")
    fly = option(TransportMode.FLIGHT, door=240, amount=300, currency="EUR")
    result = rank([train, fly], TransportPrefs(travellers=1))
    assert result is not None
    assert result.chosen_option_id == TransportMode.TRAIN.value


def test_without_a_rate_money_is_left_out_instead_of_mixing_units():
    # No seeded rate: 9500 INR must not be read as 9500 EUR and lose on price.
    train = option(TransportMode.TRAIN, door=260, amount=9500, currency="INR")
    fly = option(TransportMode.FLIGHT, door=240, amount=300, currency="EUR")
    result = rank([train, fly], TransportPrefs(travellers=1))
    assert result is not None
    assert result.chosen_option_id == TransportMode.FLIGHT.value
    # Ranking fell back to time alone, so the gap is the door-to-door difference.
    gap = (
        result.scores[TransportMode.TRAIN.value] - result.scores[TransportMode.FLIGHT.value]
    )
    assert gap == pytest.approx(20.0)
