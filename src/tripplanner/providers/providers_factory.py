"""Provider factory with intelligent routing and caching."""

from __future__ import annotations

import logging
from typing import Any

from tripplanner.config import get_settings
from tripplanner.providers.cache import FareCache, TransportMode
from tripplanner.providers.kiwi_client import KiwiCoachSource, KiwiFerrySource, KiwiTrainSource
from tripplanner.providers.liteapi import LiteAPIProvider
from tripplanner.providers.models import (
    CoachOffer,
    CoachSearchQuery,
    FerryOffer,
    FerrySearchQuery,
    RailOffer,
    RailSearchQuery,
)

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Routes search requests to configured providers with intelligent fallback and caching."""

    def __init__(self) -> None:
        self.config = get_settings()
        self.cache = FareCache({
            TransportMode.FLIGHT: self.config.flight_cache_ttl_sec,
            TransportMode.HOTEL: self.config.hotel_cache_ttl_sec,
            TransportMode.TRAIN: self.config.train_cache_ttl_sec,
            TransportMode.COACH: self.config.coach_cache_ttl_sec,
            TransportMode.FERRY: self.config.ferry_cache_ttl_sec,
            TransportMode.ACTIVITY: self.config.activity_cache_ttl_sec,
        })
        
        # Initialize providers
        self._liteapi: LiteAPIProvider | None = None
        self._kiwi_trains: KiwiTrainSource | None = None
        self._kiwi_coaches: KiwiCoachSource | None = None
        self._kiwi_ferries: KiwiFerrySource | None = None

    @property
    def liteapi(self) -> LiteAPIProvider | None:
        """Lazy-initialize LiteAPI provider."""
        if self._liteapi is None and self.config.liteapi_api_key:
            self._liteapi = LiteAPIProvider(
                api_key=self.config.liteapi_api_key,
                base_url=self.config.liteapi_base_url,
            )
        return self._liteapi

    @property
    def kiwi_trains(self) -> KiwiTrainSource | None:
        """Lazy-initialize Kiwi trains provider."""
        if self._kiwi_trains is None and self.config.kiwi_api_key:
            self._kiwi_trains = KiwiTrainSource(
                api_key=self.config.kiwi_api_key,
                base_url=self.config.kiwi_base_url,
            )
        return self._kiwi_trains

    @property
    def kiwi_coaches(self) -> KiwiCoachSource | None:
        """Lazy-initialize Kiwi coaches provider."""
        if self._kiwi_coaches is None and self.config.kiwi_api_key:
            self._kiwi_coaches = KiwiCoachSource(
                api_key=self.config.kiwi_api_key,
                base_url=self.config.kiwi_base_url,
            )
        return self._kiwi_coaches

    @property
    def kiwi_ferries(self) -> KiwiFerrySource | None:
        """Lazy-initialize Kiwi ferries provider."""
        if self._kiwi_ferries is None and self.config.kiwi_api_key:
            self._kiwi_ferries = KiwiFerrySource(
                api_key=self.config.kiwi_api_key,
                base_url=self.config.kiwi_base_url,
            )
        return self._kiwi_ferries

    def search_trains(self, query: RailSearchQuery) -> list[RailOffer]:
        """Search for train routes with caching and provider fallback."""
        if not self.config.enable_train_pricing:
            return []

        # Build cache key
        from tripplanner.providers.cache import CacheKey
        cache_key = CacheKey(
            mode=TransportMode.TRAIN,
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            adults=query.adults,
            children=query.children,
            currency=query.currency,
        )

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Train search cache hit: {cache_key}")
            return cached

        # Route to providers in order of preference
        providers_to_try: list[tuple[str, Any]] = []
        
        if self.config.travel_train_provider == "kiwi":
            if self.kiwi_trains:
                providers_to_try.append(("kiwi", self.kiwi_trains))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
        elif self.config.travel_train_provider == "liteapi":
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
            if self.kiwi_trains:
                providers_to_try.append(("kiwi", self.kiwi_trains))
        else:  # "auto"
            if self.kiwi_trains:
                providers_to_try.append(("kiwi", self.kiwi_trains))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))

        offers: list[RailOffer] = []
        for provider_name, provider in providers_to_try:
            try:
                offers = provider.search_rails(query)
                if offers:
                    logger.info(f"Train search succeeded with {provider_name}: {len(offers)} results")
                    break
            except Exception as e:
                logger.warning(f"Train search failed with {provider_name}: {e}")
                continue

        # Cache result
        self.cache.set(cache_key, offers)
        return offers

    def search_coaches(self, query: CoachSearchQuery) -> list[CoachOffer]:
        """Search for coach routes with caching and provider fallback."""
        if not self.config.enable_coach_pricing:
            return []

        # Build cache key
        from tripplanner.providers.cache import CacheKey
        cache_key = CacheKey(
            mode=TransportMode.COACH,
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            adults=query.adults,
            children=query.children,
            currency=query.currency,
        )

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Coach search cache hit: {cache_key}")
            return cached

        # Route to providers in order of preference
        providers_to_try: list[tuple[str, Any]] = []
        
        if self.config.travel_coach_provider == "kiwi":
            if self.kiwi_coaches:
                providers_to_try.append(("kiwi", self.kiwi_coaches))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
        elif self.config.travel_coach_provider == "liteapi":
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
            if self.kiwi_coaches:
                providers_to_try.append(("kiwi", self.kiwi_coaches))
        else:  # "auto"
            if self.kiwi_coaches:
                providers_to_try.append(("kiwi", self.kiwi_coaches))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))

        offers: list[CoachOffer] = []
        for provider_name, provider in providers_to_try:
            try:
                offers = provider.search_coaches(query)
                if offers:
                    logger.info(f"Coach search succeeded with {provider_name}: {len(offers)} results")
                    break
            except Exception as e:
                logger.warning(f"Coach search failed with {provider_name}: {e}")
                continue

        # Cache result
        self.cache.set(cache_key, offers)
        return offers

    def search_ferries(self, query: FerrySearchQuery) -> list[FerryOffer]:
        """Search for ferry routes with caching and provider fallback."""
        if not self.config.enable_ferry_pricing:
            return []

        # Build cache key
        from tripplanner.providers.cache import CacheKey
        cache_key = CacheKey(
            mode=TransportMode.FERRY,
            origin=query.origin,
            destination=query.destination,
            departure_date=query.departure_date,
            return_date=query.return_date,
            adults=query.adults,
            children=query.children,
            currency=query.currency,
        )

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Ferry search cache hit: {cache_key}")
            return cached

        # Route to providers in order of preference
        providers_to_try: list[tuple[str, Any]] = []
        
        if self.config.travel_ferry_provider == "kiwi":
            if self.kiwi_ferries:
                providers_to_try.append(("kiwi", self.kiwi_ferries))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
        elif self.config.travel_ferry_provider == "liteapi":
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))
            if self.kiwi_ferries:
                providers_to_try.append(("kiwi", self.kiwi_ferries))
        else:  # "auto"
            if self.kiwi_ferries:
                providers_to_try.append(("kiwi", self.kiwi_ferries))
            if self.liteapi:
                providers_to_try.append(("liteapi", self.liteapi))

        offers: list[FerryOffer] = []
        for provider_name, provider in providers_to_try:
            try:
                offers = provider.search_ferries(query)
                if offers:
                    logger.info(f"Ferry search succeeded with {provider_name}: {len(offers)} results")
                    break
            except Exception as e:
                logger.warning(f"Ferry search failed with {provider_name}: {e}")
                continue

        # Cache result
        self.cache.set(cache_key, offers)
        return offers


# Singleton instance
_router: ProviderRouter | None = None


def get_provider_router() -> ProviderRouter:
    """Get or create the global provider router."""
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router
