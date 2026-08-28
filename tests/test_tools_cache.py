"""Tests for the tool result cache (tripplanner.tools_cache)."""

from __future__ import annotations

import time

import pytest
from langchain_core.tools import tool

from tripplanner import tools_cache, user_context


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Each test starts with an empty local cache and a fixed user id.

    Cosmos is force-disabled here so the cache path is fully deterministic
    and doesn't reach for a real Azure account.
    """
    tools_cache.clear_local_cache()
    user_context.set_user_id("alice")
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    yield
    tools_cache.clear_local_cache()
    user_context.set_user_id("local")


def test_canonical_args_stable_across_key_order():
    a = tools_cache._cache_key("web_search", {"query": "paris", "limit": 5}, scope="global")
    b = tools_cache._cache_key("web_search", {"limit": 5, "query": "paris"}, scope="global")
    assert a == b


def test_cache_lookup_returns_none_for_miss():
    assert tools_cache.cache_lookup("web_search", {"q": "x"}) is None


def test_cache_store_then_lookup_returns_value():
    tools_cache.cache_store("web_search", {"q": "x"}, "first hit")
    assert tools_cache.cache_lookup("web_search", {"q": "x"}) == "first hit"


def test_google_tool_cache_uses_places_specific_ttl(monkeypatch):
    from tripplanner.config import get_settings

    captured: list[int] = []
    monkeypatch.setattr(
        tools_cache,
        "_local_set",
        lambda _user_id, _key, _value, ttl: captured.append(ttl),
    )
    monkeypatch.setattr(
        get_settings(),
        "google_places_search_cache_ttl_sec",
        86400,
    )

    tools_cache.cache_store("search_places_with_reviews", {"query": "Paris"}, "result")

    assert captured == [86400]


def test_stateful_tools_are_never_cached():
    # Even if the caller pushes a value in, lookups still miss because the
    # store is a no-op for the stateful allow-list.
    tools_cache.cache_store("update_trip_plan", {"x": 1}, "should not save")
    assert tools_cache.cache_lookup("update_trip_plan", {"x": 1}) is None


def test_cache_expires_after_ttl():
    tools_cache.cache_store("web_search", {"q": "x"}, "fresh", ttl=1)
    # Move clock forward past expiry.
    real_time = time.time
    later = real_time() + 5
    import tripplanner.tools_cache as tc

    tc.time.time = lambda: later  # type: ignore[assignment]
    try:
        assert tools_cache.cache_lookup("web_search", {"q": "x"}) is None
    finally:
        tc.time.time = real_time  # type: ignore[assignment]


def test_cache_isolates_users():
    tools_cache.cache_store("get_trip_plan", {}, "alice-plan")
    user_context.set_user_id("bob")
    assert tools_cache.cache_lookup("get_trip_plan", {}) is None
    user_context.set_user_id("alice")
    assert tools_cache.cache_lookup("get_trip_plan", {}) == "alice-plan"


def test_global_cache_shares_across_users():
    tools_cache.cache_store("web_search", {"query": "paris"}, "global-hit")
    user_context.set_user_id("bob")
    assert tools_cache.cache_lookup("web_search", {"query": "paris"}) == "global-hit"


def test_global_cache_key_normalizes_case_and_whitespace():
    tools_cache.cache_store("web_search", {"query": "  Paris  "}, "normalized")
    assert tools_cache.cache_lookup("web_search", {"query": "paris"}) == "normalized"


def test_coerce_result_handles_dict_and_list():
    assert tools_cache._coerce_result("plain") == "plain"
    assert tools_cache._coerce_result({"a": 1}) == '{"a": 1}'
    assert tools_cache._coerce_result([1, 2]) == "[1, 2]"


def test_wrap_tools_calls_underlying_once_per_unique_arg_set():
    calls = {"n": 0}

    @tool
    def fake_search(query: str) -> str:
        """A fake search tool used to verify caching."""
        calls["n"] += 1
        return f"results for {query}"

    [wrapped] = tools_cache.wrap_tools_with_cache([fake_search])

    # First call → underlying runs; second identical call → cache hit.
    assert wrapped.invoke({"query": "paris"}) == "results for paris"
    assert wrapped.invoke({"query": "paris"}) == "results for paris"
    assert calls["n"] == 1
    # Different args → fresh call.
    assert wrapped.invoke({"query": "rome"}) == "results for rome"
    assert calls["n"] == 2


def test_refresh_bypasses_lookup_and_does_not_store_result():
    calls = {"n": 0}

    @tool
    def search_hotels(city: str, refresh: bool = False) -> str:
        """Return a changing hotel quote for refresh-cache testing."""
        calls["n"] += 1
        return f"quote-{calls['n']}"

    [wrapped] = tools_cache.wrap_tools_with_cache([search_hotels])

    assert wrapped.invoke({"city": "Paris"}) == "quote-1"
    assert wrapped.invoke({"city": "Paris"}) == "quote-1"
    assert wrapped.invoke({"city": "Paris", "refresh": True}) == "quote-2"
    assert wrapped.invoke({"city": "Paris"}) == "quote-1"
    assert calls["n"] == 2


def test_wrap_tools_skips_stateful_tools_entirely():
    calls = {"n": 0}

    @tool
    def update_trip_plan(payload: str) -> str:
        """Pretend stateful tool — must never be cached."""
        calls["n"] += 1
        return f"wrote {payload}"

    [wrapped] = tools_cache.wrap_tools_with_cache([update_trip_plan])

    wrapped.invoke({"payload": "a"})
    wrapped.invoke({"payload": "a"})
    assert calls["n"] == 2  # No dedup for state-mutating calls.


def test_stateful_tool_invalidates_user_cache_entries():
    tools_cache.cache_store("get_trip_plan", {}, "stale")
    assert tools_cache.cache_lookup("get_trip_plan", {}) == "stale"

    @tool
    def update_trip_plan(payload: str) -> str:
        """Pretend write tool that should invalidate user scoped cache."""
        return f"updated:{payload}"

    [wrapped] = tools_cache.wrap_tools_with_cache([update_trip_plan])
    assert wrapped.invoke({"payload": "x"}) == "updated:x"
    assert tools_cache.cache_lookup("get_trip_plan", {}) is None


def test_local_cache_evicts_oldest_when_full(monkeypatch):
    monkeypatch.setattr(tools_cache, "_LOCAL_MAX", 3)
    for i in range(5):
        tools_cache.cache_store("web_search", {"i": i}, f"v{i}")
    # Only the most recent 3 survive (i=2,3,4).
    assert tools_cache.cache_lookup("web_search", {"i": 0}) is None
    assert tools_cache.cache_lookup("web_search", {"i": 1}) is None
    assert tools_cache.cache_lookup("web_search", {"i": 2}) == "v2"
    assert tools_cache.cache_lookup("web_search", {"i": 4}) == "v4"

