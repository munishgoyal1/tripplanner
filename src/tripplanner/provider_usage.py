"""Durable, content-free accounting for external provider and model calls."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tripplanner.usage_attribution import current_attribution, current_batch
from tripplanner.validation.harness.pricing import (
    CATALOG_VERSION,
    GOOGLE_PLACES_USD_PER_REQUEST,
)

_CONTAINER = "provider_usage"
_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)
_LOCAL_RETENTION_DAYS = 90
_LAST_PRUNE_DAY = ""
_MAX_BATCH_RECORDS = 100


def _now() -> datetime:
    return datetime.now(UTC)


def _local_dir() -> Path:
    path = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner"))) / _CONTAINER
    path.mkdir(parents=True, exist_ok=True)
    return path


def _local_path(day: str) -> Path:
    return _local_dir() / f"{day}.jsonl"


def _estimate(provider: str, operation: str, sku_class: str) -> float | None:
    if provider == "google":
        return GOOGLE_PLACES_USD_PER_REQUEST.get(f"{operation}:{sku_class}")
    return None


def _write(record: dict[str, Any]) -> None:
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            storage_cosmos.upsert_doc(
                _CONTAINER,
                str(record["environment"]),
                str(record["id"]),
                record,
            )
            return
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("provider usage Cosmos write failed: %s", type(exc).__name__)

    _prune_local()
    path = _local_path(str(record["occurred_at"])[:10])
    with _LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def persist_batch(records: list[dict[str, Any]]) -> None:
    """Persist request-scoped call details in a bounded number of documents."""
    try:
        for start in range(0, len(records), _MAX_BATCH_RECORDS):
            entries = records[start : start + _MAX_BATCH_RECORDS]
            if not entries:
                continue
            first = entries[0]
            _write(
                {
                    "id": uuid.uuid4().hex,
                    "occurred_at": first["occurred_at"],
                    "day": first["day"],
                    "environment": first["environment"],
                    "interaction_id": first.get("interaction_id", ""),
                    "record_count": len(entries),
                    "entries": entries,
                }
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("provider usage batch write failed: %s", type(exc).__name__)


def _prune_local() -> None:
    global _LAST_PRUNE_DAY
    today = _now().date()
    if _LAST_PRUNE_DAY == today.isoformat():
        return
    cutoff = today - timedelta(days=_LOCAL_RETENTION_DAYS)
    for path in _local_dir().glob("*.jsonl"):
        try:
            if datetime.strptime(path.stem, "%Y-%m-%d").date() < cutoff:
                path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue
    _LAST_PRUNE_DAY = today.isoformat()


def record_call(
    *,
    provider: str,
    operation: str,
    status: str,
    duration_ms: float,
    sku_class: str = "",
    http_status: int | None = None,
    attempted: bool = True,
    billable: bool = True,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Persist one actual external call without request or response content."""
    occurred_at = _now().isoformat()
    attribution = current_attribution().fields()
    estimate = estimated_cost_usd
    if estimate is None and billable:
        estimate = _estimate(provider, operation, sku_class)
    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "occurred_at": occurred_at,
        "day": occurred_at[:10],
        "environment": attribution.get("environment", "local"),
        "initiator": attribution.get("initiator", "unattributed"),
        "interaction_id": attribution.get("interaction_id", ""),
        "trip_id": attribution.get("trip_id", ""),
        "route": attribution.get("route", ""),
        "interaction_kind": attribution.get("interaction_kind", "other"),
        "provider": provider,
        "operation": operation or "request",
        "sku_class": sku_class or "unknown",
        "status": status,
        "http_status": http_status,
        "duration_ms": round(max(0.0, duration_ms), 2),
        "attempted": attempted,
        "billable": billable,
        "prompt_tokens": max(0, int(prompt_tokens)),
        "completion_tokens": max(0, int(completion_tokens)),
        "estimated_cost_usd": round(estimate, 8) if estimate is not None else None,
        "pricing_catalog_version": CATALOG_VERSION,
    }
    batch = current_batch()
    if batch is not None:
        batch.append(record)
    else:
        persist_batch([record])
    return record


def _read_local(since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = since.date()
    today = _now().date()
    while day <= today:
        path = _local_path(day.isoformat())
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                        if datetime.fromisoformat(str(row["occurred_at"])) >= since:
                            rows.append(row)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
        day += timedelta(days=1)
    return rows


def _read(since: datetime) -> list[dict[str, Any]]:
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            container = storage_cosmos._container(_CONTAINER)  # noqa: SLF001
            query = "SELECT * FROM c WHERE c.occurred_at >= @since"
            documents = list(
                container.query_items(
                    query=query,
                    parameters=[{"name": "@since", "value": since.isoformat()}],
                    enable_cross_partition_query=True,
                )
            )
            return _expand(documents)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("provider usage Cosmos read failed: %s", type(exc).__name__)
    return _expand(_read_local(since))


def _expand(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        entries = document.get("entries")
        if isinstance(entries, list):
            rows.extend(entry for entry in entries if isinstance(entry, dict))
        else:
            rows.append(document)
    return rows


def _rollup(rows: list[dict[str, Any]], dimensions: tuple[str, ...]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(dimension) or "unattributed") for dimension in dimensions)
        buckets[key].append(row)
    results: list[dict[str, Any]] = []
    for key, items in buckets.items():
        known = [
            float(item["estimated_cost_usd"])
            for item in items
            if item.get("estimated_cost_usd") is not None
        ]
        result = {dimension: value for dimension, value in zip(dimensions, key)}
        result.update(
            {
                "calls": sum(1 for item in items if item.get("attempted", True)),
                "avoided_calls": sum(1 for item in items if not item.get("attempted", True)),
                "failures": sum(
                    1
                    for item in items
                    if item.get("attempted", True) and item.get("status") != "ok"
                ),
                "estimated_cost_usd": round(sum(known), 6),
                "unknown_cost_calls": sum(
                    1
                    for item in items
                    if item.get("billable", True) and item.get("estimated_cost_usd") is None
                ),
                "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in items),
                "completion_tokens": sum(int(item.get("completion_tokens") or 0) for item in items),
            }
        )
        results.append(result)
    return sorted(
        results,
        key=lambda item: (-int(item["calls"]),)
        + tuple(str(item[dimension]) for dimension in dimensions),
    )


def _trip_cost_summary(
    interactions: list[dict[str, Any]], interaction_kind: str
) -> dict[str, Any]:
    matching = [row for row in interactions if row.get("interaction_kind") == interaction_kind]
    interactions_count = len(matching)
    estimated_cost = round(sum(float(row["estimated_cost_usd"]) for row in matching), 6)
    return {
        "interactions": interactions_count,
        "trips": len(
            {
                str(row["trip_id"])
                for row in matching
                if row.get("trip_id") not in (None, "", "unattributed")
            }
        ),
        "calls": sum(int(row["calls"]) for row in matching),
        "estimated_cost_usd": estimated_cost,
        "average_estimated_cost_usd": round(
            estimated_cost / interactions_count if interactions_count else 0.0, 6
        ),
        "unknown_cost_interactions": sum(
            1 for row in matching if int(row["unknown_cost_calls"]) > 0
        ),
    }


def _add_trip_names(
    rollups: list[dict[str, Any]], trip_names: dict[str, str]
) -> list[dict[str, Any]]:
    for rollup in rollups:
        trip_id = str(rollup.get("trip_id") or "")
        if trip_id and trip_id != "unattributed":
            rollup["trip_name"] = trip_names.get(trip_id, "")
    return rollups


def summary(*, days: int = 30, trip_names: dict[str, str] | None = None) -> dict[str, Any]:
    period_days = max(1, min(90, int(days)))
    since = _now() - timedelta(days=period_days)
    rows = _read(since)
    totals = _rollup(rows, ())
    total = totals[0] if totals else {
        "calls": 0,
        "failures": 0,
        "avoided_calls": 0,
        "estimated_cost_usd": 0.0,
        "unknown_cost_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    names = trip_names or {}
    by_interaction = _add_trip_names(
        _rollup(
            rows,
            ("environment", "initiator", "interaction_kind", "trip_id", "interaction_id"),
        ),
        names,
    )
    return {
        "period_days": period_days,
        "since": since.isoformat(),
        "pricing": {
            "catalog_version": CATALOG_VERSION,
            "basis": "Planning estimates; provider billing exports remain authoritative.",
            "currency": "USD",
        },
        "totals": total,
        "by_initiator": _rollup(rows, ("environment", "initiator")),
        "trip_costs": {
            "new_trip": _trip_cost_summary(by_interaction, "new_trip"),
            "trip_update": _trip_cost_summary(by_interaction, "trip_update"),
            "infrastructure": {
                "allocation_status": "not_allocated",
                "basis": "Shared Azure infrastructure cost is not allocated per trip.",
            },
        },
        "by_interaction_kind": _rollup(rows, ("environment", "interaction_kind")),
        "by_trip": _add_trip_names(
            _rollup(rows, ("environment", "initiator", "interaction_kind", "trip_id")),
            names,
        ),
        "by_provider_total": _rollup(rows, ("environment", "provider")),
        "by_provider": _add_trip_names(
            _rollup(
                rows,
                (
                    "environment",
                    "initiator",
                    "interaction_kind",
                    "trip_id",
                    "interaction_id",
                    "provider",
                ),
            ),
            names,
        ),
        "by_operation": _add_trip_names(
            _rollup(
                rows,
                (
                    "environment",
                    "initiator",
                    "interaction_kind",
                    "trip_id",
                    "interaction_id",
                    "provider",
                    "operation",
                    "sku_class",
                ),
            ),
            names,
        ),
        "by_interaction": by_interaction,
    }
