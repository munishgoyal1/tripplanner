"""Small capability registry for configured travel inventory providers."""

from __future__ import annotations

from collections.abc import Callable

from tripplanner.config import Settings, get_settings
from tripplanner.providers.hafas_rest_client import HafasRestCoachSource, HafasRestTrainSource
from tripplanner.providers.kiwi_client import KiwiCoachSource, KiwiFerrySource, KiwiTrainSource
from tripplanner.providers.liteapi import LiteAPIProvider
from tripplanner.providers.models import (
    ActivityAvailabilityProvider,
    CoachAvailabilityProvider,
    FerryAvailabilityProvider,
    FlightAvailabilityProvider,
    HotelAvailabilityProvider,
    RailAvailabilityProvider,
)
from tripplanner.providers.viator import ViatorProvider

ProviderFactory = Callable[[Settings], object]


def _liteapi(settings: Settings) -> LiteAPIProvider:
    return LiteAPIProvider(settings.liteapi_api_key, settings.liteapi_base_url)


def _viator(settings: Settings) -> ViatorProvider:
    return ViatorProvider(settings.viator_api_key, settings.viator_base_url)


def _kiwi_train(settings: Settings) -> KiwiTrainSource:
    return KiwiTrainSource(settings.kiwi_api_key, settings.kiwi_base_url)


def _kiwi_coach(settings: Settings) -> KiwiCoachSource:
    return KiwiCoachSource(settings.kiwi_api_key, settings.kiwi_base_url)


def _kiwi_ferry(settings: Settings) -> KiwiFerrySource:
    return KiwiFerrySource(settings.kiwi_api_key, settings.kiwi_base_url)


def _hafas_train(settings: Settings) -> HafasRestTrainSource:
    return HafasRestTrainSource(settings.hafas_rest_base_url)


def _hafas_coach(settings: Settings) -> HafasRestCoachSource:
    return HafasRestCoachSource(settings.hafas_rest_base_url)


_HOTEL_PROVIDERS: dict[str, ProviderFactory] = {"liteapi": _liteapi}
_FLIGHT_PROVIDERS: dict[str, ProviderFactory] = {"liteapi": _liteapi}
_ACTIVITY_PROVIDERS: dict[str, ProviderFactory] = {"viator": _viator}
_TRAIN_PROVIDERS: dict[str, ProviderFactory] = {"kiwi": _kiwi_train, "hafas": _hafas_train}
_COACH_PROVIDERS: dict[str, ProviderFactory] = {"kiwi": _kiwi_coach, "hafas": _hafas_coach}
_FERRY_PROVIDERS: dict[str, ProviderFactory] = {"kiwi": _kiwi_ferry}


def _selected_provider(kind: str, settings: Settings) -> str | None:
    selected = getattr(settings, f"travel_{kind}_provider", "auto")
    if selected == "legacy":
        return None
    if selected == "auto":
        if kind == "activity":
            return "viator" if getattr(settings, "viator_api_key", "") else None
        if kind in ("train", "coach"):
            # Prefer a keyed provider; HAFAS REST needs no key so it is the floor.
            if getattr(settings, "kiwi_api_key", ""):
                return "kiwi"
            return "hafas" if getattr(settings, "hafas_rest_base_url", "") else None
        if kind == "ferry":
            return "kiwi" if getattr(settings, "kiwi_api_key", "") else None
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


def get_train_provider(settings: Settings | None = None) -> RailAvailabilityProvider | None:
    active_settings = settings or get_settings()
    if not active_settings.enable_train_pricing:
        return None
    selected = _selected_provider("train", active_settings)
    if not selected:
        return None
    factory = _TRAIN_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown train provider: {selected}")
    if selected == "kiwi" and not getattr(active_settings, "kiwi_api_key", ""):
        raise ValueError("Kiwi train provider selected but KIWI_API_KEY is empty")
    if selected == "hafas" and not getattr(active_settings, "hafas_rest_base_url", ""):
        raise ValueError("HAFAS train provider selected but HAFAS_REST_BASE_URL is empty")
    return factory(active_settings)  # type: ignore[return-value]


def get_coach_provider(settings: Settings | None = None) -> CoachAvailabilityProvider | None:
    active_settings = settings or get_settings()
    if not active_settings.enable_coach_pricing:
        return None
    selected = _selected_provider("coach", active_settings)
    if not selected:
        return None
    factory = _COACH_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown coach provider: {selected}")
    if selected == "kiwi" and not getattr(active_settings, "kiwi_api_key", ""):
        raise ValueError("Kiwi coach provider selected but KIWI_API_KEY is empty")
    if selected == "hafas" and not getattr(active_settings, "hafas_rest_base_url", ""):
        raise ValueError("HAFAS coach provider selected but HAFAS_REST_BASE_URL is empty")
    return factory(active_settings)  # type: ignore[return-value]


def get_ferry_provider(settings: Settings | None = None) -> FerryAvailabilityProvider | None:
    active_settings = settings or get_settings()
    if not active_settings.enable_ferry_pricing:
        return None
    selected = _selected_provider("ferry", active_settings)
    if not selected:
        return None
    factory = _FERRY_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown ferry provider: {selected}")
    if selected == "kiwi" and not getattr(active_settings, "kiwi_api_key", ""):
        raise ValueError("Kiwi ferry provider selected but KIWI_API_KEY is empty")
    return factory(active_settings)  # type: ignore[return-value]
