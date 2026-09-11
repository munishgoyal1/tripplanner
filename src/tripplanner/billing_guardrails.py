"""Shared, cached loader for infra/billing-guardrails.json.

Single source of truth for Azure + GCP billing/alert config (see that file's
own top-level ``$comment``). Anything at runtime that needs one of those
values -- the in-app alert-condition mirror in ``alert_events.py``, or a
real GCP per-minute quota a caller should self-pace against -- reads it
through here instead of hand-rolling its own JSON load.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARDRAILS_PATH = _REPO_ROOT / "infra" / "billing-guardrails.json"

_cache: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_GUARDRAILS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a bad/missing config file must not break the app
            _cache = {}
    return _cache


def gcp_quota_per_minute(service: str, quota_id: str, *, default: int) -> int:
    """Real Google-enforced per-minute ceiling for the current environment.

    Used to self-pace outbound calls under the same number GCP itself
    enforces (infra/gcp/apply-billing-guardrails.ps1 applies these via
    ``gcloud quotas preferences``) -- exceeding it gets a real 429 from
    Google regardless of any in-app per-trip budget.
    """
    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    for quota in load().get("gcp", {}).get("quotas", []):
        if quota.get("service") == service and quota.get("quotaId") == quota_id:
            return int(quota.get(environment, quota.get("local", default)))
    return default


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None
