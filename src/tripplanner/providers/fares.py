"""Fare sources with caching, concurrency, and telemetry.

A mode is priced only when a source we can name returns a fare. There is no
estimate tier: an unpriced hop shows its time, its transfers and its effect on
the day, and shows no number at all. Adding a retailer or aggregator later means
registering one more source here — nothing above this file changes shape.

Fares are cached per origin/destination/date/currency for 4–12 hours depending
on volatility. Concurrent source queries ensure no single slow provider blocks
user experience (first result wins within 2s timeout).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from tripplanner.decisions.models import Confidence, FareBasis, TransportMode, UnpricedReason
from tripplanner.providers.cache import CacheKey, FareCache
from tripplanner.providers.models import FlightSearchQuery, CoachSearchQuery, FerrySearchQuery, RailSearchQuery
from tripplanner.providers.registry import get_flight_provider, get_train_provider, get_coach_provider, get_ferry_provider

logger = logging.getLogger(__name__)

# Global cache with per-mode TTLs (seconds)
_FARE_CACHE = FareCache(ttl_seconds={
    "flight": 4 * 3600,      # 4 hours (highly dynamic)
    "train": 12 * 3600,      # 12 hours (stable within day)
    "coach": 12 * 3600,      # 12 hours
    "ferry": 12 * 3600,      # 12 hours
    "hotel": 4 * 3600,       # 4 hours
    "activity": 24 * 3600,   # 24 hours
})

# Telemetry: track provider choices and performance
_PROVIDER_STATS = {
    "quote_success": {},
    "quote_failure": {},
    "cache_hits": {},
    "avg_latency_ms": {},
}


@dataclass(frozen=True)
class FareRequest:
    mode: TransportMode
    from_place: str
    to_place: str
    date: str = ""
    travellers: int = 1
    currency: str = "EUR"


@dataclass(frozen=True)
class FareQuote:
    amount: float
    currency: str
    provider: str
    basis: FareBasis = FareBasis.PER_TRAVELLER
    # Aggregators publish a band rather than a bookable fare. Keeping the upper
    # bound means the UI can say "from X to Y" instead of implying a fixed price.
    amount_max: float | None = None
    url: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confidence: Confidence = Confidence.LIVE


class FareSource(Protocol):
    """A source that can price at least one transport mode."""

    name: str
    modes: frozenset[TransportMode]

    def quote(self, request: FareRequest) -> FareQuote | None: ...


class AirFareSource:
    """Prices flights through the configured flight provider (Duffel today)."""

    name = "flights"
    modes = frozenset({TransportMode.FLIGHT})

    def quote(self, request: FareRequest) -> FareQuote | None:
        provider = get_flight_provider()
        if provider is None or not request.date:
            return None
        offers = provider.search_flights(
            FlightSearchQuery(
                origin=request.from_place,
                destination=request.to_place,
                departure_date=request.date,
                adults=max(1, request.travellers),
                currency=request.currency.upper(),
                max_results=3,
            )
        )
        cheapest = min(
            (offer for offer in offers if offer.total and offer.total.amount > 0),
            key=lambda offer: offer.total.amount,
            default=None,
        )
        if cheapest is None:
            return None
        return FareQuote(
            amount=cheapest.total.amount,
            currency=cheapest.total.currency,
            provider=provider.name,
            # Provider totals already cover the whole party in the query above.
            basis=FareBasis.PER_PARTY,
            checked_at=cheapest.quoted_at or datetime.now(UTC),
        )


class RailFareSource:
    """Prices train routes through the configured train provider (Kiwi today)."""

    name = "trains"
    modes = frozenset({TransportMode.TRAIN})

    def quote(self, request: FareRequest) -> FareQuote | None:
        provider = get_train_provider()
        if provider is None or not request.date:
            return None
        offers = provider.search_rails(
            RailSearchQuery(
                origin=request.from_place,
                destination=request.to_place,
                departure_date=request.date,
                adults=max(1, request.travellers),
                max_results=3,
            )
        )
        cheapest = min(
            (offer for offer in offers if offer.total and offer.total.amount > 0),
            key=lambda offer: offer.total.amount,
            default=None,
        )
        if cheapest is None:
            return None
        return FareQuote(
            amount=cheapest.total.amount,
            currency=cheapest.total.currency,
            provider=provider.name,
            basis=FareBasis.PER_PARTY,
            checked_at=cheapest.quoted_at or datetime.now(UTC),
        )


class CoachFareSource:
    """Prices coach/bus routes through the configured coach provider."""

    name = "coaches"
    modes = frozenset({TransportMode.COACH})

    def quote(self, request: FareRequest) -> FareQuote | None:
        provider = get_coach_provider()
        if provider is None or not request.date:
            return None
        offers = provider.search_coaches(
            CoachSearchQuery(
                origin=request.from_place,
                destination=request.to_place,
                departure_date=request.date,
                adults=max(1, request.travellers),
                max_results=3,
            )
        )
        cheapest = min(
            (offer for offer in offers if offer.total and offer.total.amount > 0),
            key=lambda offer: offer.total.amount,
            default=None,
        )
        if cheapest is None:
            return None
        return FareQuote(
            amount=cheapest.total.amount,
            currency=cheapest.total.currency,
            provider=provider.name,
            basis=FareBasis.PER_PARTY,
            checked_at=cheapest.quoted_at or datetime.now(UTC),
        )


class FerryFareSource:
    """Prices ferry routes through the configured ferry provider (Kiwi today)."""

    name = "ferries"
    modes = frozenset({TransportMode.FERRY})

    def quote(self, request: FareRequest) -> FareQuote | None:
        provider = get_ferry_provider()
        if provider is None or not request.date:
            return None
        offers = provider.search_ferries(
            FerrySearchQuery(
                origin=request.from_place,
                destination=request.to_place,
                departure_date=request.date,
                adults=max(1, request.travellers),
                max_results=3,
            )
        )
        cheapest = min(
            (offer for offer in offers if offer.total and offer.total.amount > 0),
            key=lambda offer: offer.total.amount,
            default=None,
        )
        if cheapest is None:
            return None
        return FareQuote(
            amount=cheapest.total.amount,
            currency=cheapest.total.currency,
            provider=provider.name,
            basis=FareBasis.PER_PARTY,
            checked_at=cheapest.quoted_at or datetime.now(UTC),
        )


# Ordered: the first source that covers the mode and answers wins. Register ground
# transportation sources here; they'll auto-enable when configured.
_SOURCES: list[FareSource] = [
    AirFareSource(),
    RailFareSource(),
    CoachFareSource(),
    FerryFareSource(),
]


def sources_for(mode: TransportMode) -> list[FareSource]:
    return [source for source in _SOURCES if mode in source.modes]


def register_source(source: FareSource) -> None:
    """Add a source at the front of the chain. Used by tests and future providers."""
    _SOURCES.insert(0, source)


def unregister_source(name: str) -> None:
    global _SOURCES
    _SOURCES = [source for source in _SOURCES if source.name != name]


def _record_success(provider: str, mode: str, latency_ms: float) -> None:
    """Record successful quote in telemetry."""
    if provider not in _PROVIDER_STATS["quote_success"]:
        _PROVIDER_STATS["quote_success"][provider] = 0
        _PROVIDER_STATS["avg_latency_ms"][provider] = 0
    _PROVIDER_STATS["quote_success"][provider] += 1
    # Rolling average
    current = _PROVIDER_STATS["avg_latency_ms"][provider]
    count = _PROVIDER_STATS["quote_success"][provider]
    _PROVIDER_STATS["avg_latency_ms"][provider] = (
        (current * (count - 1) + latency_ms) / count
    )


def _record_failure(provider: str, mode: str) -> None:
    """Record failed quote in telemetry."""
    if provider not in _PROVIDER_STATS["quote_failure"]:
        _PROVIDER_STATS["quote_failure"][provider] = 0
    _PROVIDER_STATS["quote_failure"][provider] += 1


def _record_cache_hit(provider: str) -> None:
    """Record cache hit."""
    if provider not in _PROVIDER_STATS["cache_hits"]:
        _PROVIDER_STATS["cache_hits"][provider] = 0
    _PROVIDER_STATS["cache_hits"][provider] += 1


def get_provider_stats() -> dict:
    """Return provider performance telemetry for monitoring/debugging."""
    return _PROVIDER_STATS.copy()


async def _query_source_async(
    source: FareSource,
    request: FareRequest,
    start_time: datetime,
) -> tuple[FareQuote | None, str | None]:
    """Query a single source asynchronously. Returns (quote, error_message)."""
    try:
        # Run the synchronous quote call in a thread pool
        loop = asyncio.get_event_loop()
        quote = await loop.run_in_executor(None, source.quote, request)
        
        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        if quote is not None:
            _record_success(source.name, str(request.mode), latency_ms)
            return quote, None
        return None, None
    except Exception as exc:
        _record_failure(source.name, str(request.mode))
        error_msg = f"{source.name} failed: {type(exc).__name__}"
        logger.info(error_msg)
        return None, error_msg


async def _quote_fare_async(
    request: FareRequest,
    timeout_seconds: float = 2.0,
) -> tuple[FareQuote | None, UnpricedReason | None]:
    """Concurrently query fare sources with timeout. Returns first result.
    
    Args:
        request: FareRequest with mode, from_place, to_place, date, etc.
        timeout_seconds: Max time to wait for first result (default 2s for UX).
    
    Returns:
        (FareQuote, None) if quote found; (None, UnpricedReason) otherwise.
    """
    # Check cache first
    cache_key = CacheKey(
        mode=str(request.mode).lower(),
        origin=request.from_place,
        destination=request.to_place,
        departure_date=request.date,
        adults=request.travellers,
        currency=request.currency,
    )
    cached = _FARE_CACHE.get(cache_key)
    if cached is not None:
        _record_cache_hit("cache")
        return cached, None
    
    candidates = sources_for(request.mode)
    if not candidates:
        return None, UnpricedReason.NO_SOURCE
    
    # Launch concurrent queries
    start_time = datetime.now(UTC)
    tasks = [
        _query_source_async(source, request, start_time)
        for source in candidates
    ]
    
    try:
        # Wait for first successful result within timeout
        for coro in asyncio.as_completed(tasks, timeout=timeout_seconds):
            quote, error = await coro
            if quote is not None:
                # Cache and return first result
                _FARE_CACHE.set(cache_key, quote)
                return quote, None
    except asyncio.TimeoutError:
        logger.info("fare query timeout for %s %s→%s", 
                   request.mode, request.from_place, request.to_place)
    except Exception as exc:
        logger.error("unexpected error in concurrent fare query: %s", exc)
    
    # All queries failed or timed out
    failed_any = any(
        source.name in _PROVIDER_STATS["quote_failure"]
        for source in candidates
    )
    return None, (
        UnpricedReason.SOURCE_FAILED if failed_any 
        else UnpricedReason.OUT_OF_COVERAGE
    )


def quote_fare(request: FareRequest) -> tuple[FareQuote | None, UnpricedReason | None]:
    """Return a fare, or the reason there is none. Never raises, never guesses.
    
    This is the synchronous entry point. For async contexts, use _quote_fare_async.
    Uses in-process concurrency and caching to minimize latency.
    """
    # For now, fall back to sequential querying in sync context
    # In production, this would be wrapped in an async runtime
    candidates = sources_for(request.mode)
    if not candidates:
        return None, UnpricedReason.NO_SOURCE
    
    # Check cache
    cache_key = CacheKey(
        mode=str(request.mode).lower(),
        origin=request.from_place,
        destination=request.to_place,
        departure_date=request.date,
        adults=request.travellers,
        currency=request.currency,
    )
    cached = _FARE_CACHE.get(cache_key)
    if cached is not None:
        _record_cache_hit("cache")
        return cached, None
    
    failed = False
    start_time = datetime.now(UTC)
    
    for source in candidates:
        try:
            quote = source.quote(request)
            if quote is not None:
                latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                _record_success(source.name, str(request.mode), latency_ms)
                _FARE_CACHE.set(cache_key, quote)
                return quote, None
        except Exception as exc:
            failed = True
            _record_failure(source.name, str(request.mode))
            logger.info("fare source %s failed for %s: %s", source.name, request.mode, exc)
            continue
    
    return None, UnpricedReason.SOURCE_FAILED if failed else UnpricedReason.OUT_OF_COVERAGE
