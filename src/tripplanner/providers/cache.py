"""In-memory fare cache with TTL support."""

from __future__ import annotations

import logging
import pickle
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Generic, TypeVar

from tripplanner.config import get_settings

try:
    import redis
except ImportError:  # pragma: no cover - optional runtime dependency by environment
    redis = None

T = TypeVar("T")
log = logging.getLogger(__name__)
_PROVIDER_CACHES: weakref.WeakSet[ProviderTTLCache[Any]] = weakref.WeakSet()


class TransportMode(StrEnum):
    """Transport modes for caching purposes."""

    FLIGHT = "flight"
    HOTEL = "hotel"
    TRAIN = "train"
    COACH = "coach"
    FERRY = "ferry"
    ACTIVITY = "activity"


@dataclass(frozen=True)
class CacheKey:
    """Immutable cache key for fare queries."""

    mode: TransportMode
    origin: str
    destination: str
    departure_date: str
    return_date: str = ""
    adults: int = 1
    children: int = 0
    currency: str = "INR"

    def __hash__(self) -> int:
        return hash((
            self.mode,
            self.origin,
            self.destination,
            self.departure_date,
            self.return_date,
            self.adults,
            self.children,
            self.currency,
        ))


class FareCache:
    """Simple in-memory fare cache with per-mode TTL.

    TTLs are configured per TransportMode to reflect price volatility:
    - Flight/Hotel: 4 hours (highly dynamic)
    - Train/Coach/Ferry: 12 hours (stable day-of)
    - Activity: 24 hours (least dynamic)
    """

    def __init__(self, ttl_seconds: dict[TransportMode, int]) -> None:
        """Initialize cache with mode-specific TTLs.

        Args:
            ttl_seconds: Mapping of TransportMode -> TTL in seconds.
                Typical values:
                - Flight: 14400 (4h)
                - Hotel: 14400 (4h)
                - Train: 43200 (12h)
                - Coach: 43200 (12h)
                - Ferry: 43200 (12h)
                - Activity: 86400 (24h)
        """
        self.ttl = ttl_seconds
        self.cache: dict[CacheKey, tuple[Any, datetime]] = {}

    def get(self, key: CacheKey) -> Any | None:
        """Retrieve cached fare if not expired, else evict and return None.

        Args:
            key: CacheKey instance.

        Returns:
            Cached fare object if valid, None otherwise.
        """
        if key not in self.cache:
            return None

        fare, created_at = self.cache[key]
        ttl = self.ttl.get(key.mode, 0)
        if datetime.now(UTC) < created_at + timedelta(seconds=ttl):
            return fare

        # Expired: evict
        del self.cache[key]
        return None

    def set(self, key: CacheKey, fare: Any) -> None:
        """Cache a fare result.

        Args:
            key: CacheKey instance.
            fare: Fare object (list of offers or single offer).
        """
        self.cache[key] = (fare, datetime.now(UTC))

    def clear(self) -> None:
        """Clear all cached entries."""
        self.cache.clear()

    def stats(self) -> dict[str, int]:
        """Return cache statistics.

        Returns:
            Dict with 'entries' (total), 'expired' (expired but not evicted yet).
        """
        now = datetime.now(UTC)
        expired = 0
        for key, (_, created_at) in self.cache.items():
            ttl = self.ttl.get(key.mode, 0)
            if now >= created_at + timedelta(seconds=ttl):
                expired += 1
        return {"entries": len(self.cache), "expired": expired}


@dataclass(frozen=True)
class ProviderCacheEntry(Generic[T]):
    value: T
    provider: str
    checked_at: datetime
    expires_at: datetime


class ProviderTTLCache(Generic[T]):
    """Small in-process TTL cache for provider capability results.

    This is intentionally generic and conservative. It is a low-cost MVP guard
    around provider fan-out, not a replacement for persisted trip evidence.
    """

    def __init__(self) -> None:
        self._items: dict[str, ProviderCacheEntry[T]] = {}
        self._redis: _RedisProviderCache[T] | None = None
        _PROVIDER_CACHES.add(self)

        settings = get_settings()
        if settings.cache_redis_enabled:
            self._redis = _RedisProviderCache(
                url=settings.cache_redis_url,
                namespace=settings.cache_redis_namespace,
                connect_timeout=settings.cache_redis_connect_timeout_sec,
                socket_timeout=settings.cache_redis_socket_timeout_sec,
            )

    def get(self, key: str) -> ProviderCacheEntry[T] | None:
        if self._redis:
            remote = self._redis.get(key)
            if remote:
                self._items[key] = remote
                return remote

        entry = self._items.get(key)
        if not entry:
            return None
        if datetime.now(UTC) >= entry.expires_at:
            del self._items[key]
            return None
        return entry

    def set(self, key: str, value: T, *, provider: str, ttl_seconds: int) -> ProviderCacheEntry[T]:
        checked_at = datetime.now(UTC)
        entry = ProviderCacheEntry(
            value=value,
            provider=provider,
            checked_at=checked_at,
            expires_at=checked_at + timedelta(seconds=max(1, ttl_seconds)),
        )
        self._items[key] = entry
        if self._redis:
            self._redis.set(key, entry, ttl_seconds=max(1, ttl_seconds))
        return entry

    def clear(self) -> None:
        self._items.clear()
        if self._redis:
            self._redis.clear_namespace()

    def status(self) -> dict[str, Any]:
        return {
            "memory_entries": len(self._items),
            "redis": (
                self._redis.status()
                if self._redis
                else {"enabled": False, "connected": False}
            ),
        }


class _RedisProviderCache(Generic[T]):
    """Best-effort Redis cache that gracefully falls back to in-memory only."""

    def __init__(self, *, url: str, namespace: str, connect_timeout: float, socket_timeout: float):
        self._namespace = namespace.rstrip(":")
        self._client: redis.Redis | None = None
        self._warned_down = False

        if redis is None:
            log.warning(
                "CACHE_REDIS_ENABLED=1 but redis package is unavailable; using in-memory cache"
            )
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
            log.info("Redis cache enabled for provider TTL cache")
        except Exception as exc:  # noqa: BLE001 - cache backend must never break requests
            log.warning("Redis cache unavailable, using in-memory fallback only: %s", exc)

    def _namespaced(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": True,
            "connected": self._client is not None and not self._warned_down,
            "entries": 0,
            "bytes": 0,
            "truncated": False,
        }
        if not self._client:
            return result
        try:
            keys = list(self._client.scan_iter(match=f"{self._namespace}:*", count=100, _type="string"))
            if len(keys) > 1000:
                keys = keys[:1000]
                result["truncated"] = True
            result["entries"] = len(keys)
            result["bytes"] = sum(int(self._client.memory_usage(key) or 0) for key in keys)
            self._warned_down = False
        except Exception as exc:  # noqa: BLE001 - status must never break requests
            self._warn_once(exc)
            result["connected"] = False
        return result

    def get(self, key: str) -> ProviderCacheEntry[T] | None:
        if not self._client:
            return None
        try:
            payload = self._client.get(self._namespaced(key))
            if not payload:
                return None
            entry = pickle.loads(payload)
            if not isinstance(entry, ProviderCacheEntry):
                return None
            if datetime.now(UTC) >= entry.expires_at:
                self._client.delete(self._namespaced(key))
                return None
            self._warned_down = False
            return entry
        except Exception as exc:  # noqa: BLE001 - cache backend must never break requests
            self._warn_once(exc)
            return None

    def set(self, key: str, entry: ProviderCacheEntry[T], *, ttl_seconds: int) -> None:
        if not self._client:
            return
        try:
            self._client.setex(
                self._namespaced(key),
                max(1, int(ttl_seconds)),
                pickle.dumps(entry, protocol=pickle.HIGHEST_PROTOCOL),
            )
            self._warned_down = False
        except Exception as exc:  # noqa: BLE001 - cache backend must never break requests
            self._warn_once(exc)

    def clear_namespace(self) -> None:
        if not self._client:
            return
        try:
            keys = self._client.keys(f"{self._namespace}:*")
            if keys:
                self._client.delete(*keys)
        except Exception as exc:  # noqa: BLE001 - cache backend must never break requests
            self._warn_once(exc)

    def _warn_once(self, exc: Exception) -> None:
        if self._warned_down:
            return
        self._warned_down = True
        log.warning("Redis cache call failed; continuing with in-memory fallback: %s", exc)


def provider_cache_status() -> dict[str, Any]:
    caches = [cache.status() for cache in list(_PROVIDER_CACHES)]
    redis_enabled = any(cache["redis"]["enabled"] for cache in caches)
    redis_connected = any(cache["redis"]["connected"] for cache in caches)
    return {
        "configured": get_settings().cache_redis_enabled,
        "backend": "redis" if redis_connected else "memory",
        "redis_connected": redis_connected,
        "fallback_active": redis_enabled and not redis_connected,
        "memory_entries": sum(int(cache["memory_entries"]) for cache in caches),
        "redis_entries": sum(int(cache["redis"].get("entries", 0)) for cache in caches),
        "redis_bytes": sum(int(cache["redis"].get("bytes", 0)) for cache in caches),
        "redis_stats_truncated": any(
            bool(cache["redis"].get("truncated", False)) for cache in caches
        ),
    }
