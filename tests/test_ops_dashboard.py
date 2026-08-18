from __future__ import annotations

from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.ops_metrics import (
    record_chat_turn,
    record_model_call,
    record_product_event,
    record_request,
    reset,
    snapshot,
)
from tripplanner.providers import cache as provider_cache
from tripplanner.web import oauth

_SECRET = "ops-dashboard-test-secret"


def _client(monkeypatch, email: str | None = None) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    monkeypatch.setenv("WEB_SESSION_SECRET", _SECRET)
    monkeypatch.setenv("OPS_DASHBOARD_OWNER_EMAIL", "owner@example.com")
    client = TestClient(api.app)
    if email:
        client.cookies.set(
            oauth.SESSION_COOKIE,
            oauth.make_session_token("google-owner", "Owner", email, ""),
        )
    return client


def test_ops_metrics_snapshot_counts_errors_and_percentiles() -> None:
    reset()
    record_request("GET", "/health", 200, 10)
    record_request("GET", "/health", 500, 30)
    record_model_call("test-model", "ok", 20)

    result = snapshot()

    assert result["requests"]["calls"] == 2
    assert result["requests"]["errors"] == 1
    assert result["requests"]["p50_ms"] == 10
    assert result["requests"]["p95_ms"] == 30
    assert result["models"]["calls"] == 1


def test_ops_metrics_snapshot_aggregates_privacy_safe_chat_turns() -> None:
    reset()
    record_chat_turn("user-a@example.com", "completed", 1000, tool_calls=3)
    record_chat_turn("user-a@example.com", "error", 2000, tool_calls=1)
    record_chat_turn("user-b@example.com", "completed", 4000)

    result = snapshot()["chat_turns"]

    assert result == {
        "calls": 3,
        "completed": 2,
        "errors": 1,
        "distinct_users": 2,
        "p50_ms": 2000,
        "p95_ms": 4000,
        "tool_calls": 4,
        "avg_tools_per_turn": 1.3,
        "outcomes": {"completed": 2, "error": 1},
    }


def test_ops_metrics_snapshot_aggregates_product_funnel_and_drop_offs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reset()
    times = iter([100.0, 130.0, 160.0, 200.0, 220.0, 400.0, 400.0])
    monkeypatch.setattr("tripplanner.ops_metrics.time.time", lambda: next(times))
    record_product_event("page_view", "session-a", country="us", source="search")
    record_product_event("planning_started", "session-a", country="us", source="search")
    record_product_event("trip_created", "session-a", country="us", source="search")
    record_product_event("planning_completed", "session-a", country="us", source="search")
    record_product_event("page_view", "session-b", source="direct")
    record_product_event("planning_failed", "session-b", source="direct")

    result = snapshot()["product"]

    assert result["sessions"] == 2
    assert result["users"] == 2
    assert result["engagement_seconds"] == 280
    assert result["funnel"] == {
        "page_view": 2,
        "planning_started": 1,
        "trip_created": 1,
        "planning_completed": 1,
    }
    assert result["drop_offs"] == {"planning_failed": 1}
    assert result["countries"] == {"US": 1, "unknown": 1}
    assert result["sources"] == {"search": 1, "direct": 1}


def test_ops_overview_is_owner_only_and_hidden_from_openapi(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    owner = _client(monkeypatch, "OWNER@example.com")
    response = owner.get("/ops/overview")

    assert response.status_code == 200
    assert {"business", "requests", "models", "tools", "cache"} <= response.json().keys()
    assert "/ops/overview" not in owner.get("/openapi.json").json()["paths"]
    assert "/analytics/event" not in owner.get("/openapi.json").json()["paths"]

    non_owner = _client(monkeypatch, "other@example.com")
    assert non_owner.get("/ops/overview").status_code == 404
    assert _client(monkeypatch).get("/ops/overview").status_code == 404


def test_ops_overview_is_reachable_on_a_local_run(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setenv("WEB_SESSION_SECRET", _SECRET)
    monkeypatch.setenv("OPS_DASHBOARD_OWNER_EMAIL", "owner@example.com")

    response = TestClient(api.app).get("/ops/overview")

    assert response.status_code == 200
    assert {"business", "requests", "models"} <= response.json().keys()


def test_analytics_event_records_only_allowlisted_content_free_fields(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reset()
    client = _client(monkeypatch, "owner@example.com")

    response = client.post(
        "/analytics/event",
        json={
            "event": "trip_created",
            "session_id": "session-1234",
            "source": "search",
            "destination": "must-not-be-recorded",
        },
    )
    client.post(
        "/analytics/event",
        json={"event": "unsupported", "session_id": "session-1234"},
    )

    assert response.status_code == 204
    product = snapshot()["product"]
    assert product["activities"] == {"trip_created": 1}
    assert product["users"] == 1
    assert product["sources"] == {"search": 1}


def test_provider_cache_status_reports_memory_redis_and_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner import caching

    monkeypatch.setattr(caching, "_REGISTRY", {})
    settings = type(
        "Settings",
        (),
        {"cache_redis_enabled": True, "cache_redis_namespace": "tripplanner:test"},
    )()

    # Redis selected but unreachable: the request still gets a cache, and the
    # dashboard has to say so rather than claim Redis is serving.
    fallback_backend = caching.RedisBackend.__new__(caching.RedisBackend)
    fallback_backend._mirror = caching.MemoryBackend()
    fallback_backend._client = None
    fallback_backend._down_since = None
    monkeypatch.setattr(caching, "_BACKEND", fallback_backend)
    monkeypatch.setattr(caching, "get_settings", lambda: settings)

    caching.get_cache("probe").set("a", 1)
    caching.get_cache("probe").set("b", 2)
    fallback = provider_cache.provider_cache_status()

    assert fallback["configured"] is True
    assert fallback["backend"] == "memory"
    assert fallback["redis_connected"] is False
    assert fallback["fallback_active"] is True
    assert fallback["memory_entries"] == 2
    assert fallback["redis_entries"] == 0

    monkeypatch.setattr(caching, "_REGISTRY", {})
    monkeypatch.setattr(caching, "_BACKEND", caching.MemoryBackend())
    memory_only = provider_cache.provider_cache_status()

    assert memory_only["backend"] == "memory"
    assert memory_only["fallback_active"] is False


def test_provider_cache_status_reports_redis_when_it_answers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner import caching

    class Answering:
        def scan_iter(self, **_kwargs):
            yield b"tripplanner:probe:a"

        def memory_usage(self, _key):
            return 64

    monkeypatch.setattr(caching, "_REGISTRY", {})
    backend = caching.RedisBackend.__new__(caching.RedisBackend)
    backend._mirror = caching.MemoryBackend()
    backend._client = Answering()
    backend._down_since = None
    monkeypatch.setattr(caching, "_BACKEND", backend)

    status = provider_cache.provider_cache_status()

    assert status["backend"] == "redis"
    assert status["redis_connected"] is True
    assert status["redis_entries"] == 1
    assert status["redis_bytes"] == 64
