"""Configuration and environment variable loading."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

DEFAULT_AZURE_OPENAI_API_VERSION = "2024-10-21"


def _env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
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
    # NOTE: Amadeus Self-Service is being decommissioned on July 17, 2026.
    # Code preserved for future enterprise-tier migration. Prefer Duffel for new searches.
    # Sign up free (while available): https://developers.amadeus.com
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

    # Google Places API (New) — restaurant/attraction ratings & reviews
    # Get a key: https://console.cloud.google.com (enable 'Places API (New)')
    # Free tier: $200/month credit
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

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
    cosmos_database: str = os.getenv("COSMOS_DATABASE", "tripplanner")
    cosmos_emulator: bool = os.getenv("COSMOS_EMULATOR", "").strip() == "1"
    cosmos_dev_backend: str = Field(
        default_factory=lambda: os.getenv("COSMOS_DEV_BACKEND", "emulator").strip().lower()
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


@lru_cache
def get_settings() -> Settings:
    return Settings()

