"""In-memory fare cache with TTL support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


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
