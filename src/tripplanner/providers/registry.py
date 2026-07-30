"""Small capability registry for configured travel inventory providers."""

from __future__ import annotations

from collections.abc import Callable

from tripplanner.config import Settings, get_settings
from tripplanner.providers.liteapi import LiteAPIProvider
from tripplanner.providers.models import (
    ActivityAvailabilityProvider,
    FlightAvailabilityProvider,
    HotelAvailabilityProvider,
)
from tripplanner.providers.viator import ViatorProvider

ProviderFactory = Callable[[Settings], object]


def _liteapi(settings: Settings) -> LiteAPIProvider:
    return LiteAPIProvider(settings.liteapi_api_key, settings.liteapi_base_url)


def _viator(settings: Settings) -> ViatorProvider:
    return ViatorProvider(settings.viator_api_key, settings.viator_base_url)


_HOTEL_PROVIDERS: dict[str, ProviderFactory] = {"liteapi": _liteapi}
_FLIGHT_PROVIDERS: dict[str, ProviderFactory] = {"liteapi": _liteapi}
_ACTIVITY_PROVIDERS: dict[str, ProviderFactory] = {"viator": _viator}


def _selected_provider(kind: str, settings: Settings) -> str | None:
    selected = getattr(settings, f"travel_{kind}_provider", "auto")
    if selected == "legacy":
        return None
    if selected == "auto":
        if kind == "activity":
            return "viator" if getattr(settings, "viator_api_key", "") else None
        return "liteapi" if getattr(settings, "liteapi_api_key", "") else None
    return selected


def get_hotel_provider(settings: Settings | None = None) -> HotelAvailabilityProvider | None:
    active_settings = settings or get_settings()
    selected = _selected_provider("hotel", active_settings)
    if not selected:
        return None
    factory = _HOTEL_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown hotel provider: {selected}")
    if selected == "liteapi" and not getattr(active_settings, "liteapi_api_key", ""):
        raise ValueError("LiteAPI hotel provider selected but LITEAPI_API_KEY is empty")
    return factory(active_settings)  # type: ignore[return-value]


def get_flight_provider(settings: Settings | None = None) -> FlightAvailabilityProvider | None:
    active_settings = settings or get_settings()
    selected = _selected_provider("flight", active_settings)
    if not selected:
        return None
    factory = _FLIGHT_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown flight provider: {selected}")
    if selected == "liteapi" and not getattr(active_settings, "liteapi_api_key", ""):
        raise ValueError("LiteAPI flight provider selected but LITEAPI_API_KEY is empty")
    return factory(active_settings)  # type: ignore[return-value]


def get_activity_provider(settings: Settings | None = None) -> ActivityAvailabilityProvider | None:
    active_settings = settings or get_settings()
    selected = _selected_provider("activity", active_settings)
    if not selected:
        return None
    factory = _ACTIVITY_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown activity provider: {selected}")
    if selected == "viator" and not getattr(active_settings, "viator_api_key", ""):
        raise ValueError("Viator activity provider selected but VIATOR_API_KEY is empty")
    return factory(active_settings)  # type: ignore[return-value]
