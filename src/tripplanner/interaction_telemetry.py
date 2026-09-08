"""Content-safe local study traces for attributed interactions."""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tripplanner.json_store import atomic_write_json

SCHEMA_VERSION = 1
_HOSTED_ENVIRONMENTS = {"canary", "prod", "production"}
_LOGGER = logging.getLogger(__name__)


def _root() -> Path:
    home = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    return home / "trip-telemetry" / "interactions"


def _is_enabled(environment: str) -> bool:
    if environment.strip().lower() in _HOSTED_ENVIRONMENTS:
        return False
    return os.getenv("TRIPPLANNER_INTERACTION_TELEMETRY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "interaction"


def persist_interaction(
    attribution: dict[str, str],
    events: list[dict[str, Any]],
    provider_calls: list[dict[str, Any]],
) -> Path | None:
    """Write one readable interaction artifact without prompts or provider payloads."""
    environment = attribution.get("environment", "local")
    if not _is_enabled(environment):
        return None

    occurred_at = str(
        (events[0] if events else provider_calls[0] if provider_calls else {}).get(
            "occurred_at", datetime.now(UTC).isoformat()
        )
    )
    day = occurred_at[:10]
    interaction_id = attribution.get("interaction_id", "")
    path = _root() / day / f"{_safe_id(interaction_id)}.json"
    try:
        atomic_write_json(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "interaction": attribution,
                "occurred_at": occurred_at,
                "event_count": len(events),
                "provider_call_count": len(provider_calls),
                "events": events,
                "provider_calls": provider_calls,
            },
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must never fail a request
        _LOGGER.warning("interaction telemetry write failed: %s", type(exc).__name__)
        return None
    return path
