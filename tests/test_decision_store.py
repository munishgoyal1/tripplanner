"""Decisions live on the trip document; these are the limits that keep them small."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tripplanner.decisions.models import (
    Decision,
    DecisionState,
    Effect,
    Option,
    OverrideRecord,
    Price,
    Rule,
    TransportMode,
    UnpricedReason,
    make_decision_id,
)
from tripplanner.decisions.store import (
    MAX_DECISIONS_PER_TRIP,
    MAX_OPTIONS_PER_DECISION,
    find_decision,
    list_decisions,
    prune_decisions,
    upsert_decision,
)


def make_decision(
    decision_id: str = "dec_a",
    *,
    options: int = 2,
    created_at: datetime | None = None,
    chosen: str = "train",
) -> Decision:
    modes = list(TransportMode)[:options]
    return Decision(
        id=decision_id,
        created_at=created_at or datetime.now(UTC),
        rule=Rule(code="door_to_door_time", text="Whole-journey time"),
        chosen_option_id=chosen,
        options=[
            Option(id=mode.value, mode=mode, label=mode.value, door_to_door_min=100)
            for mode in modes
        ],
        effect=Effect(total_cost=100, currency="EUR"),
    )


def test_option_without_a_price_is_marked_unpriced_with_a_reason():
    option = Option(id="train", mode=TransportMode.TRAIN, label="Train")
    assert option.priced is False
    assert option.unpriced_reason is UnpricedReason.NO_SOURCE


def test_option_with_a_price_carries_no_unpriced_reason():
    option = Option(
        id="flight",
        mode=TransportMode.FLIGHT,
        label="Fly",
        price=Price(amount=180, currency="EUR"),
        unpriced_reason=UnpricedReason.NO_SOURCE,
    )
    assert option.priced is True
    assert option.unpriced_reason is None


def test_decision_ids_are_deterministic():
    first = make_decision_id("transport", "Lisbon", "Porto", "2026-05-04")
    second = make_decision_id("transport", "  lisbon ", "PORTO", "2026-05-04")
    assert first == second == "dec_transport_lisbon_porto_2026_05_04"


def test_upsert_replaces_rather_than_duplicates():
    plan: dict = {}
    upsert_decision(plan, make_decision("dec_a", chosen="train"))
    upsert_decision(plan, make_decision("dec_a", chosen="flight"))
    stored = list_decisions(plan)
    assert len(stored) == 1
    assert stored[0].chosen_option_id == "flight"


def test_upsert_preserves_a_user_override_across_a_refresh():
    plan: dict = {}
    upsert_decision(plan, make_decision("dec_a", chosen="train"))
    stored = list_decisions(plan)[0]
    overruled = stored.model_copy(
        update={
            "override": OverrideRecord(
                option_id="flight", at=datetime.now(UTC), previous_option_id="train"
            ),
            "state": DecisionState.OVERRULED,
        }
    )
    upsert_decision(plan, overruled)

    upsert_decision(plan, make_decision("dec_a", chosen="train"))
    refreshed = find_decision(plan, "dec_a")
    assert refreshed is not None
    assert refreshed.active_option_id == "flight"
    assert refreshed.state.value == "overruled"


def test_options_are_capped_but_the_active_one_is_always_kept():
    decision = make_decision("dec_a", options=7, chosen="metro")
    pruned = prune_decisions([decision])[0]
    assert len(pruned.options) == MAX_OPTIONS_PER_DECISION
    assert pruned.option("metro") is not None


def test_trip_is_capped_and_overruled_decisions_survive_the_cull():
    base = datetime.now(UTC)
    decisions = [
        make_decision(f"dec_{i}", created_at=base + timedelta(minutes=i))
        for i in range(MAX_DECISIONS_PER_TRIP + 5)
    ]
    decisions[0] = decisions[0].model_copy(
        update={
            "override": OverrideRecord(
                option_id="flight", at=base, previous_option_id="train"
            ),
            "state": DecisionState.OVERRULED,
        }
    )
    pruned = prune_decisions(decisions)
    assert len(pruned) == MAX_DECISIONS_PER_TRIP
    assert any(d.id == "dec_0" for d in pruned)


def test_malformed_records_are_skipped_rather_than_breaking_the_trip():
    plan = {"decisions": [{"nope": True}, "not a dict"]}
    assert list_decisions(plan) == []
