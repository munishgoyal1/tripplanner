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
    failed = any(event.get("error") or event.get("status") in {"error", "failed"}
                 or event.get("outcome") in {"error", "failed"} for event in events)
    if (attribution.get("initiator") != "user_trip" and not failed
            and not any(call.get("attempted", True) for call in provider_calls)):
        return None

    occurred_at = str(
        (events[0] if events else provider_calls[0] if provider_calls else {}).get(
            "occurred_at", datetime.now(UTC).isoformat()
        )
    )
    day = occurred_at[:10]
    interaction_id = attribution.get("interaction_id", "")
    path = _root() / day / f"{_safe_id(interaction_id)}.json"
    semantic_events = [event for event in events if event.get("kind") != "telemetry_summary"]
    aggregated_events = sum(
        int(event.get("aggregated_event_count") or 0)
        for event in events
        if event.get("kind") == "telemetry_summary"
    )
    try:
        atomic_write_json(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "interaction": attribution,
                "occurred_at": occurred_at,
                "event_count": len(semantic_events) + aggregated_events,
                "provider_call_count": sum(
                    int(call.get("units") or 1) for call in provider_calls
                ),
                "events": events if len(events) <= 200 else events[:100] + events[-100:],
                "provider_calls": provider_calls[:100],
                "detail_truncated": len(events) > 200 or len(provider_calls) > 100,
            },
        )
        from tripplanner.diagnostic_retention import schedule_prune

        schedule_prune(_root(), "*/*.json", max_bytes=50 * 1024 * 1024,
                       max_age=7 * 24 * 60 * 60)
    except Exception as exc:  # noqa: BLE001 - telemetry must never fail a request
        _LOGGER.warning("interaction telemetry write failed: %s", type(exc).__name__)
        return None
    return path
