"""Versioned estimate catalogs used by harness reports, never billed-cost claims."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRate:
    input_per_million_usd: float
    output_per_million_usd: float
    cached_input_per_million_usd: float | None = None


CATALOG_VERSION = "2026-09-10"

# Azure Global Standard list-price planning assumptions, verified 2026-09-09
# against public Azure OpenAI token tables (not the owner's billed invoice).
# Longest prefix wins so gpt-5.4-mini is never priced as gpt-5.
AZURE_OPENAI: tuple[tuple[str, TokenRate], ...] = (
    ("gpt-5.4-mini", TokenRate(0.75, 4.50, 0.08)),
    ("gpt-5.4-nano", TokenRate(0.20, 1.25)),
    ("gpt-5.4-pro", TokenRate(30.0, 180.0)),
    ("gpt-5.4", TokenRate(2.50, 15.0, 0.25)),
    ("gpt-5.2", TokenRate(1.75, 14.0)),
    ("gpt-5.1", TokenRate(1.25, 10.0)),
    ("gpt-5-mini", TokenRate(0.25, 2.00)),
    ("gpt-5-nano", TokenRate(0.05, 0.40)),
    ("gpt-5-pro", TokenRate(15.0, 120.0)),
    ("gpt-5", TokenRate(1.25, 10.0, 0.13)),
    ("gpt-4.1-mini", TokenRate(0.40, 1.60)),
    ("gpt-4.1-nano", TokenRate(0.10, 0.40)),
    ("gpt-4.1", TokenRate(2.00, 8.00)),
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
    "text_search:pro": 0.032,
    "text_search:enterprise_atmosphere": 0.040,
    "place_details:essentials": 0.005,
    "place_details:pro": 0.017,
    "place_details:enterprise_atmosphere": 0.025,
    "photo_media:photo_media": 0.007,
}

# Azure deployment names cannot contain a dot, so gpt-5.4-mini may appear as
# gpt-5-4-mini. Convert digit-digit hyphens before prefix matching.
_VERSION_SEPARATOR_RE = re.compile(r"(?<=\d)-(?=\d)")


def normalize_model_name(model: str) -> str:
    return _VERSION_SEPARATOR_RE.sub(".", (model or "").lower())


def azure_openai_rate(model: str) -> TokenRate:
    normalized = normalize_model_name(model)
    matches = [
        (prefix, rate)
        for prefix, rate in AZURE_OPENAI
        if normalized.startswith(prefix)
    ]
    if not matches:
        return DEFAULT_AZURE_OPENAI
    return max(matches, key=lambda item: len(item[0]))[1]
