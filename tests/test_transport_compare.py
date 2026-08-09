"""The comparison tool: fan-out, fallbacks and the ceilings that keep it cheap."""

from __future__ import annotations

import json

import pytest

from tripplanner.decisions.models import FareBasis, TransportMode
from tripplanner.decisions.store import list_decisions
from tripplanner.providers import fares
from tripplanner.providers.fares import FareQuote
from tripplanner.tools import transport_compare
from tripplanner.tools.transport_compare import compare_transport_options


class StubSource:
    def __init__(self, name, modes, amount=None, currency="EUR"):
        self.name = name
        self.modes = frozenset(modes)
        self._amount = amount
        self._currency = currency

    def quote(self, request):
        if self._amount is None:
            return None
        return FareQuote(
            amount=self._amount,
            currency=self._currency,
            provider=self.name,
            basis=FareBasis.PER_PARTY,
        )


@pytest.fixture(autouse=True)
def isolated_tool(monkeypatch):
    """No network, no shared state leaking between cases."""
    transport_compare._cache.clear()
    transport_compare.reset_turn_budget()

    saved: dict = {}

    def fake_metrics(origin, destination, mode):
        return {
            "DRIVE": {"mode": "DRIVE", "duration_min": 190, "distance_km": 313.0},
            "TRANSIT": {"mode": "TRANSIT", "duration_min": 165, "distance_km": 313.0},
        }.get(mode)

    monkeypatch.setattr(transport_compare, "route_metrics", fake_metrics)

    from tripplanner.tools import trip_planner

    monkeypatch.setattr(
        trip_planner, "load_active_trip_dict", lambda: {"currency": "EUR", "decisions": []}
    )
    monkeypatch.setattr(
        trip_planner,
        "record_trip_decision",
        lambda decision: saved.update({"decision": decision}) or True,
    )
    yield saved
    transport_compare._cache.clear()
    transport_compare.reset_turn_budget()


@pytest.fixture(autouse=True)
def no_ambient_ground_providers(monkeypatch):
    """Keep comparison output driven by stub sources, not by a configured provider."""
    for getter in ("get_train_provider", "get_coach_provider", "get_ferry_provider"):
        monkeypatch.setattr(fares, getter, lambda: None)
    # The fare cache is process-global; one test's stub quote must not answer the next.
    fares._FARE_CACHE.clear()
    yield
    fares._FARE_CACHE.clear()


@pytest.fixture
def air_source():
    source = StubSource("stub-air", {TransportMode.FLIGHT}, amount=286)
    fares.register_source(source)
    yield source
    fares.unregister_source("stub-air")


def run(**kwargs) -> dict:
    defaults = {
        "from_place": "Lisbon",
        "to_place": "Porto",
        "date": "2026-05-04",
        "travellers": 2,
        "day": 3,
    }
    return json.loads(compare_transport_options.invoke({**defaults, **kwargs}))


def test_every_mode_is_compared_and_the_losers_are_kept(isolated_tool, air_source):
    result = run()
    modes = {option["mode"] for option in result["options"]}
    assert modes == {"road", "train", "flight"}
    explained = [o for o in result["options"] if o["rejected_because"]]
    assert len(explained) == 2


def test_rail_comes_back_unpriced_rather_than_estimated(isolated_tool, air_source):
    result = run()
    rail = next(o for o in result["options"] if o["mode"] == "train")
    assert rail["price"] is None
    assert rail["unpriced_reason"] == "out_of_coverage"
    assert rail["door_to_door_min"] > 0
    assert result["priced"] == "partial"


def test_the_flight_is_priced_from_its_source(isolated_tool, air_source):
    result = run()
    flight = next(o for o in result["options"] if o["mode"] == "flight")
    assert flight["price"] == {"amount": 286.0, "currency": "EUR"}


def test_with_no_fare_source_at_all_nothing_is_priced(isolated_tool):
    result = run()
    assert result["priced"] == "none"
    assert all(option["price"] is None for option in result["options"])


def test_the_decision_is_recorded_on_the_trip(isolated_tool, air_source):
    result = run()
    decision = isolated_tool["decision"]
    assert decision.id == result["decision_id"]
    assert decision.scope.from_place == "Lisbon"
    assert decision.scope.day == 3
    assert decision.rule.text
    assert len(decision.options) == 3
    plan: dict = {}
    from tripplanner.decisions.store import upsert_decision

    upsert_decision(plan, decision)
    assert len(list_decisions(plan)) == 1


def test_a_short_hop_is_not_worth_comparing(isolated_tool, monkeypatch):
    monkeypatch.setattr(
        transport_compare,
        "route_metrics",
        lambda origin, destination, mode: (
            {"mode": mode, "duration_min": 25, "distance_km": 18.0} if mode == "DRIVE" else None
        ),
    )
    out = compare_transport_options.invoke(
        {"from_place": "Lisbon", "to_place": "Sintra", "date": "2026-05-04"}
    )
    assert "too short to be worth" in out


def test_air_is_not_offered_on_a_short_ground_hop(isolated_tool, air_source, monkeypatch):
    monkeypatch.setattr(
        transport_compare,
        "route_metrics",
        lambda origin, destination, mode: {
            "mode": mode,
            "duration_min": 80,
            "distance_km": 90.0,
        },
    )
    result = run(to_place="Obidos")
    assert "flight" not in {option["mode"] for option in result["options"]}


def test_the_second_identical_call_is_served_from_cache(isolated_tool, air_source):
    first = run()
    calls: list[str] = []
    original = transport_compare.route_metrics

    def counting(origin, destination, mode):
        calls.append(mode)
        return original(origin, destination, mode)

    transport_compare.route_metrics = counting
    try:
        second = run()
    finally:
        transport_compare.route_metrics = original
    assert calls == []
    assert second["decision_id"] == first["decision_id"]


def test_the_per_turn_ceiling_stops_runaway_comparisons(isolated_tool, air_source):
    for index in range(transport_compare.MAX_COMPARISONS_PER_TURN):
        run(to_place=f"City{index}")
    out = compare_transport_options.invoke(
        {"from_place": "Lisbon", "to_place": "Faro", "date": "2026-05-04"}
    )
    assert "budget for this turn" in out


def test_a_failed_ground_route_degrades_instead_of_raising(isolated_tool, monkeypatch):
    monkeypatch.setattr(
        transport_compare, "route_metrics", lambda origin, destination, mode: None
    )
    out = compare_transport_options.invoke(
        {"from_place": "Lisbon", "to_place": "Porto", "date": "2026-05-04"}
    )
    assert "Could not compare this hop" in out
