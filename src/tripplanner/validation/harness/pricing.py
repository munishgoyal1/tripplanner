"""Versioned estimate catalogs used by harness reports, never billed-cost claims."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRate:
    input_per_million_usd: float
    output_per_million_usd: float
    cached_input_per_million_usd: float | None = None


CATALOG_VERSION = "2026-03-01"

# Planning assumptions copied from the application's existing usage estimator.
# They must be reviewed against the deployed Azure offer before financial decisions.
AZURE_OPENAI: tuple[tuple[str, TokenRate], ...] = (
    ("gpt-5", TokenRate(5.0, 15.0)),
    ("gpt-4.1-mini", TokenRate(0.15, 0.60)),
    ("gpt-4.1", TokenRate(3.0, 12.0)),
    ("gpt-4o-mini", TokenRate(0.15, 0.60)),
    ("gpt-4o", TokenRate(2.5, 10.0)),
    ("gpt-4", TokenRate(30.0, 60.0)),
    ("gpt-3.5", TokenRate(0.5, 1.5)),
)
DEFAULT_AZURE_OPENAI = TokenRate(1.0, 3.0)

# USD per request planning assumptions. Google pricing varies by account,
# region, free usage caps, and contract; billing export remains authoritative.
GOOGLE_PLACES_USD_PER_REQUEST = {
    "text_search:essentials": 0.032,
    "text_search:pro": 0.035,
    "text_search:enterprise_atmosphere": 0.040,
    "place_details:essentials": 0.005,
    "place_details:pro": 0.017,
    "place_details:enterprise_atmosphere": 0.025,
    "photo_media:photo_media": 0.007,
}


def azure_openai_rate(model: str) -> TokenRate:
    normalized = (model or "").lower().replace("-4-1", "-4.1")
    return next(
        (rate for prefix, rate in AZURE_OPENAI if normalized.startswith(prefix)),
        DEFAULT_AZURE_OPENAI,
    )
