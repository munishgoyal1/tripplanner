"""Currency conversion from published European Central Bank reference rates.

A converted amount is still a real amount: the rate is published, dated and
cached, and an unavailable rate returns ``None`` rather than an assumed parity.
Nothing here invents or estimates a price.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.frankfurter.dev/v1"
_RATE_TTL = timedelta(hours=12)
_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class RateTable:
    base: str
    rates: dict[str, float]
    fetched_at: datetime
    rate_date: str = ""

    @property
    def is_fresh(self) -> bool:
        return datetime.now(UTC) - self.fetched_at < _RATE_TTL


_cache: dict[str, RateTable] = {}


def clear_cache() -> None:
    _cache.clear()


def _fetch(base: str) -> RateTable | None:
    try:
        response = httpx.get(
            f"{_BASE_URL}/latest", params={"base": base}, timeout=_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("rates") or {}
        rates = {str(code).upper(): float(value) for code, value in raw.items()}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        logger.info("fx rates unavailable for %s: %s", base, type(exc).__name__)
        return None
    if not rates:
        return None
    return RateTable(
        base=base,
        rates=rates,
        fetched_at=datetime.now(UTC),
        rate_date=str(payload.get("date") or ""),
    )


def rate_table(base: str) -> RateTable | None:
    """Published rates for one base currency, refreshed at most twice a day.

    An expired table is still returned when a refresh fails; a real rate from
    this morning beats refusing to compare two prices at all.
    """
    base = (base or "").upper()
    if not base:
        return None
    cached = _cache.get(base)
    if cached and cached.is_fresh:
        return cached
    fetched = _fetch(base)
    if fetched is None:
        return cached
    _cache[base] = fetched
    return fetched


def convert(amount: float, from_currency: str, to_currency: str) -> float | None:
    """Return ``amount`` expressed in ``to_currency``, or None if no rate exists."""
    source = (from_currency or "").upper()
    target = (to_currency or "").upper()
    if not source or not target:
        return None
    if source == target:
        return amount
    table = rate_table(source)
    if table is None:
        return None
    rate = table.rates.get(target)
    if rate is None or rate <= 0:
        return None
    return amount * rate
