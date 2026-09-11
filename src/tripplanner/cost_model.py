"""Cached loader for ``config/cost-model.json`` and the one USD->INR boundary.

Every ceiling in this application is denominated in **INR** (see
``limits_config.py``). Provider pricing catalogs -- ``validation.harness.pricing``
and the ``estimated_cost_usd`` field that ``provider_usage.record_call`` persists
-- are denominated in **USD**. Those two units meet in exactly one place: the
``usd_to_inr`` function below, called once when the cost ledger ingests a batch.

Mixing them silently multiplies a ceiling by ~88, which would open the budget far
beyond what the owner set, so the convention is enforced by naming rather than by
comment: every amount carries its unit in its identifier (``cost_inr``,
``estimated_cost_usd``, ``COST_CEILING_INR_DAILY``). ``tests/test_limits_derivation.py``
asserts no ceiling accessor returns an unconverted USD figure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODEL_PATH = _REPO_ROOT / "config" / "cost-model.json"

# Mirrors config/cost-model.json so a missing or unreadable file degrades to the
# same numbers rather than to zero -- a cost model that silently reads as zero
# would price every call at nothing and defeat the ceiling it feeds.
_FALLBACK: dict[str, Any] = {
    "fx": {"inrPerUsd": 88.0},
    "freePoolsPerMonth": {},
    "freePoolShare": {"local": 0.5, "canary": 0.15, "prod": 0.35},
    "quotaSizing": {"googleShareOfDailyCeiling": 0.5, "dailyHeadroom": 1.5,
                    "burstPerMinuteFloor": {}},
    "anomaly": {"ratioToMedian": 3.0, "absoluteFloorInr": 150.0, "minSamplesForMedian": 5},
    "reservation": {
        "reservePercentile": 75,
        "unknownCostPercentile": 95,
        "minSamples": 5,
        "seedReserveInr": {"new_trip": 60.0, "trip_update": 20.0},
        "seedUnknownInr": {"new_trip": 120.0, "trip_update": 40.0},
    },
}

_cache: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_MODEL_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a bad/missing model file must not break the app
            _cache = dict(_FALLBACK)
    return _cache


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def inr_per_usd() -> float:
    """FX rate used for the single USD->INR conversion in the cost ledger."""
    try:
        rate = float(load().get("fx", {}).get("inrPerUsd", 88.0))
    except (TypeError, ValueError):
        return 88.0
    return rate if rate > 0 else 88.0


def usd_to_inr(amount_usd: float | None) -> float:
    """Convert a provider-catalog USD amount to INR.

    The ONLY sanctioned crossing between the two units. Callers must name the
    result ``*_inr``; passing the result anywhere expecting USD, or a USD figure
    to anything expecting INR, is the failure this module exists to prevent.
    """
    if amount_usd is None:
        return 0.0
    try:
        return float(amount_usd) * inr_per_usd()
    except (TypeError, ValueError):
        return 0.0


def environment() -> str:
    return os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower() or "local"


def free_pool_per_month(sku: str) -> int:
    """Account-wide free monthly allowance for ``provider:sku_class``, 0 if none."""
    try:
        return int(load().get("freePoolsPerMonth", {}).get(sku, 0) or 0)
    except (TypeError, ValueError):
        return 0


def free_pool_share(env: str | None = None) -> float:
    shares = load().get("freePoolShare", {})
    try:
        return float(shares.get(env or environment(), 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def environment_free_pool(sku: str, env: str | None = None) -> int:
    """This environment's reserved slice of a pooled monthly allowance."""
    return int(free_pool_per_month(sku) * free_pool_share(env))


def anomaly_settings() -> dict[str, Any]:
    return dict(load().get("anomaly", _FALLBACK["anomaly"]))


def reservation_settings() -> dict[str, Any]:
    return dict(load().get("reservation", _FALLBACK["reservation"]))


def quota_sizing() -> dict[str, Any]:
    return dict(load().get("quotaSizing", _FALLBACK["quotaSizing"]))
