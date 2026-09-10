"""Tests for src/tripplanner/alert_events.py — durable alert-condition capture."""

from __future__ import annotations

import importlib

import pytest

from tripplanner import alert_events as ae


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setattr("tripplanner.storage_cosmos.is_enabled", lambda: False)
    importlib.reload(ae)
    ae.reset_for_tests()

    clock = {"t": 0.0}
    monkeypatch.setattr(ae, "_now", lambda: clock["t"])
    yield clock
    ae.reset_for_tests()


def test_thresholds_are_sourced_from_billing_guardrails_json():
    # window/severity for the four KQL-derived signals must match the JSON
    # this module claims to read, not a hardcoded duplicate.
    assert ae._window_seconds("chat_latency_burn", 0) == 15 * 60
    assert ae._severity("chat_latency_burn", 0) == 2
    assert ae._severity("cache_degradation", 0) == 3
    threshold, window, severity = ae._cosmos_throttling_config()
    assert (threshold, window, severity) == (20, 15 * 60, 3)


def test_chat_latency_burn_fires_then_resolves(_isolated):
    clock = _isolated
    for _ in range(ae._CHAT_LATENCY_MIN_SAMPLES):
        ae.observe("chat_operation", {"outcome": "completed", "duration_ms": 200_000})
        clock["t"] += 1
    fired = ae.recent(days=1)
    assert any(r["signal"] == "chat_latency_burn" for r in fired)

    # Age the slow burst out of the window, then feed fast turns -- p95 should
    # drop back under threshold and the open record should resolve.
    clock["t"] += 1000
    for _ in range(ae._CHAT_LATENCY_MIN_SAMPLES):
        ae.observe("chat_operation", {"outcome": "completed", "duration_ms": 100})
        clock["t"] += 1
    snap = ae.snapshot(days=1)
    assert snap["by_signal"]["chat_latency_burn"]["resolved"] >= 1


def test_model_throttling_requires_both_count_and_rate(_isolated):
    clock = _isolated
    # 5 samples, 1 throttle => below MIN_COUNT(2) and below MIN_RATE(0.2*5=1) borderline; use 1/5=0.2 but count<2
    for i in range(5):
        ae.observe(
            "chat_operation",
            {"outcome": "rate_limited" if i == 0 else "completed", "duration_ms": 10},
        )
        clock["t"] += 1
    assert not any(r["signal"] == "model_throttling" for r in ae.recent(days=1))

    ae.reset_for_tests()
    for i in range(5):
        ae.observe(
            "chat_operation",
            {"outcome": "rate_limited" if i < 2 else "completed", "duration_ms": 10},
        )
        clock["t"] += 1
    assert any(r["signal"] == "model_throttling" for r in ae.recent(days=1))


def test_provider_circuit_open_requires_signals_spread_over_span(_isolated):
    clock = _isolated
    for _ in range(ae._CIRCUIT_OPEN_MIN_SIGNALS):
        ae.observe("outbound_call", {"status": "circuit_open", "provider": "tavily"})
        clock["t"] += 1  # too close together -- span requirement not met
    assert not any(r["signal"] == "provider_circuit_open" for r in ae.recent(days=1))

    ae.reset_for_tests()
    for _ in range(ae._CIRCUIT_OPEN_MIN_SIGNALS):
        ae.observe("outbound_call", {"status": "circuit_open", "provider": "tavily"})
        clock["t"] += ae._CIRCUIT_OPEN_MIN_SPAN_SEC / (ae._CIRCUIT_OPEN_MIN_SIGNALS - 1)
    records = ae.recent(days=1)
    assert any(r["signal"] == "provider_circuit_open" and r["key"] == "tavily" for r in records)


def test_cache_degradation_fires_on_high_miss_rate(_isolated):
    clock = _isolated
    for i in range(ae._CACHE_DEGRADATION_MIN_ACCESSES):
        ae.observe("cache_access", {"result": "miss" if i % 2 == 0 else "hit"})
        clock["t"] += 1
    assert any(r["signal"] == "cache_degradation" for r in ae.recent(days=1))


def test_cosmos_throttling_uses_json_threshold(_isolated):
    clock = _isolated
    threshold, _window, _severity = ae._cosmos_throttling_config()
    for _ in range(threshold):
        ae.observe(
            "storage_operation",
            {"store": "cosmos", "status": "error", "status_code": 429},
        )
        clock["t"] += 1
    assert any(r["signal"] == "cosmos_throttling" for r in ae.recent(days=1))


def test_gcp_quota_exceeded_fires_on_any_429(_isolated):
    ae.observe(
        "outbound_call",
        {"provider": "google", "endpoint": "places.googleapis.com", "http_status": 429},
    )
    records = ae.recent(days=1)
    assert any(r["signal"] == "gcp_quota_exceeded" for r in records)


def test_application_failure_fires_from_tool_error(_isolated):
    ae.observe("tool_call", {"status": "error"})
    assert any(r["signal"] == "application_failure" for r in ae.recent(days=1))


def test_application_failure_fires_from_error_log_record(_isolated):
    ae.observe_log_record("ERROR")
    assert any(r["signal"] == "application_failure" for r in ae.recent(days=1))


def test_application_failure_ignores_info_log_record(_isolated):
    ae.observe_log_record("INFO")
    assert not any(r["signal"] == "application_failure" for r in ae.recent(days=1))


def test_observe_never_raises_on_bad_input(_isolated):
    ae.observe("chat_operation", {"duration_ms": "not-a-number"})
    ae.observe("outbound_call", {})
    ae.observe("unknown_kind", {"whatever": object()})


def test_snapshot_counts_by_signal(_isolated):
    ae.observe("tool_call", {"status": "error"})
    snap = ae.snapshot(days=1)
    assert snap["by_signal"]["application_failure"]["fired"] == 1
    assert snap["total_fired"] >= 1
