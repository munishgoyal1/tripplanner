"""Configuration and environment variable loading."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    # Azure OpenAI
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

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

