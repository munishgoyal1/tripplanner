"""Fare sources, and the honest absence of one.

A mode is priced only when a source we can name returns a fare. There is no
estimate tier: an unpriced hop shows its time, its transfers and its effect on
the day, and shows no number at all. Adding a retailer or aggregator later means
registering one more source here — nothing above this file changes shape.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from tripplanner.decisions.models import Confidence, FareBasis, TransportMode, UnpricedReason
from tripplanner.providers.models import FlightSearchQuery, CoachSearchQuery, FerrySearchQuery, RailSearchQuery
from tripplanner.providers.registry import get_flight_provider, get_train_provider, get_coach_provider, get_ferry_provider

logger = logging.getLogger(__name__)


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
    """Prices coach/bus routes through the configured coach provider (Kiwi today)."""

    name = "coaches"
    modes = frozenset({TransportMode.BUS})

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


def quote_fare(request: FareRequest) -> tuple[FareQuote | None, UnpricedReason | None]:
    """Return a fare, or the reason there is none. Never raises, never guesses."""
    candidates = sources_for(request.mode)
    if not candidates:
        return None, UnpricedReason.NO_SOURCE

    failed = False
    for source in candidates:
        try:
            quote = source.quote(request)
        except Exception as exc:
            failed = True
            logger.info("fare source %s failed for %s: %s", source.name, request.mode, exc)
            continue
        if quote is not None:
            return quote, None
    return None, UnpricedReason.SOURCE_FAILED if failed else UnpricedReason.OUT_OF_COVERAGE
