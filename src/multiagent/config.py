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
    # Sign up free: https://developers.amadeus.com
    amadeus_api_key: str = os.getenv("AMADEUS_API_KEY", "")
    amadeus_api_secret: str = os.getenv("AMADEUS_API_SECRET", "")
    amadeus_base_url: str = os.getenv(
        "AMADEUS_BASE_URL", "https://test.api.amadeus.com"
    )  # Use https://api.amadeus.com for production

    # Google Places API (New) — restaurant/attraction ratings & reviews
    # Get a key: https://console.cloud.google.com (enable 'Places API (New)')
    # Free tier: $200/month credit
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

    # Tavily web search — fresh travel content beyond LLM training cutoff
    # Sign up free: https://tavily.com (1000 searches/month free)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # General
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()
