"""Tests for per-tool metrics in observability.py + integration with the
cache wrapper in tools_cache.py."""

from __future__ import annotations

import pytest
from langchain_core.tools import tool

from tripplanner import observability as obs
from tripplanner import tools_cache as tc
from tripplanner import user_context


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    obs.reset_tool_metrics()
    tc.clear_local_cache()
    user_context.set_user_id("alice")
    monkeypatch.setattr("tripplanner.storage_cosmos.is_enabled", lambda: False)
    yield
    user_context.set_user_id("local")
    obs.reset_tool_metrics()
    tc.clear_local_cache()


def test_record_tool_call_counts_and_avg():
    obs.record_tool_call("foo", duration_ms=100, status="ok")
    obs.record_tool_call("foo", duration_ms=300, status="ok")
    snap = obs.tool_metrics_snapshot()
    assert snap["foo"]["calls"] == 2
    assert snap["foo"]["errors"] == 0
    assert snap["foo"]["avg_ms"] == 200.0
    assert snap["foo"]["error_rate"] == 0.0


def test_record_tool_call_tracks_errors_and_cache_hits():
    obs.record_tool_call("foo", duration_ms=50, status="ok", cache_hit=True)
    obs.record_tool_call("foo", duration_ms=50, status="ok", cache_hit=False)
    obs.record_tool_call("foo", duration_ms=10, status="error", error="ValueError")
    snap = obs.tool_metrics_snapshot()
    assert snap["foo"]["calls"] == 3
    assert snap["foo"]["errors"] == 1
    assert snap["foo"]["cache_hits"] == 1
    assert snap["foo"]["error_rate"] == round(1 / 3, 3)
    assert snap["foo"]["hit_rate"] == round(1 / 3, 3)


def test_tool_metrics_snapshot_returns_p50_and_p95():
    for ms in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        obs.record_tool_call("foo", duration_ms=ms, status="ok")
    snap = obs.tool_metrics_snapshot()
    # p50 should land in the middle of the window, p95 near the top.
    assert 40 <= snap["foo"]["p50_ms"] <= 60
    assert snap["foo"]["p95_ms"] >= snap["foo"]["p50_ms"]


def test_reset_tool_metrics_clears_table():
    obs.record_tool_call("foo", duration_ms=10, status="ok")
    obs.reset_tool_metrics()
    assert obs.tool_metrics_snapshot() == {}


def test_cache_wrapper_records_miss_then_hit():
    calls = {"n": 0}

    @tool
    def echo_search(q: str) -> str:
        """Fake search."""
        calls["n"] += 1
        return f"result:{q}"

    wrapped = tc.wrap_tools_with_cache([echo_search])[0]
    wrapped.invoke({"q": "paris"})
    wrapped.invoke({"q": "paris"})

    snap = obs.tool_metrics_snapshot()
    assert calls["n"] == 1  # second call was a cache hit
    m = snap["echo_search"]
    assert m["calls"] == 2
    assert m["cache_hits"] == 1
    assert m["hit_rate"] == 0.5


def test_cache_wrapper_records_error_status():
    @tool
    def boom_search(q: str) -> str:
        """Fake failing tool."""
        raise ValueError("boom")

    wrapped = tc.wrap_tools_with_cache([boom_search])[0]
    with pytest.raises(Exception):
        wrapped.invoke({"q": "x"})

    snap = obs.tool_metrics_snapshot()
    m = snap["boom_search"]
    assert m["calls"] == 1
    assert m["errors"] == 1
    assert m["error_rate"] == 1.0


def test_metrics_endpoint_returns_snapshot():
    from fastapi.testclient import TestClient

    from tripplanner.api import app

    obs.record_tool_call("foo", duration_ms=42, status="ok")
    client = TestClient(app)
    resp = client.get("/metrics/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert "foo" in data["tools"]
    assert data["tools"]["foo"]["calls"] == 1

