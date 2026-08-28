"""The cost ledger is pure over a plan dict, so these assert on real evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tripplanner.decisions.trip_cost import (
    LIVE,
    STALE,
    UNPRICED,
    UNVERIFIED,
    build_cost_ledger,
    compare_equivalent_offers,
    compare_trip_decisions,
    plan_price_rechecks,
)
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


def test_a_current_check_proves_the_quote_but_not_unknown_mandatory_costs():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [{"name": "LX Boutique", "price": 420}],
    }
    ledger = build_cost_ledger(plan)
    assert [line.status for line in ledger.lines] == [LIVE]
    assert ledger.priced_total == 420.0
    assert ledger.priced_count == 1
    assert ledger.complete is False
    assert ledger.all_in_total is None
    assert ledger.required_unknown == ("taxes and mandatory property fees",)
    assert ledger.lines[0].provider == "liteapi"
    assert ledger.summary == "1 live quote · final total not confirmed (1 unknown cost category)"


def test_an_explicit_all_in_quote_confirms_the_true_total():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [
            {
                "name": "LX Boutique",
                "price": 420,
                "source": {"provider": "liteapi"},
                "price_composition": {"all_in": True, "taxes": 40, "fees": 10},
            }
        ],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.complete is True
    assert ledger.all_in_total == 420.0
    assert ledger.lines[0].components == (
        {
            "kind": "taxes",
            "label": "Taxes",
            "amount": 40.0,
            "currency": "EUR",
            "inclusion": "included",
        },
        {
            "kind": "fees",
            "label": "Fees",
            "amount": 10.0,
            "currency": "EUR",
            "inclusion": "included",
        },
    )
    assert ledger.summary == "All-in total confirmed for 1 item."


def test_known_excluded_mandatory_cost_is_added_without_estimating():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "liteapi")],
        "selected_hotels": [
            {
                "name": "LX Boutique",
                "price": 420,
                "source": {"provider": "liteapi"},
                "price_composition": {
                    "mandatory_costs_complete": True,
                    "excluded": [{"kind": "city_tax", "label": "City tax", "amount": 25}],
                },
            }
        ],
    }
    ledger = build_cost_ledger(plan)
    assert ledger.priced_total == 420.0
    assert ledger.all_in_total == 445.0
    assert ledger.lines[0].components == (
        {
            "kind": "city_tax",
            "label": "City tax",
            "amount": 25.0,
            "currency": "EUR",
            "inclusion": "excluded",
        },
    )


def test_an_all_in_claim_requires_a_matching_item_provider_check():
    plan = {
        "currency": "EUR",
        "price_checks": [check("lodging", "other-provider")],
        "selected_hotels": [
            {
                "name": "LX Boutique",
                "price": 420,
                "source": {"provider": "liteapi"},
                "price_composition": {"all_in": True},
            }
        ],
    }

    ledger = build_cost_ledger(plan)

    assert ledger.lines[0].status == UNVERIFIED
    assert ledger.complete is False
    assert ledger.all_in_total is None
    assert ledger.required_unknown == ("taxes and mandatory property fees",)


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
    converted = next(line for line in ledger.lines if line.label == "Dollar Stay")
    assert converted.fx == {
        "from_currency": "USD",
        "to_currency": "EUR",
        "rate": 0.9,
        "source": "European Central Bank via Frankfurter",
        "rate_date": "2026-08-10",
        "fetched_at": converted.fx["fetched_at"],
    }


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
    assert ledger.as_dict()["coverage_pct"] == 50


def test_equivalent_cross_source_offers_compare_confirmed_all_in_totals():
    offers = [
        {
            "provider": "liteapi",
            "subject_key": "hotel:abc:2026-09-10:2026-09-13:room-deluxe",
            "label": "Deluxe room",
            "amount": 420,
            "currency": "EUR",
            "price_composition": {"all_in": True},
            "checked_at": datetime.now(UTC).isoformat(),
        },
        {
            "provider": "hotel-direct",
            "subject_key": "hotel:abc:2026-09-10:2026-09-13:room-deluxe",
            "label": "Deluxe room direct",
            "amount": 390,
            "currency": "EUR",
            "price_composition": {
                "mandatory_costs_complete": True,
                "excluded": [{"label": "City tax", "amount": 15}],
            },
            "checked_at": datetime.now(UTC).isoformat(),
        },
    ]

    comparison = compare_equivalent_offers(offers, target_currency="EUR")

    assert comparison[0]["recommended_provider"] == "hotel-direct"
    assert comparison[0]["recommended_all_in_total"] == 405
    assert comparison[0]["savings"] == 15
    assert comparison[0]["compared_providers"] == ["hotel-direct", "liteapi"]


def test_cross_source_comparison_withholds_savings_when_fees_are_unknown():
    offers = [
        {
            "provider": "one",
            "subject_key": "flight:blr-del:2026-09-10:economy",
            "amount": 100,
            "currency": "EUR",
            "price_composition": {"all_in": True},
        },
        {
            "provider": "two",
            "subject_key": "flight:blr-del:2026-09-10:economy",
            "amount": 80,
            "currency": "EUR",
            "price_composition": {},
        },
    ]

    comparison = compare_equivalent_offers(offers, target_currency="EUR")

    assert comparison[0]["recommended_provider"] == "one"
    assert comparison[0]["savings"] is None
    assert comparison[0]["excluded_providers"] == {"two": "mandatory costs are unresolved"}


def test_persisted_stay_decisions_compare_only_the_same_room_product():
    at = datetime.now(UTC).isoformat()

    def option(option_id: str, provider: str, room: str, amount: int) -> dict:
        return {
            "id": option_id,
            "label": "LX Boutique",
            "price": {
                "amount": amount,
                "currency": "EUR",
                "basis": "per_party",
                "all_in": True,
            },
            "lodging": {
                "checkin": "2026-09-10",
                "checkout": "2026-09-13",
                "room_name": room,
                "board_name": "Breakfast",
                "refundable": True,
            },
            "source": {"provider": provider, "checked_at": at},
        }

    plan = {
        "currency": "EUR",
        "decisions": [
            {
                "id": "dec_lodging_lisbon",
                "kind": "lodging",
                "created_at": at,
                "rule": {"code": "verified_stay_total", "text": "Lowest total"},
                "chosen_option_id": "lite-deluxe",
                "options": [
                    option("lite-deluxe", "liteapi", "Deluxe", 420),
                    option("direct-deluxe", "hotel-direct", "Deluxe", 390),
                    option("other-standard", "other", "Standard", 300),
                ],
            }
        ],
    }

    comparisons = compare_trip_decisions(plan)

    assert len(comparisons) == 1
    deluxe = comparisons[0]
    assert deluxe["recommended_provider"] == "hotel-direct"
    assert deluxe["savings"] == 30
    assert "other" not in deluxe["compared_providers"]


def test_finalized_unbooked_stale_prices_produce_explicit_recheck_tasks():
    plan = {
        "trip_id": "trip-1",
        "status": "finalized",
        "selected_hotels": [{"name": "LX Boutique", "booking_status": "planned"}],
        "price_checks": [check("lodging", "liteapi", minutes_ago=120, ttl_minutes=30)],
    }

    tasks = plan_price_rechecks(plan)

    assert tasks == [
        {
            "kind": "lodging",
            "provider": "liteapi",
            "reason": "finalized but unbooked quote expired",
        }
    ]


def test_consent_gated_offer_benefit_uses_terms_but_never_card_numbers():
    offers = [
        {
            "provider": "portal",
            "subject_key": "hotel:abc:2026-09-10:2026-09-13:room-deluxe",
            "amount": 400,
            "currency": "EUR",
            "price_composition": {"all_in": True},
        }
    ]
    benefits = [
        {
            "program": "Example Rewards",
            "card_label": "Example Premier",
            "card_number": "4111111111111111",
            "portal": "portal",
            "discount_percent": 10,
            "terms_url": "https://example.test/terms",
            "consent": True,
        }
    ]

    comparison = compare_equivalent_offers(
        offers,
        target_currency="EUR",
        benefits=benefits,
    )

    applied = comparison[0]["applied_benefit"]
    assert comparison[0]["recommended_all_in_total"] == 360
    assert applied == {
        "program": "Example Rewards",
        "card_label": "Example Premier",
        "discount": 40,
        "currency": "EUR",
        "terms_url": "https://example.test/terms",
    }
    assert "4111111111111111" not in str(comparison)
