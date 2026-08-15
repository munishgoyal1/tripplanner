from __future__ import annotations

import pytest

from tripplanner import caching


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(caching, "_REGISTRY", {})
    monkeypatch.setattr(caching, "_BACKEND", caching.MemoryBackend())


def test_a_value_survives_until_its_ttl_and_not_beyond(monkeypatch):
    cache = caching.get_cache("probe", default_ttl_seconds=60)
    cache.set("k", {"a": 1})
    assert cache.get("k") == {"a": 1}

    now = [0.0]
    monkeypatch.setattr(caching.time, "time", lambda: now[0])
    cache.set("short", "value", ttl_seconds=10)
    now[0] = 11.0
    assert cache.get("short") is None


def test_regions_do_not_collide_on_the_same_key():
    left = caching.get_cache("left")
    right = caching.get_cache("right")
    left.set("same", "from-left")
    right.set("same", "from-right")

    assert left.get("same") == "from-left"
    assert right.get("same") == "from-right"


def test_clearing_one_region_leaves_the_others_alone():
    left = caching.get_cache("left")
    right = caching.get_cache("right")
    left.set("a", 1)
    right.set("b", 2)

    left.clear()

    assert left.get("a") is None
    assert right.get("b") == 2


def test_status_reports_memory_when_redis_is_not_configured():
    caching.get_cache("probe").set("k", "v")
    status = caching.cache_status()

    assert status["backend"] == "memory"
    assert status["redis_connected"] is False
    assert status["fallback_active"] is False
    assert {region["name"] for region in status["regions"]} == {"probe"}


def test_an_unreachable_redis_still_serves_from_memory(monkeypatch):
    backend = caching.RedisBackend.__new__(caching.RedisBackend)
    backend._mirror = caching.MemoryBackend()
    backend._client = None
    backend._down_since = None
    monkeypatch.setattr(caching, "_BACKEND", backend)

    cache = caching.get_cache("probe")
    cache.set("k", "v")

    assert cache.get("k") == "v"
    assert caching.cache_status()["fallback_active"] is True


def test_a_redis_that_fails_mid_flight_falls_back_rather_than_raising(monkeypatch):
    class Broken:
        def get(self, *_args, **_kwargs):
            raise ConnectionError("redis is gone")

        def set(self, *_args, **_kwargs):
            raise ConnectionError("redis is gone")

        def delete(self, *_args, **_kwargs):
            raise ConnectionError("redis is gone")

    backend = caching.RedisBackend.__new__(caching.RedisBackend)
    backend._mirror = caching.MemoryBackend()
    backend._client = Broken()
    backend._down_since = None
    monkeypatch.setattr(caching, "_BACKEND", backend)

    cache = caching.get_cache("probe")
    cache.set("k", "v")

    assert cache.get("k") == "v"
