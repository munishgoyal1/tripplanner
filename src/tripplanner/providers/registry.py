"""Small capability registry for configured travel inventory providers."""

from __future__ import annotations

from collections.abc import Callable

from tripplanner.config import Settings, get_settings
from tripplanner.providers.liteapi import LiteAPIProvider
from tripplanner.providers.models import (
    ActivityAvailabilityProvider,
    CoachAvailabilityProvider,
    FerryAvailabilityProvider,
    FlightAvailabilityProvider,
    HotelAvailabilityProvider,
    ProviderAccess,
    ProviderCandidate,
    ProviderCapability,
    RailAvailabilityProvider,
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
_TRAIN_PROVIDERS: dict[str, ProviderFactory] = {}
_COACH_PROVIDERS: dict[str, ProviderFactory] = {}
_FERRY_PROVIDERS: dict[str, ProviderFactory] = {}


_PROVIDER_CATALOG: tuple[ProviderCandidate, ...] = (
    ProviderCandidate(
        name="liteapi",
        capabilities=[
            ProviderCapability.HOTEL_SEARCH,
            ProviderCapability.HOTEL_VERIFY,
            ProviderCapability.FLIGHT_SEARCH,
            ProviderCapability.FLIGHT_VERIFY,
        ],
        access=ProviderAccess.ACTIVE_FREE_OR_SANDBOX,
        free_mvp_ok=True,
        enabled=True,
        notes="Nuitee/LiteAPI advertises a production-like sandbox and search/prebook/book flow.",
    ),
    ProviderCandidate(
        name="viator",
        capabilities=[ProviderCapability.ACTIVITY_SEARCH, ProviderCapability.TICKET_SEARCH],
        access=ProviderAccess.PARTNER_GATED,
        free_mvp_ok=True,
        enabled=True,
        notes="Affiliate signup is free; full API access requires suitable partner approval.",
    ),
    ProviderCandidate(
        name="openmeteo",
        capabilities=[],
        access=ProviderAccess.PUBLIC_OPEN,
        free_mvp_ok=True,
        enabled=True,
        requires_key=False,
        notes="Used by weather tools, not this inventory registry.",
    ),
    ProviderCandidate(
        name="gtfs_open_trip_planner",
        capabilities=[ProviderCapability.ROUTE_COMPUTE],
        access=ProviderAccess.PUBLIC_OPEN,
        free_mvp_ok=True,
        requires_key=False,
        notes="Recommended public-transit direction; adapter not implemented yet.",
    ),
    ProviderCandidate(
        name="openrouteservice",
        capabilities=[ProviderCapability.ROUTE_COMPUTE],
        access=ProviderAccess.ACTIVE_FREE_OR_SANDBOX,
        free_mvp_ok=True,
        notes="Free developer routing tier exists; adapter not implemented yet.",
    ),
    ProviderCandidate(
        name="travelpayouts",
        capabilities=[ProviderCapability.FLIGHT_SEARCH, ProviderCapability.HOTEL_SEARCH],
        access=ProviderAccess.PARTNER_GATED,
        free_mvp_ok=True,
        notes="Affiliate/deep-link candidate; API docs require partner account validation.",
    ),
    ProviderCandidate(
        name="tiqets",
        capabilities=[ProviderCapability.TICKET_SEARCH],
        access=ProviderAccess.PARTNER_GATED,
        free_mvp_ok=True,
        notes="Distributor API exists; production access is partner-gated.",
    ),
    ProviderCandidate(
        name="kiwi",
        capabilities=[
            ProviderCapability.FLIGHT_SEARCH,
            ProviderCapability.TRAIN_SEARCH,
            ProviderCapability.COACH_SEARCH,
        ],
        access=ProviderAccess.PARTNER_GATED,
        free_mvp_ok=False,
        notes=(
            "Tequila is a partner platform; do not auto-enable without "
            "current approved API access."
        ),
    ),
    ProviderCandidate(
        name="omio",
        capabilities=[ProviderCapability.TRAIN_SEARCH, ProviderCapability.COACH_SEARCH],
        access=ProviderAccess.PARTNER_GATED,
        free_mvp_ok=False,
        notes="Affiliate Search API is partner-gated; do not auto-enable as a free public API.",
    ),
    ProviderCandidate(
        name="hafas_rest_transport_rest",
        capabilities=[ProviderCapability.TRAIN_SEARCH, ProviderCapability.COACH_SEARCH],
        access=ProviderAccess.PUBLIC_OPEN,
        free_mvp_ok=False,
        enabled=False,
        requires_key=False,
        notes=(
            "Community-run hafas-rest-api mirrors (v6.db.transport.rest). Keyless and "
            "schema-verified, but a single-maintainer best-effort host: db returned 503 "
            "for an entire evaluation session. Rejected as a non-mainstream source; "
            "reference adapter kept on branch hafas-rest-provider."
        ),
    ),
)


def provider_catalog() -> list[ProviderCandidate]:
    return [candidate.model_copy(deep=True) for candidate in _PROVIDER_CATALOG]


def _selected_provider(kind: str, settings: Settings) -> str | None:
    selected = getattr(settings, f"travel_{kind}_provider", "auto")
    if selected == "legacy":
        return None
    if selected == "auto":
        if kind == "activity":
            return "viator" if getattr(settings, "viator_api_key", "") else None
        if kind in ("hotel", "flight"):
            return "liteapi" if getattr(settings, "liteapi_api_key", "") else None
        return None
    return selected


def _providers_for(
    kind: str,
    settings: Settings,
    registry: dict[str, ProviderFactory],
) -> list[object]:
    selected = _selected_provider(kind, settings)
    if not selected:
        return []
    if selected == "auto":
        return []
    names = [name.strip() for name in selected.split(",") if name.strip()]
    providers: list[object] = []
    for name in names:
        factory = registry.get(name)
        if not factory:
            raise ValueError(f"Unknown or inactive {kind} provider: {name}")
        providers.append(factory(settings))
    return providers


def get_hotel_providers(settings: Settings | None = None) -> list[HotelAvailabilityProvider]:
    active_settings = settings or get_settings()
    providers = _providers_for("hotel", active_settings, _HOTEL_PROVIDERS)
    if (
        providers
        and any(provider.name == "liteapi" for provider in providers)
        and not getattr(active_settings, "liteapi_api_key", "")
    ):
        raise ValueError("LiteAPI hotel provider selected but LITEAPI_API_KEY is empty")
    return providers  # type: ignore[return-value]


def get_flight_providers(settings: Settings | None = None) -> list[FlightAvailabilityProvider]:
    active_settings = settings or get_settings()
    providers = _providers_for("flight", active_settings, _FLIGHT_PROVIDERS)
    if (
        providers
        and any(provider.name == "liteapi" for provider in providers)
        and not getattr(active_settings, "liteapi_api_key", "")
    ):
        raise ValueError("LiteAPI flight provider selected but LITEAPI_API_KEY is empty")
    return providers  # type: ignore[return-value]


def get_activity_providers(settings: Settings | None = None) -> list[ActivityAvailabilityProvider]:
    active_settings = settings or get_settings()
    providers = _providers_for("activity", active_settings, _ACTIVITY_PROVIDERS)
    if (
        providers
        and any(provider.name == "viator" for provider in providers)
        and not getattr(active_settings, "viator_api_key", "")
    ):
        raise ValueError("Viator activity provider selected but VIATOR_API_KEY is empty")
    return providers  # type: ignore[return-value]


def get_hotel_provider(settings: Settings | None = None) -> HotelAvailabilityProvider | None:
    providers = get_hotel_providers(settings)
    return providers[0] if providers else None


def get_flight_provider(settings: Settings | None = None) -> FlightAvailabilityProvider | None:
    providers = get_flight_providers(settings)
    return providers[0] if providers else None


def get_activity_provider(settings: Settings | None = None) -> ActivityAvailabilityProvider | None:
    providers = get_activity_providers(settings)
    return providers[0] if providers else None


def get_train_provider(settings: Settings | None = None) -> RailAvailabilityProvider | None:
    active_settings = settings or get_settings()
    if not active_settings.enable_train_pricing:
        return None
    selected = _selected_provider("train", active_settings)
    if not selected:
        return None
    factory = _TRAIN_PROVIDERS.get(selected)
    if not factory:
        raise ValueError(f"Unknown or inactive train provider: {selected}")
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
        raise ValueError(f"Unknown or inactive coach provider: {selected}")
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
        raise ValueError(f"Unknown or inactive ferry provider: {selected}")
    return factory(active_settings)  # type: ignore[return-value]
