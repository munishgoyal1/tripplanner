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

from tripplanner import http_client
from tripplanner.caching import get_cache

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.frankfurter.dev/v1"
_RATE_TTL = timedelta(hours=12)
# The entry outlives its freshness on purpose: a stale table is still a real
# rate, and rate_table falls back to it when a refresh fails.
_RETENTION_SECONDS = int(timedelta(days=7).total_seconds())
_cache = get_cache("fx-rates", default_ttl_seconds=_RETENTION_SECONDS)


@dataclass(frozen=True)
class RateTable:
    base: str
    rates: dict[str, float]
    fetched_at: datetime
    rate_date: str = ""

    @property
    def is_fresh(self) -> bool:
        return datetime.now(UTC) - self.fetched_at < _RATE_TTL

    def to_payload(self) -> dict:
        return {
            "base": self.base,
            "rates": self.rates,
            "fetched_at": self.fetched_at.isoformat(),
            "rate_date": self.rate_date,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> RateTable | None:
        try:
            return cls(
                base=str(payload["base"]),
                rates={str(k): float(v) for k, v in (payload["rates"] or {}).items()},
                fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
                rate_date=str(payload.get("rate_date") or ""),
            )
        except (KeyError, TypeError, ValueError):
            return None


def clear_cache() -> None:
    _cache.clear()


def _fetch(base: str) -> RateTable | None:
    try:
        response = http_client.get(f"{_BASE_URL}/latest", params={"base": base})
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
    payload = _cache.get(base)
    cached = RateTable.from_payload(payload) if isinstance(payload, dict) else None
    if cached and cached.is_fresh:
        return cached
    fetched = _fetch(base)
    if fetched is None:
        return cached
    _cache.set(base, fetched.to_payload())
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
