"""Provider-facing caches built on the shared cache layer.

Nothing here talks to a storage engine. :mod:`tripplanner.caching` owns the
backend, so these caches are in-memory or Redis-backed purely by configuration.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Generic, TypeVar

from tripplanner.caching import cache_status, get_cache

T = TypeVar("T")
log = logging.getLogger(__name__)


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

    def as_cache_key(self) -> str:
        return "|".join([
            str(self.mode),
            self.origin.strip().lower(),
            self.destination.strip().lower(),
            self.departure_date,
            self.return_date,
            str(self.adults),
            str(self.children),
            self.currency.upper(),
        ])


class FareCache:
    """Fare quotes keyed by route and party, with per-mode TTL.

    TTLs reflect price volatility: flights and hotels move within the day,
    ground transport is stable day-of, activities barely move at all.
    """

    def __init__(
        self,
        ttl_seconds: dict[str, int],
        *,
        encode: Callable[[Any], Any] | None = None,
        decode: Callable[[Any], Any] | None = None,
    ) -> None:
        """
        Args:
            ttl_seconds: Mapping of mode name -> TTL in seconds.
            encode: Turns a fare into something JSON-encodable. Without it the
                fare is still cached, but a shared backend cannot carry it.
            decode: Rebuilds the fare from that form.
        """
        self.ttl = ttl_seconds
        self._encode = encode
        self._decode = decode
        self._cache = get_cache(
            "fares", default_ttl_seconds=max(ttl_seconds.values(), default=3600)
        )

    def get(self, key: CacheKey) -> Any | None:
        stored = self._cache.get(key.as_cache_key())
        if stored is None:
            return None
        if self._decode is None:
            return stored
        try:
            return self._decode(stored)
        except (AttributeError, KeyError, TypeError, ValueError):
            self._cache.delete(key.as_cache_key())
            return None

    def set(self, key: CacheKey, fare: Any) -> None:
        ttl = int(self.ttl.get(key.mode, 0))
        if ttl <= 0:
            return
        payload = self._encode(fare) if self._encode else fare
        self._cache.set(key.as_cache_key(), payload, ttl_seconds=ttl)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict[str, int]:
        return {"entries": self._cache.stats().entries, "expired": 0}


@dataclass(frozen=True)
class ProviderCacheEntry(Generic[T]):
    value: T
    provider: str
    checked_at: datetime
    expires_at: datetime


class ProviderTTLCache(Generic[T]):
    """TTL cache for provider capability results.

    Conservative by design: it guards provider fan-out, and is not a substitute
    for persisted trip evidence.
    """

    def __init__(self, region: str = "provider") -> None:
        self._cache = get_cache(region, default_ttl_seconds=3600)

    def get(self, key: str) -> ProviderCacheEntry[T] | None:
        stored = self._cache.get(key)
        if not isinstance(stored, dict):
            return None
        try:
            expires_at = datetime.fromisoformat(str(stored["expires_at"]))
            if datetime.now(UTC) >= expires_at:
                self._cache.delete(key)
                return None
            return ProviderCacheEntry(
                value=stored["value"],
                provider=str(stored.get("provider") or ""),
                checked_at=datetime.fromisoformat(str(stored["checked_at"])),
                expires_at=expires_at,
            )
        except (KeyError, TypeError, ValueError):
            self._cache.delete(key)
            return None

    def set(self, key: str, value: T, *, provider: str, ttl_seconds: int) -> ProviderCacheEntry[T]:
        checked_at = datetime.now(UTC)
        entry = ProviderCacheEntry(
            value=value,
            provider=provider,
            checked_at=checked_at,
            expires_at=checked_at + timedelta(seconds=max(1, ttl_seconds)),
        )
        self._cache.set(
            key,
            {
                "value": value,
                "provider": provider,
                "checked_at": entry.checked_at.isoformat(),
                "expires_at": entry.expires_at.isoformat(),
            },
            ttl_seconds=max(1, ttl_seconds),
        )
        return entry

    def clear(self) -> None:
        self._cache.clear()

    def status(self) -> dict[str, Any]:
        snapshot = self._cache.stats()
        return {
            "entries": snapshot.entries,
            "backend": snapshot.backend,
            "hits": snapshot.hits,
            "misses": snapshot.misses,
        }


def provider_cache_status() -> dict[str, Any]:
    """Cache health for the owner ops dashboard."""
    return cache_status()
