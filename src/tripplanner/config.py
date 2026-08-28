"""Configuration and environment variable loading."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=False)
_environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
load_dotenv(_REPO_ROOT / "config" / "environments" / f"{_environment}.env", override=False)

DEFAULT_AZURE_OPENAI_API_VERSION = "2024-10-21"


def _env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_positive_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


class Settings(BaseModel):
    # Azure OpenAI
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    azure_openai_api_version: str = Field(
        default_factory=lambda: os.getenv(
            "AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_OPENAI_API_VERSION
        )
    )

    # Amadeus Self-Service API (flights, hotels, activities)
    # PARKED: decommissioned 2026-07-17. Retained for a possible enterprise-tier
    # contract later. Requires ENABLE_AMADEUS_LEGACY=1 as well as credentials, so
    # adding a key alone never reactivates it.
    enable_amadeus_legacy: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_AMADEUS_LEGACY", "0").strip() == "1"
    )
    amadeus_api_key: str = os.getenv("AMADEUS_API_KEY", "")
    amadeus_api_secret: str = os.getenv("AMADEUS_API_SECRET", "")
    amadeus_base_url: str = os.getenv(
        "AMADEUS_BASE_URL", "https://test.api.amadeus.com"
    )  # Use https://api.amadeus.com for production

    # Duffel API (primary flight provider) — modern flight search & booking
    # Free test mode (no credit card): https://app.duffel.com/sign-up
    # Test tokens look like duffel_test_xxx and return synthetic offers.
    duffel_api_key: str = os.getenv("DUFFEL_API_KEY", "")

    # Read-only live hotel/flight rates. Booking operations are intentionally absent.
    liteapi_api_key: str = os.getenv("LITEAPI_API_KEY", "")
    liteapi_base_url: str = os.getenv(
        "LITEAPI_BASE_URL", "https://api.liteapi.travel/v3.0"
    ).rstrip("/")
    travel_hotel_provider: str = os.getenv("TRAVEL_HOTEL_PROVIDER", "auto").strip().lower()
    travel_flight_provider: str = os.getenv("TRAVEL_FLIGHT_PROVIDER", "auto").strip().lower()

    # OpenRouteService directions fallback. The free standard plan is suitable
    # for MVP coordinate-based driving, walking, and cycling route checks.
    openrouteservice_api_key: str = os.getenv("OPENROUTESERVICE_API_KEY", "")
    openrouteservice_base_url: str = os.getenv(
        "OPENROUTESERVICE_BASE_URL", "https://api.openrouteservice.org"
    ).rstrip("/")
    openrouteservice_route_ttl_sec: int = _env_positive_int(
        "OPENROUTESERVICE_ROUTE_TTL_SEC", 6 * 60 * 60
    )

    # Partner-gated transport candidates. Keep disabled until current approved
    # API access and free/sandbox terms are confirmed for this account.
    kiwi_api_key: str = os.getenv("KIWI_API_KEY", "")
    kiwi_base_url: str = os.getenv("KIWI_BASE_URL", "https://www.kiwi.com/api/v1").rstrip("/")

    # Omio affiliate Search API is partner-gated. Do not assume public/free API access.
    omio_api_key: str = os.getenv("OMIO_API_KEY", "")
    omio_base_url: str = os.getenv("OMIO_BASE_URL", "https://api.omio.com").rstrip("/")

    # Rail transport pricing providers (train, coach, ferry)
    enable_train_pricing: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_TRAIN_PRICING", "0").strip() == "1"
    )
    enable_coach_pricing: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_COACH_PRICING", "0").strip() == "1"
    )
    enable_ferry_pricing: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_FERRY_PRICING", "0").strip() == "1"
    )

    # Preferred rail transport provider. Only providers registered as active in
    # providers/registry.py are accepted; Kiwi/Omio remain inactive candidates.
    travel_train_provider: str = os.getenv("TRAVEL_TRAIN_PROVIDER", "auto").strip().lower()
    travel_coach_provider: str = os.getenv("TRAVEL_COACH_PROVIDER", "auto").strip().lower()
    travel_ferry_provider: str = os.getenv("TRAVEL_FERRY_PROVIDER", "auto").strip().lower()

    # Fare cache TTLs (in seconds)
    # Flight and hotel: 4 hours (highly dynamic)
    flight_cache_ttl_sec: int = _env_positive_int("FLIGHT_CACHE_TTL_SEC", 14400)
    hotel_cache_ttl_sec: int = _env_positive_int("HOTEL_CACHE_TTL_SEC", 14400)

    # Train, coach, ferry: 12 hours (less dynamic, stable day-of)
    train_cache_ttl_sec: int = _env_positive_int("TRAIN_CACHE_TTL_SEC", 43200)
    coach_cache_ttl_sec: int = _env_positive_int("COACH_CACHE_TTL_SEC", 43200)
    ferry_cache_ttl_sec: int = _env_positive_int("FERRY_CACHE_TTL_SEC", 43200)

    # Activity: 24 hours (least dynamic)
    activity_cache_ttl_sec: int = _env_positive_int("ACTIVITY_CACHE_TTL_SEC", 86400)

    # Driving has no fare to quote, so its running cost is arithmetic over
    # distance. Both must be set or no running cost is shown at all: a made-up
    # fuel price is exactly the kind of invented number this product refuses.
    road_fuel_price_per_litre: float = Field(
        default_factory=lambda: _env_positive_float("ROAD_FUEL_PRICE_PER_LITRE", 0.0)
    )
    road_fuel_litres_per_100km: float = Field(
        default_factory=lambda: _env_positive_float("ROAD_FUEL_LITRES_PER_100KM", 0.0)
    )
    road_cost_currency: str = os.getenv("ROAD_COST_CURRENCY", "").strip().upper()

    # Short-lived shared cache in front of the provider search tools. This is a
    # separate layer from the fare cache above, which backs transport comparisons.
    # Keep CACHE_REDIS_ENABLED=0 to use in-memory only.
    hotel_search_cache_ttl_sec: int = _env_positive_int("HOTEL_SEARCH_CACHE_TTL_SEC", 600)
    flight_search_cache_ttl_sec: int = _env_positive_int("FLIGHT_SEARCH_CACHE_TTL_SEC", 600)
    activity_search_cache_ttl_sec: int = _env_positive_int(
        "ACTIVITY_SEARCH_CACHE_TTL_SEC", 21600
    )
    cache_ttl_scale: float = Field(
        default_factory=lambda: _env_positive_float("CACHE_TTL_SCALE", 1.0)
    )
    cache_stable_forever: bool = Field(
        default_factory=lambda: os.getenv("CACHE_STABLE_FOREVER", "0").strip() == "1"
    )
    cache_volatile_forever: bool = Field(
        default_factory=lambda: os.getenv("CACHE_VOLATILE_FOREVER", "0").strip() == "1"
    )
    cache_warm_everything: bool = Field(
        default_factory=lambda: os.getenv("CACHE_WARM_EVERYTHING", "0").strip() == "1"
    )
    cache_redis_enabled: bool = Field(
        default_factory=lambda: os.getenv("CACHE_REDIS_ENABLED", "0").strip() == "1"
    )
    cache_redis_url: str = os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0")
    cache_redis_namespace: str = os.getenv("CACHE_REDIS_NAMESPACE", "tripplanner:provider-cache")
    cache_redis_connect_timeout_sec: float = _env_positive_float(
        "CACHE_REDIS_CONNECT_TIMEOUT_SEC", 0.2
    )
    cache_redis_socket_timeout_sec: float = _env_positive_float(
        "CACHE_REDIS_SOCKET_TIMEOUT_SEC", 0.2
    )

    def cache_ttl(self, seconds: int | float) -> int:
        """Apply the environment-wide cache lifetime control."""
        return max(1, round(float(seconds) * self.cache_ttl_scale))

    def stable_cache_ttl(self, seconds: int | float) -> int:
        """Resolve a stable-data TTL; -1 means the entry never expires."""
        return -1 if self.cache_stable_forever else self.cache_ttl(seconds)

    def volatile_cache_ttl(self, seconds: int | float) -> int:
        """Resolve a fast-varying-data TTL; -1 means the entry never expires."""
        return -1 if self.cache_volatile_forever else self.cache_ttl(seconds)

    # Static schedule estimates used only when a persisted itinerary or live
    # provider does not contain the corresponding operational timing.
    flight_duration_default_min: int = _env_positive_int("FLIGHT_DURATION_DEFAULT_MIN", 90)
    airport_departure_buffer_min: int = _env_positive_int("AIRPORT_DEPARTURE_BUFFER_MIN", 120)
    airport_arrival_buffer_min: int = _env_positive_int("AIRPORT_ARRIVAL_BUFFER_MIN", 45)
    railway_departure_buffer_min: int = _env_positive_int("RAILWAY_DEPARTURE_BUFFER_MIN", 45)
    railway_arrival_buffer_min: int = _env_positive_int("RAILWAY_ARRIVAL_BUFFER_MIN", 15)
    bus_departure_buffer_min: int = _env_positive_int("BUS_DEPARTURE_BUFFER_MIN", 30)
    bus_arrival_buffer_min: int = _env_positive_int("BUS_ARRIVAL_BUFFER_MIN", 15)

    # Read-only Viator tours and activity schedules. Transactional APIs are absent.
    viator_api_key: str = os.getenv("VIATOR_API_KEY", "")
    viator_base_url: str = os.getenv(
        "VIATOR_BASE_URL", "https://api.sandbox.viator.com/partner"
    ).rstrip("/")
    travel_activity_provider: str = os.getenv("TRAVEL_ACTIVITY_PROVIDER", "auto").strip().lower()

    # Google Places API (New) is a paid provider. A key alone is insufficient:
    # the owner must explicitly enable it for the current environment.
    enable_google_places: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_GOOGLE_PLACES", "0").strip() == "1"
    )
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
    google_places_metadata_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_METADATA_CACHE_TTL_SEC", 604800
        )
    )
    google_places_search_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_SEARCH_CACHE_TTL_SEC", 604800
        )
    )
    google_places_reviews_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_REVIEWS_CACHE_TTL_SEC", 604800
        )
    )
    google_places_miss_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int("GOOGLE_PLACES_MISS_CACHE_TTL_SEC", 60)
    )
    google_places_hours_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_HOURS_CACHE_TTL_SEC", 7200
        )
    )
    google_places_photo_url_cache_ttl_sec: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_PHOTO_URL_CACHE_TTL_SEC", 3000
        )
    )
    google_places_max_text_searches_per_trip: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_TRIP", 3
        )
    )
    google_places_max_review_details_per_trip: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_MAX_REVIEW_DETAILS_PER_TRIP", 1
        )
    )
    google_places_max_photos_per_trip: int = Field(
        default_factory=lambda: _env_positive_int("GOOGLE_PLACES_MAX_PHOTOS_PER_TRIP", 3)
    )
    google_places_max_photos_per_place: int = Field(
        default_factory=lambda: _env_positive_int(
            "GOOGLE_PLACES_MAX_PHOTOS_PER_PLACE", 1
        )
    )

    # Google Maps JavaScript API — browser-side key for the interactive trip
    # map (pins, day routes). MUST be a SEPARATE key from google_places_api_key
    # because it is exposed to the browser: lock it down with an HTTP-referrer
    # restriction + restrict it to "Maps JavaScript API" + "Directions API" in
    # the Cloud console. Leave empty to disable the map panel entirely.
    google_maps_browser_key: str = os.getenv("GOOGLE_MAPS_BROWSER_KEY", "")

    # GA4 measurement id exposed to the browser only in production. This is a
    # public identifier, not a credential; leave empty to disable analytics.
    google_analytics_measurement_id: str = os.getenv("GOOGLE_ANALYTICS_MEASUREMENT_ID", "")

    # Tavily web search — fresh travel content beyond LLM training cutoff
    # Sign up free: https://tavily.com (1000 searches/month free)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Azure Cosmos DB — persistent storage for hosted multi-user mode.
    # When set, the trip planner persists preferences and trips here instead
    # of ~/.tripplanner/. Leave empty for local CLI / test mode.
    # Use the NoSQL API and enable Free Tier (1000 RU/s + 25 GB free).
    cosmos_endpoint: str = os.getenv("COSMOS_ENDPOINT", "")
    cosmos_key: str = os.getenv("COSMOS_KEY", "")
    cosmos_connection_string: str = os.getenv("COSMOS_CONNECTION_STRING", "")
    cosmos_use_managed_identity: bool = (
        os.getenv("COSMOS_USE_MANAGED_IDENTITY", "").strip() == "1"
    )
    cosmos_database: str = os.getenv("COSMOS_DATABASE", "tripplanner")
    cosmos_emulator: bool = os.getenv("COSMOS_EMULATOR", "").strip() == "1"
    cosmos_dev_backend: str = Field(
        default_factory=lambda: os.getenv("COSMOS_DEV_BACKEND", "emulator").strip().lower()
    )
    secondary_durable_cache_enabled: bool = Field(
        default_factory=lambda: os.getenv("SECONDARY_DURABLE_CACHE_ENABLED", "0").strip()
        == "1"
    )
    secondary_durable_cache_endpoint: str = os.getenv(
        "SECONDARY_DURABLE_CACHE_ENDPOINT", ""
    )
    secondary_durable_cache_key: str = os.getenv("SECONDARY_DURABLE_CACHE_KEY", "")
    secondary_durable_cache_connection_string: str = os.getenv(
        "SECONDARY_DURABLE_CACHE_CONNECTION_STRING", ""
    )
    secondary_durable_cache_use_managed_identity: bool = (
        os.getenv("SECONDARY_DURABLE_CACHE_USE_MANAGED_IDENTITY", "").strip() == "1"
    )
    secondary_durable_cache_database: str = os.getenv(
        "SECONDARY_DURABLE_CACHE_DATABASE", "tripplanner-cache"
    )
    secondary_durable_cache_emulator: bool = (
        os.getenv("SECONDARY_DURABLE_CACHE_EMULATOR", "").strip() == "1"
    )

    # General
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # When set to "1", logs to stdout in JSON form (queryable in Log Analytics
    # / Kusto). Auto-on when COSMOS_ENDPOINT is set (hosted mode). Leave unset
    # for human-friendly text logs in local dev.
    log_json: str = os.getenv("LOG_JSON", "")
    # When "1", on_message ALSO writes the raw user message body to the
    # restricted audit sink (Cosmos container `audit_events` in hosted mode,
    # ~/.tripplanner/audit/<date>.jsonl locally). The app log only sees
    # length/word count -- never the content.
    audit_user_messages: str = os.getenv("AUDIT_USER_MESSAGES", "")

    # Shows the recorded comparisons in the workspace and accepts overrules.
    # Off leaves the records being written but hides them, so a half-finished
    # surface never reaches a traveller.
    decisions_ui_enabled: bool = Field(
        default_factory=lambda: os.getenv("DECISIONS_UI_ENABLED", "1").strip() != "0"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
