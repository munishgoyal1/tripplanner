from __future__ import annotations

from typing import Any

import pytest

from scripts import performance_baseline


class FakeClient:
    def __init__(self, statuses: list[int] | None = None) -> None:
        self.statuses = iter(statuses or [])
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        status = next(self.statuses, 200)
        return type("Response", (), {"status_code": status})()


def test_percentile_uses_nearest_rank() -> None:
    values = [float(value) for value in range(1, 21)]

    assert performance_baseline.percentile(values, 50) == 10.0
    assert performance_baseline.percentile(values, 95) == 19.0


def test_measure_scenario_excludes_warmups(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ticks = iter([0, 1_000_000, 1_000_000, 3_000_000, 3_000_000, 6_000_000])
    monkeypatch.setattr(performance_baseline.time, "perf_counter_ns", lambda: next(ticks))
    client = FakeClient()

    result = performance_baseline.measure_scenario(
        client,
        performance_baseline.SCENARIOS[0],
        samples=2,
        warmups=1,
    )

    assert result["samples"] == 2
    assert result["p50_ms"] == 2.0
    assert result["p95_ms"] == 3.0
    assert len(client.calls) == 3


def test_run_baseline_rejects_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def measure(_client, scenario, **_kwargs):  # type: ignore[no-untyped-def]
        return {
            "samples": 1,
            "errors": int(scenario.name == "trip_map"),
            "error_rate": 1.0 if scenario.name == "trip_map" else 0.0,
            "min_ms": 1.0,
            "mean_ms": 1.0,
            "p50_ms": 1.0,
            "p95_ms": 1.0,
            "max_ms": 1.0,
        }

    monkeypatch.setattr(performance_baseline, "measure_scenario", measure)

    with pytest.raises(
        performance_baseline.PerformanceRegressionError,
        match="trip_map",
    ):
        performance_baseline.run_baseline(FakeClient(), samples=1, warmups=0)


def test_hermetic_baseline_invokes_routes_and_records_zero_cost() -> None:
    report = performance_baseline.run_hermetic_baseline(
        samples=5,
        warmups=1,
        p95_limit_ms=750.0,
    )

    assert report["status"] == "passed"
    assert report["llm_usage"] == {"calls": 0, "cost_usd": 0.0}
    assert set(report["scenarios"]) == {
        "trip_view",
        "trip_map",
        "trip_itinerary",
        "stop_booked",
        "chat_json",
        "chat_sse",
    }
    assert report["chat_transport_parity"] == {
        "matched": True,
        "fields": ["reply", "agent", "trip_id"],
    }
    assert all(result["errors"] == 0 for result in report["scenarios"].values())
    assert all(result["p95_ms"] <= 750.0 for result in report["scenarios"].values())
