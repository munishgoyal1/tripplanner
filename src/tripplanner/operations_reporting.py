"""Durable owner-only snapshots for the operations dashboard."""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from tripplanner import storage_cosmos
from tripplanner.config import get_settings

_LOGGER = logging.getLogger(__name__)
_PRODUCT_CONTAINER = "product_events"
_PAGES = frozenset({"welcome", "planner", "operations"})


def _event_path(day: str) -> Path:
    root = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    path = root / _PRODUCT_CONTAINER
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{day}.jsonl"


def _bucket(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def persist_product_event(
    event: str,
    session_id: str,
    *,
    user_id: str | None,
    country: str,
    source: str,
    page: str,
) -> None:
    occurred_at = datetime.now(UTC).isoformat()
    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    record = {
        "id": uuid.uuid4().hex,
        "user_id": environment,
        "occurred_at": occurred_at,
        "event": event,
        "session_bucket": _bucket(session_id),
        "user_bucket": _bucket(user_id) if user_id else _bucket(session_id),
        "country": country,
        "source": source,
        "page": page if page in _PAGES else "other",
    }
    try:
        if storage_cosmos.is_enabled():
            storage_cosmos.upsert_doc(
                _PRODUCT_CONTAINER, environment, str(record["id"]), record
            )
            return
        if environment in {"canary", "prod", "production"}:
            return
        with _event_path(occurred_at[:10]).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001 - analytics never fails the request
        _LOGGER.warning("product analytics persistence failed: %s", type(exc).__name__)


def _range(
    days: int,
    start_date: date | None,
    end_date: date | None,
) -> tuple[datetime, datetime, int]:
    today = datetime.now(UTC).date()
    if start_date is not None or end_date is not None:
        last_day = min(end_date or today, today)
        first_day = start_date or last_day - timedelta(days=29)
        if first_day > last_day:
            raise ValueError("start_date must not be after end_date")
    else:
        period_days = max(1, min(365, int(days)))
        last_day = today
        first_day = last_day - timedelta(days=period_days - 1)
    since = datetime.combine(first_day, time.min, tzinfo=UTC)
    until = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=UTC)
    return since, until, (last_day - first_day).days + 1


def _read_product_events(since: datetime, until: datetime) -> list[dict[str, Any]]:
    if storage_cosmos.is_enabled():
        return storage_cosmos.operations_query(
            _PRODUCT_CONTAINER,
            "SELECT * FROM c WHERE c.occurred_at >= @since AND c.occurred_at < @until",
            [
                {"name": "@since", "value": since.isoformat()},
                {"name": "@until", "value": until.isoformat()},
            ],
        )
    rows: list[dict[str, Any]] = []
    day = since.date()
    while day < until.date():
        path = _event_path(day.isoformat())
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    occurred_at = datetime.fromisoformat(str(row["occurred_at"]))
                    if since <= occurred_at < until:
                        rows.append(row)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        day += timedelta(days=1)
    return rows


def _all_documents(container: str) -> list[dict[str, Any]]:
    try:
        return storage_cosmos.operations_query(container, "SELECT * FROM c")
    except Exception as exc:  # noqa: BLE001 - one dataset must not hide the dashboard
        _LOGGER.warning("operations query failed for %s: %s", container, type(exc).__name__)
        return []


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or UTC)
    except ValueError:
        return None


def _in_range(value: Any, since: datetime, until: datetime) -> bool:
    parsed = _timestamp(value)
    return parsed is not None and since <= parsed < until


def _trip_rows(since: datetime, until: datetime) -> tuple[list[dict[str, Any]], dict[str, int]]:
    trips = _all_documents("trips")
    chats = {
        (str(row.get("user_id") or ""), str(row.get("id") or "")[5:]): row
        for row in _all_documents("users")
        if str(row.get("id") or "").startswith("chat_")
        and row.get("id") != "chat_operations"
    }
    feedback: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _all_documents("trip_feedback"):
        key = (str(row.get("user_id") or ""), str(row.get("trip_id") or ""))
        feedback.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    total_turns = 0
    total_updates = 0
    for trip in trips:
        user_id = str(trip.get("user_id") or "")
        trip_id = str(trip.get("trip_id") or trip.get("id") or "")
        messages = list((chats.get((user_id, trip_id)) or {}).get("messages") or [])
        user_turns = sum(1 for row in messages if row.get("role") == "user")
        timestamped = [
            row
            for row in messages
            if isinstance(row.get("ts"), (int, float))
            and since.timestamp() <= float(row["ts"]) / 1000 < until.timestamp()
        ]
        period_messages = timestamped
        if not any(isinstance(row.get("ts"), (int, float)) for row in messages) and _in_range(
            trip.get("updated_at"), since, until
        ):
            period_messages = messages
        period_user_turns = sum(1 for row in period_messages if row.get("role") == "user")
        assistant_rows = [row for row in messages if row.get("role") == "assistant"]
        first_seconds = next(
            (int(row["seconds"]) for row in assistant_rows if row.get("seconds") is not None),
            None,
        )
        iterations = max(0, user_turns - 1)
        total_turns += period_user_turns
        initial_turns = 1 if _in_range(trip.get("created_at"), since, until) else 0
        total_updates += max(0, period_user_turns - initial_turns)
        trip_feedback = sorted(
            feedback.get((user_id, trip_id), []),
            key=lambda row: str(row.get("created_at") or ""),
        )
        feedback_text = "; ".join(
            " · ".join(
                value
                for value in (
                    str(item.get("sentiment") or ""),
                    f"{item.get('rating')}/5" if item.get("rating") else "",
                    str(item.get("comment") or ""),
                )
                if value
            )
            for item in trip_feedback
        )
        rows.append(
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "title": str(trip.get("destination") or trip_id),
                "places_requested": str(trip.get("destination") or ""),
                "created_at": str(trip.get("created_at") or ""),
                "updated_at": str(trip.get("updated_at") or ""),
                "first_build_seconds": first_seconds,
                "iterations": iterations,
                "chat_turns": user_turns,
                "feedback": feedback_text,
            }
        )
    rows.sort(key=lambda row: str(row["updated_at"] or row["created_at"]), reverse=True)
    return rows, {"chat_turns": total_turns, "existing_trip_updates": total_updates}


def _config_snapshot() -> list[dict[str, Any]]:
    settings = get_settings()
    hosted = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").lower() in {
        "canary",
        "prod",
        "production",
    }
    auth = (
        "Managed identity"
        if settings.cosmos_use_managed_identity
        else "Connection string"
        if settings.cosmos_connection_string
        else "Account key"
        if settings.cosmos_key
        else "Not configured"
    )
    values = [
        ("Runtime", "Compute", "Azure Container Apps" if hosted else "Local process"),
        (
            "Data",
            "Primary persistence",
            "Azure Cosmos DB" if storage_cosmos.is_enabled() else "Local JSON",
        ),
        ("Data", "Cosmos authentication", auth),
        ("AI", "Azure OpenAI", "Enabled" if settings.enable_azure_openai else "Disabled"),
        ("AI", "Model deployment", settings.azure_openai_deployment),
        ("AI", "Data-plane API", settings.azure_openai_api_version),
        ("Maps", "Google Places", "Enabled" if settings.enable_google_places else "Disabled"),
        ("Maps", "Google Maps", "Enabled" if settings.enable_google_maps else "Disabled"),
        (
            "Analytics",
            "Google Analytics",
            "Enabled" if settings.google_analytics_measurement_id else "Disabled",
        ),
        ("Cache", "Redis", "Enabled" if settings.cache_redis_enabled else "Memory only"),
        ("Providers", "Flights", settings.travel_flight_provider),
        ("Providers", "Hotels", settings.travel_hotel_provider),
        ("Providers", "Activities", settings.travel_activity_provider),
    ]
    return [
        {"category": category, "name": name, "value": str(value)}
        for category, name, value in values
    ]


def snapshot(
    *,
    days: int,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    since, until, period_days = _range(days, start_date, end_date)
    events = _read_product_events(since, until)
    trips, trip_totals = _trip_rows(since, until)
    page_counts = Counter(
        str(row.get("page") or "other") for row in events if row.get("event") == "page_view"
    )
    new_trips = sum(1 for row in trips if _in_range(row.get("created_at"), since, until))
    return {
        "period": {
            "days": period_days,
            "start_date": since.date().isoformat(),
            "end_date": (until.date() - timedelta(days=1)).isoformat(),
        },
        "business": {
            "visitors": len({row.get("user_bucket") for row in events}),
            "page_counts": dict(page_counts.most_common()),
            "new_trips": new_trips,
            **trip_totals,
        },
        "trips": trips,
        "infra": {
            "cosmos": storage_cosmos.operations_inventory(),
            "configuration": _config_snapshot(),
        },
    }
