"""One cache layer with a swappable backend.

Every ephemeral cache in the app goes through :func:`get_cache`. The backend is
chosen once from configuration: in-process dictionaries by default, Redis when
``CACHE_REDIS_ENABLED=1``. Callers never learn which one they got, so turning
Redis on or off is a configuration change rather than a code change.

Redis is read first and written through to memory, so a shared hit still avoids
the provider call while a cold process keeps a local copy. An unreachable Redis
degrades to memory instead of failing the request: a cache is an optimisation,
and losing it must never lose a trip.

Durable stores are deliberately not here. ``tools_cache`` and ``places_cache``
persist to Cosmos because their contents are expensive to rebuild and are
expected to outlive any cache eviction; moving them behind a TTL cache would
quietly turn durable data into disposable data.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from tripplanner.config import get_settings

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency by environment
    redis = None

log = logging.getLogger(__name__)

_REGISTRY: dict[str, Cache] = {}
_REGISTRY_LOCK = threading.RLock()
_BACKEND: CacheBackend | None = None
_BACKEND_LOCK = threading.RLock()


@dataclass(frozen=True)
class CacheStats:
    name: str
    backend: str
    entries: int
    hits: int
    misses: int


class CacheBackend(Protocol):
    """Storage a cache reads and writes. Values are JSON-encodable."""

    name: str

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...

    def clear_prefix(self, prefix: str) -> None: ...

    def count_prefix(self, prefix: str) -> int: ...

    def status(self) -> dict[str, Any]: ...


class MemoryBackend:
    """Process-local store. Expiry is checked on read rather than swept."""

    name = "memory"

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            found = self._items.get(key)
            if not found:
                return None
            expires_at, value = found
            if time.time() >= expires_at:
                del self._items[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            expires_at = float("inf") if ttl_seconds == -1 else time.time() + max(1, ttl_seconds)
            self._items[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._items if k.startswith(prefix)]:
                del self._items[key]

    def count_prefix(self, prefix: str) -> int:
        with self._lock:
            now = time.time()
            return sum(
                1
                for key, (expires_at, _) in self._items.items()
                if key.startswith(prefix) and now < expires_at
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": self.name,
                "connected": True,
                "entries": len(self._items),
                "memory_entries": len(self._items),
                "bytes": 0,
                "truncated": False,
            }


class RedisBackend:
    """Shared store, with a memory mirror so a Redis outage is survivable.

    Values are JSON, not pickle: a cache reachable by more than one process is
    an input, and unpickling an input is remote code execution.
    """

    name = "redis"

    def __init__(self, *, url: str, connect_timeout: float, socket_timeout: float) -> None:
        self._mirror = MemoryBackend()
        self._client: Any | None = None
        self._down_since: float | None = None

        if redis is None:
            log.warning("CACHE_REDIS_ENABLED=1 but the redis package is missing; using memory")
            return
        try:
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=max(0.05, connect_timeout),
                socket_timeout=max(0.05, socket_timeout),
                health_check_interval=30,
                retry_on_timeout=True,
            )
            client.ping()
            self._client = client
            log.info("Redis cache backend connected")
        except Exception as exc:  # noqa: BLE001 - the cache must never break a request
            log.warning("Redis unavailable, serving from memory only: %s", exc)

    def _demote(self, exc: Exception) -> None:
        if self._down_since is None:
            self._down_since = time.time()
            log.warning("Redis cache degraded to memory: %s", exc)

    def get(self, key: str) -> Any | None:
        if self._client:
            try:
                payload = self._client.get(key)
                self._down_since = None
                if payload is not None:
                    return json.loads(payload)
            except json.JSONDecodeError:
                # A value this process cannot read is not worth keeping.
                self.delete(key)
            except Exception as exc:  # noqa: BLE001
                self._demote(exc)
        return self._mirror.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        ttl = -1 if ttl_seconds == -1 else max(1, ttl_seconds)
        self._mirror.set(key, value, ttl)
        if not self._client:
            return
        try:
            if ttl == -1:
                self._client.set(key, json.dumps(value))
            else:
                self._client.set(key, json.dumps(value), ex=ttl)
            self._down_since = None
        except (TypeError, ValueError):
            log.debug("cache value for %s is not JSON-encodable; kept in memory only", key)
        except Exception as exc:  # noqa: BLE001
            self._demote(exc)

    def delete(self, key: str) -> None:
        self._mirror.delete(key)
        if not self._client:
            return
        try:
            self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            self._demote(exc)

    def _scan(self, prefix: str, limit: int = 5000) -> list[bytes]:
        if not self._client:
            return []
        found: list[bytes] = []
        for key in self._client.scan_iter(match=f"{prefix}*", count=200):
            found.append(key)
            if len(found) >= limit:
                break
        return found

    def clear_prefix(self, prefix: str) -> None:
        self._mirror.clear_prefix(prefix)
        if not self._client:
            return
        try:
            keys = self._scan(prefix)
            if keys:
                self._client.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            self._demote(exc)

    def count_prefix(self, prefix: str) -> int:
        if self._client:
            try:
                count = len(self._scan(prefix))
                self._down_since = None
                return count
            except Exception as exc:  # noqa: BLE001
                self._demote(exc)
        return self._mirror.count_prefix(prefix)

    def status(self) -> dict[str, Any]:
        connected = self._client is not None and self._down_since is None
        mirror = self._mirror.status()
        result: dict[str, Any] = {
            "backend": self.name,
            "connected": connected,
            "entries": 0,
            "memory_entries": mirror["entries"],
            "bytes": 0,
            "truncated": False,
        }
        if not connected:
            return result
        try:
            keys = self._scan("tripplanner:", limit=1000)
            result["entries"] = len(keys)
            result["truncated"] = len(keys) >= 1000
            result["bytes"] = sum(int(self._client.memory_usage(key) or 0) for key in keys)
        except Exception as exc:  # noqa: BLE001 - status must never break a request
            self._demote(exc)
            result["connected"] = False
        return result


def _build_backend() -> CacheBackend:
    settings = get_settings()
    if settings.cache_redis_enabled and settings.cache_redis_url:
        return RedisBackend(
            url=settings.cache_redis_url,
            connect_timeout=settings.cache_redis_connect_timeout_sec,
            socket_timeout=settings.cache_redis_socket_timeout_sec,
        )
    return MemoryBackend()


def get_backend() -> CacheBackend:
    global _BACKEND
    with _BACKEND_LOCK:
        if _BACKEND is None:
            _BACKEND = _build_backend()
        return _BACKEND


def reset_backend() -> None:
    """Drop the chosen backend and every cache built on it.

    Configuration is read once per process, so this exists for tests and for a
    settings reload rather than for request handling.
    """
    global _BACKEND
    with _BACKEND_LOCK:
        _BACKEND = None
    with _REGISTRY_LOCK:
        for cache in _REGISTRY.values():
            cache.rebind()


class Cache:
    """A named, TTL'd region of the shared backend."""

    def __init__(self, name: str, *, default_ttl_seconds: int, volatile: bool) -> None:
        self.name = name
        self.default_ttl_seconds = max(1, default_ttl_seconds)
        self.volatile = volatile
        self._hits = 0
        self._misses = 0

    @property
    def _backend(self) -> CacheBackend:
        # Resolved per call, not at construction. Modules build their cache at
        # import time, and connecting to Redis that early dialled out before a
        # test or a settings reload could choose a different backend.
        return get_backend()

    def rebind(self) -> None:
        self._hits = 0
        self._misses = 0

    @property
    def prefix(self) -> str:
        return f"{get_settings().cache_redis_namespace.rstrip(':')}:{self.name}:"

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def get(self, key: str) -> Any | None:
        value = self._backend.get(self._key(key))
        if value is None:
            self._misses += 1
        else:
            self._hits += 1
        return value

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        configured_ttl = ttl_seconds or self.default_ttl_seconds
        settings = get_settings()
        if configured_ttl == -1:
            effective_ttl = -1
        elif self.volatile:
            effective_ttl = settings.volatile_cache_ttl(configured_ttl)
        else:
            effective_ttl = settings.stable_cache_ttl(configured_ttl)
        self._backend.set(self._key(key), value, effective_ttl)

    def delete(self, key: str) -> None:
        self._backend.delete(self._key(key))

    def clear(self) -> None:
        self._backend.clear_prefix(self.prefix)
        self._hits = 0
        self._misses = 0

    def stats(self) -> CacheStats:
        return CacheStats(
            name=self.name,
            backend=self._backend.name,
            entries=self._backend.count_prefix(self.prefix),
            hits=self._hits,
            misses=self._misses,
        )


def get_cache(
    name: str, *, default_ttl_seconds: int = 3600, volatile: bool = True
) -> Cache:
    """The cache registered under ``name``, created on first use."""
    with _REGISTRY_LOCK:
        cache = _REGISTRY.get(name)
        if cache is None:
            cache = Cache(name, default_ttl_seconds=default_ttl_seconds, volatile=volatile)
            _REGISTRY[name] = cache
        elif cache.volatile != volatile:
            raise ValueError(f"cache region {name!r} cannot change volatility classification")
        return cache


def cache_status() -> dict[str, Any]:
    """Backend health plus per-region counters, for the owner ops dashboard."""
    backend = get_backend()
    detail = backend.status()
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    redis_selected = backend.name == "redis"
    connected = redis_selected and bool(detail.get("connected"))
    return {
        "configured": get_settings().cache_redis_enabled,
        "backend": "redis" if connected else "memory",
        "redis_connected": connected,
        "fallback_active": redis_selected and not connected,
        "memory_entries": int(detail.get("memory_entries", 0)),
        "redis_entries": int(detail.get("entries", 0)) if connected else 0,
        "redis_bytes": int(detail.get("bytes", 0)),
        "redis_stats_truncated": bool(detail.get("truncated", False)),
        "regions": [
            {
                "name": stats.name,
                "entries": stats.entries,
                "hits": stats.hits,
                "misses": stats.misses,
            }
            for stats in (cache.stats() for cache in caches)
        ],
    }


def clear_all() -> None:
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    for cache in caches:
        cache.clear()
