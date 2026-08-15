"""The cost ledger is pure over a plan dict, so these assert on real evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tripplanner.decisions.trip_cost import LIVE, STALE, UNPRICED, UNVERIFIED, build_cost_ledger
from tripplanner.providers import fx


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    fx.clear_cache()
    monkeypatch.setattr(fx, "_fetch", lambda base: None)
    yield
    fx.clear_cache()


def check(kind: str, provider: str, *, minutes_ago: int = 0, ttl_minutes: int = 60) -> dict:
    at = datetime.now() - timedelta(minutes=minutes_ago)
    return {
        "kind": kind,
        "provider": provider,
        "checked_at": at.isoformat(timespec="seconds"),
        "expires_at": (at + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds"),
    }


def test_an_empty_plan_has_nothing_to_claim():
    ledger = build_cost_ledger(None)
    assert ledger.lines == []
    assert ledger.priced_total is None
    assert ledger.complete is False
    assert ledger.summary == ""


def test_a_current_check_makes_its_items_priced():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [{"name": "LX Boutique", "price": 420}],
    }
    ledger = build_cost_ledger(plan)
    assert [line.status for line in ledger.lines] == [LIVE]
    assert ledger.priced_total == 420.0
    assert ledger.priced_count == 1
    assert ledger.complete is True
    assert ledger.lines[0].provider == "liteapi"


def test_an_expired_check_makes_its_items_stale_and_unpriced_in_the_total():
    plan = {
        "currency": "EUR",
        "price_checks": [check("flights", "duffel", minutes_ago=120, ttl_minutes=30)],
        "selected_flights": [{"airline": "TAP", "price": 180}],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.lines[0].status == STALE
    assert ledger.priced_total is None
    assert ledger.stale_count == 1
    assert ledger.complete is False


def test_a_number_with_no_check_behind_it_is_unverified():
    plan = {"currency": "EUR", "selected_hotels": [{"name": "Unknown Inn", "price": 300}]}
    ledger = build_cost_ledger(plan)
    assert ledger.lines[0].status == UNVERIFIED
    assert ledger.priced_total is None
    assert ledger.unverified_count == 1


def test_an_item_with_no_price_is_unpriced_and_says_why():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [{"name": "Somewhere"}],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.lines[0].status == UNPRICED
    assert ledger.lines[0].reason == "no price recorded for this item"


def test_two_currencies_are_converted_before_being_added():
    fx._cache.set(
        "USD",
        fx.RateTable(
            base="USD", rates={"EUR": 0.9}, fetched_at=datetime.now(UTC), rate_date="2026-08-10"
        ).to_payload(),
    )
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [
            {"name": "Euro Stay", "price": 100},
            {"name": "Dollar Stay", "price": 200, "currency": "USD"},
        ],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.priced_total == 280.0
    assert all(line.currency == "EUR" for line in ledger.lines)


def test_without_a_rate_the_line_is_unpriced_rather_than_summed_wrongly():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [
            {"name": "Euro Stay", "price": 100},
            {"name": "Rupee Stay", "price": 9000, "currency": "INR"},
        ],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.priced_total == 100.0
    unpriced = [line for line in ledger.lines if line.status == UNPRICED]
    assert len(unpriced) == 1
    assert "no published INR->EUR rate" in unpriced[0].reason


def test_the_summary_names_what_is_not_backed():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [{"name": "Priced", "price": 100}, {"name": "No price"}],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.summary == "1 priced · 1 unpriced"
    assert ledger.as_dict()["complete"] is False
