"""Applying and undoing a traveller's overrule of a recorded comparison."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tripplanner.decisions.apply import apply_override, restore
from tripplanner.decisions.models import (
    Decision,
    DecisionScope,
    DecisionState,
    FareBasis,
    Option,
    Price,
    Rule,
    TransportMode,
)
from tripplanner.decisions.store import find_decision, upsert_decision


def option(
    option_id: str,
    mode: TransportMode,
    label: str,
    *,
    amount: float | None = None,
    door: int = 300,
    duration: int = 180,
) -> Option:
    price = (
        Price(amount=amount, currency="EUR", basis=FareBasis.PER_PARTY)
        if amount is not None
        else None
    )
    return Option(
        id=option_id,
        mode=mode,
        label=label,
        price=price,
        duration_min=duration,
        door_to_door_min=door,
    )


def make_decision(options: list[Option], chosen: str) -> Decision:
    return Decision(
        id="dec_transport_mode_lisbon_porto",
        created_at=datetime.now(UTC),
        scope=DecisionScope(day=2, from_place="Lisbon", to_place="Porto", date="2026-05-04"),
        subject="Lisbon to Porto",
        rule=Rule(code="door_to_door_time", text="Fastest door to door."),
        chosen_option_id=chosen,
        options=options,
    )


@pytest.fixture
def plan() -> dict:
    return {
        "trip_id": "t1",
        "destination": "Portugal",
        "travelers": "2 adults",
        "currency": "EUR",
        "total_cost": 1000.0,
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Belem Tower", "kind": "attraction", "time": "10:00"}]},
            {
                "day": 2,
                "stops": [
                    {"name": "Breakfast", "kind": "meal", "time": "08:00"},
                    {
                        "name": "Train: Lisbon to Porto",
                        "kind": "transport",
                        "time": "09:00",
                        "duration_min": 165,
                        "price": 120.0,
                    },
                    {"name": "Livraria Lello", "kind": "attraction", "time": "14:00"},
                ],
            },
        ],
    }


@pytest.fixture
def seeded(plan: dict) -> dict:
    decision = make_decision(
        [
            option("opt_train", TransportMode.TRAIN, "Train", amount=120.0, door=300, duration=165),
            option("opt_air", TransportMode.FLIGHT, "Flight", amount=286.0, door=290, duration=60),
        ],
        "opt_train",
    )
    upsert_decision(plan, decision)
    return plan


def test_override_swaps_the_stop_and_moves_the_total(seeded: dict) -> None:
    result = apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")

    assert result.ok
    stop = seeded["day_wise_itinerary"][1]["stops"][1]
    assert stop["kind"] == "flight"
    assert stop["name"] == "Flight: Lisbon to Porto"
    assert stop["duration_min"] == 60
    assert stop["decision_id"] == "dec_transport_mode_lisbon_porto"
    assert result.delta == pytest.approx(166.0)
    assert seeded["total_cost"] == pytest.approx(1166.0)
    assert result.total_cost == pytest.approx(1166.0)


def test_override_shifts_only_the_stops_after_it(seeded: dict) -> None:
    apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")

    stops = seeded["day_wise_itinerary"][1]["stops"]
    assert stops[0]["time"] == "08:00"
    assert stops[1]["time"] == "09:00"
    # 165 minutes became 60, so the afternoon comes forward by 105.
    assert stops[2]["time"] == "12:15"
    assert seeded["day_wise_itinerary"][0]["stops"][0]["time"] == "10:00"


def test_override_records_who_chose_and_what_it_replaced(seeded: dict) -> None:
    apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")

    decision = find_decision(seeded, "dec_transport_mode_lisbon_porto")
    assert decision is not None
    assert decision.state == DecisionState.OVERRULED
    assert decision.override is not None
    assert decision.override.option_id == "opt_air"
    assert decision.override.previous_option_id == "opt_train"
    assert decision.active_option_id == "opt_air"
    assert decision.chosen_option_id == "opt_train"


def test_restore_returns_the_exact_prior_total_and_shape(seeded: dict) -> None:
    before_stop = dict(seeded["day_wise_itinerary"][1]["stops"][1])
    before_times = [s.get("time") for s in seeded["day_wise_itinerary"][1]["stops"]]

    apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")
    result = restore(seeded, "dec_transport_mode_lisbon_porto")

    assert result.ok
    assert seeded["total_cost"] == pytest.approx(1000.0)
    stops = seeded["day_wise_itinerary"][1]["stops"]
    assert [s.get("time") for s in stops] == before_times
    assert stops[1]["name"] == before_stop["name"]
    assert stops[1]["kind"] == before_stop["kind"]
    assert stops[1]["duration_min"] == before_stop["duration_min"]

    decision = find_decision(seeded, "dec_transport_mode_lisbon_porto")
    assert decision is not None
    assert decision.override is None
    assert decision.state == DecisionState.AGENT


def test_baseline_remembers_the_agents_own_price(seeded: dict) -> None:
    apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")
    assert seeded["cost_baseline"]["first"] == pytest.approx(1000.0)
    assert seeded["cost_baseline"]["current"] == pytest.approx(1166.0)
    assert seeded["cost_baseline"]["saved"] == pytest.approx(-166.0)

    restore(seeded, "dec_transport_mode_lisbon_porto")
    # `first` is what the agent planned. Undoing does not rewrite history.
    assert seeded["cost_baseline"]["first"] == pytest.approx(1000.0)
    assert seeded["cost_baseline"]["current"] == pytest.approx(1000.0)
    assert seeded["cost_baseline"]["saved"] == pytest.approx(0.0)


def test_unpriced_option_leaves_the_total_alone_and_says_so(plan: dict) -> None:
    decision = make_decision(
        [
            option("opt_train", TransportMode.TRAIN, "Train", amount=120.0),
            option("opt_coach", TransportMode.COACH, "Coach", amount=None, door=420, duration=380),
        ],
        "opt_train",
    )
    upsert_decision(plan, decision)

    result = apply_override(plan, "dec_transport_mode_lisbon_porto", "opt_coach")

    assert result.ok
    assert result.delta == 0.0
    assert plan["total_cost"] == pytest.approx(1000.0)
    assert any("no fare source" in w.lower() for w in result.warnings)


def test_conflicting_override_still_applies_and_warns(seeded: dict, monkeypatch) -> None:
    from tripplanner.tools import trip_guard

    monkeypatch.setattr(
        trip_guard,
        "validate_plan",
        lambda plan: [
            trip_guard.Violation(
                code="museum_closed",
                rule="opening_hours",
                message="Livraria Lello is shut when you would now arrive.",
                day=2,
            )
        ],
    )

    result = apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")

    assert result.ok
    assert seeded["day_wise_itinerary"][1]["stops"][1]["kind"] == "flight"
    assert any("Livraria Lello" in w for w in result.warnings)
    decision = find_decision(seeded, "dec_transport_mode_lisbon_porto")
    assert decision is not None and decision.override is not None
    assert any("Livraria Lello" in w for w in decision.override.warnings)


def test_unknown_decision_and_unknown_option_are_refused(seeded: dict) -> None:
    assert apply_override(seeded, "dec_nope", "opt_air").ok is False
    assert apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_ghost").ok is False
    assert seeded["total_cost"] == pytest.approx(1000.0)


def test_choosing_the_current_option_changes_nothing(seeded: dict) -> None:
    result = apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_train")

    assert result.ok
    assert result.delta == 0.0
    assert "cost_baseline" not in seeded
    decision = find_decision(seeded, "dec_transport_mode_lisbon_porto")
    assert decision is not None and decision.state == DecisionState.AGENT


def test_restore_without_an_override_is_a_no_op(seeded: dict) -> None:
    result = restore(seeded, "dec_transport_mode_lisbon_porto")

    assert result.ok
    assert seeded["total_cost"] == pytest.approx(1000.0)
    assert "cost_baseline" not in seeded


def test_missing_leg_updates_the_record_and_says_the_plan_moved_on(seeded: dict) -> None:
    seeded["day_wise_itinerary"][1]["stops"].pop(1)

    result = apply_override(seeded, "dec_transport_mode_lisbon_porto", "opt_air")

    assert result.ok
    assert any("no longer in the itinerary" in w for w in result.warnings)
    decision = find_decision(seeded, "dec_transport_mode_lisbon_porto")
    assert decision is not None and decision.active_option_id == "opt_air"
