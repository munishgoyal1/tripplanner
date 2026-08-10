from __future__ import annotations

from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.ops_metrics import record_model_call, record_request, reset, snapshot
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


def test_ops_overview_is_owner_only_and_hidden_from_openapi(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    owner = _client(monkeypatch, "OWNER@example.com")
    response = owner.get("/ops/overview")

    assert response.status_code == 200
    assert {"business", "requests", "models", "tools", "cache"} <= response.json().keys()
    assert "/ops/overview" not in owner.get("/openapi.json").json()["paths"]

    non_owner = _client(monkeypatch, "other@example.com")
    assert non_owner.get("/ops/overview").status_code == 404
    assert _client(monkeypatch).get("/ops/overview").status_code == 404


def test_provider_cache_status_reports_memory_redis_and_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    provider_cache._PROVIDER_CACHES.clear()
    settings = type("Settings", (), {"cache_redis_enabled": True})()
    monkeypatch.setattr(provider_cache, "get_settings", lambda: settings)

    memory = type(
        "Cache",
        (),
        {
            "status": lambda self: {
                "memory_entries": 2,
                "redis": {"enabled": True, "connected": False},
            }
        },
    )()
    provider_cache._PROVIDER_CACHES.add(memory)
    fallback = provider_cache.provider_cache_status()

    assert fallback == {
        "configured": True,
        "backend": "memory",
        "redis_connected": False,
        "fallback_active": True,
        "memory_entries": 2,
    }

    provider_cache._PROVIDER_CACHES.clear()
    redis_cache = type(
        "Cache",
        (),
        {
            "status": lambda self: {
                "memory_entries": 1,
                "redis": {"enabled": True, "connected": True},
            }
        },
    )()
    provider_cache._PROVIDER_CACHES.add(redis_cache)

    assert provider_cache.provider_cache_status()["backend"] == "redis"
