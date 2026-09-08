"""Process-local, content-free metrics for the owner operations dashboard."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

_STARTED_AT = time.time()
_LOCK = threading.Lock()
_REQUESTS: deque[dict[str, Any]] = deque(maxlen=1000)
_MODELS: deque[dict[str, Any]] = deque(maxlen=250)
_CHAT_TURNS: deque[dict[str, Any]] = deque(maxlen=500)
_OPERATIONS: deque[dict[str, Any]] = deque(maxlen=2000)
_PRODUCT_EVENTS: deque[dict[str, Any]] = deque(maxlen=2000)

PRODUCT_EVENTS = {
    "page_view",
    "planning_started",
    "planning_completed",
    "planning_failed",
    "trip_created",
    "new_trip_started",
    "trip_reset",
    "login",
    "place_added",
    "place_removed",
    "trip_shared",
    "itinerary_exported",
    "calendar_exported",
    "shared_trip_imported",
}
_FUNNEL = ("page_view", "planning_started", "trip_created", "planning_completed")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((percentile / 100) * (len(ordered) - 1))
    return round(ordered[index], 1)


def record_request(method: str, route: str, status: int, duration_ms: float) -> None:
    with _LOCK:
        _REQUESTS.append(
            {
                "method": method,
                "route": route,
                "status": status,
                "duration_ms": duration_ms,
                "at": time.time(),
            }
        )


def record_model_call(model: str, status: str, duration_ms: float) -> None:
    with _LOCK:
        _MODELS.append(
            {
                "model": model,
                "status": status,
                "duration_ms": duration_ms,
                "at": time.time(),
            }
        )


def record_chat_turn(
    user_id: str,
    outcome: str,
    duration_ms: float,
    *,
    tool_calls: int = 0,
) -> None:
    user_bucket = sha256(user_id.encode("utf-8")).hexdigest()[:16]
    with _LOCK:
        _CHAT_TURNS.append(
            {
                "user_bucket": user_bucket,
                "outcome": outcome,
                "duration_ms": duration_ms,
                "tool_calls": max(0, tool_calls),
                "at": time.time(),
            }
        )


def record_operation(
    kind: str,
    operation: str,
    status: str,
    duration_ms: float,
) -> None:
    with _LOCK:
        _OPERATIONS.append(
            {
                "kind": kind,
                "operation": operation,
                "status": status,
                "duration_ms": duration_ms,
                "at": time.time(),
            }
        )


def record_product_event(
    event: str,
    session_id: str,
    *,
    user_id: str | None = None,
    country: str = "unknown",
    source: str = "unknown",
    page: str = "other",
) -> None:
    if event not in PRODUCT_EVENTS:
        raise ValueError("Unsupported product event")
    safe_session = sha256(session_id.encode("utf-8")).hexdigest()[:16]
    safe_user = sha256(user_id.encode("utf-8")).hexdigest()[:16] if user_id else safe_session
    safe_country = country.upper() if len(country) == 2 and country.isalpha() else "unknown"
    safe_source = source if source in {"direct", "search", "social", "referral"} else "unknown"
    safe_page = page if page in {"welcome", "planner", "operations"} else "other"
    with _LOCK:
        _PRODUCT_EVENTS.append(
            {
                "event": event,
                "session_bucket": safe_session,
                "user_bucket": safe_user,
                "country": safe_country,
                "source": safe_source,
                "page": safe_page,
                "at": time.time(),
            }
        )
    from tripplanner.operations_reporting import persist_product_event

    persist_product_event(
        event,
        session_id,
        user_id=user_id,
        country=safe_country,
        source=safe_source,
        page=safe_page,
    )


def snapshot() -> dict[str, Any]:
    with _LOCK:
        requests = list(_REQUESTS)
        models = list(_MODELS)
        chat_turns = list(_CHAT_TURNS)
        operations = list(_OPERATIONS)
        product_events = list(_PRODUCT_EVENTS)

    by_route: dict[str, dict[str, Any]] = {}
    for route in sorted({f"{item['method']} {item['route']}" for item in requests}):
        matching = [item for item in requests if f"{item['method']} {item['route']}" == route]
        latencies = [float(item["duration_ms"]) for item in matching]
        errors = sum(1 for item in matching if int(item["status"]) >= 400)
        by_route[route] = {
            "calls": len(matching),
            "errors": errors,
            "p50_ms": _percentile(latencies, 50),
            "p90_ms": _percentile(latencies, 90),
            "p95_ms": _percentile(latencies, 95),
        }

    model_latencies = [float(item["duration_ms"]) for item in models]
    status_counts = Counter(str(item["status"]) for item in models)
    request_latencies = [float(item["duration_ms"]) for item in requests]
    error_types = Counter(str(item["status"]) for item in requests if int(item["status"]) >= 400)
    chat_latencies = [float(item["duration_ms"]) for item in chat_turns]
    chat_outcomes = Counter(str(item["outcome"]) for item in chat_turns)
    total_tool_calls = sum(int(item["tool_calls"]) for item in chat_turns)
    activity_counts = Counter(str(item["event"]) for item in product_events)
    session_events: dict[str, list[dict[str, Any]]] = {}
    for item in product_events:
        session_events.setdefault(str(item["session_bucket"]), []).append(item)
    engagement_seconds = 0.0
    for events in session_events.values():
        ordered = sorted(events, key=lambda item: float(item["at"]))
        for previous, current in zip(ordered, ordered[1:]):
            engagement_seconds += min(300.0, float(current["at"]) - float(previous["at"]))
    funnel = {
        stage: len(
            {
                item["session_bucket"]
                for item in product_events
                if item["event"] == stage
            }
        )
        for stage in _FUNNEL
    }
    drop_offs: Counter[str] = Counter()
    for events in session_events.values():
        reached = {str(item["event"]) for item in events}
        if "planning_failed" in reached and "planning_completed" not in reached:
            drop_offs["planning_failed"] += 1
        elif "planning_started" in reached and "planning_completed" not in reached:
            drop_offs["planning_abandoned"] += 1
        elif reached == {"page_view"}:
            drop_offs["page_only"] += 1
    session_dimensions = [
        min(events, key=lambda item: float(item["at"])) for events in session_events.values()
    ]
    by_operation: dict[str, dict[str, Any]] = {}
    operation_keys = sorted({f"{item['kind']}.{item['operation']}" for item in operations})
    for key in operation_keys:
        matching = [
            item for item in operations if f"{item['kind']}.{item['operation']}" == key
        ]
        latencies = [float(item["duration_ms"]) for item in matching]
        by_operation[key] = {
            "calls": len(matching),
            "errors": sum(1 for item in matching if item["status"] == "error"),
            "p50_ms": _percentile(latencies, 50),
            "p95_ms": _percentile(latencies, 95),
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "uptime_seconds": max(0, round(time.time() - _STARTED_AT)),
        "requests": {
            "calls": len(requests),
            "errors": sum(error_types.values()),
            "p50_ms": _percentile(request_latencies, 50),
            "p90_ms": _percentile(request_latencies, 90),
            "p95_ms": _percentile(request_latencies, 95),
            "by_route": by_route,
            "error_statuses": dict(error_types.most_common(5)),
        },
        "models": {
            "calls": len(models),
            "errors": status_counts.get("error", 0),
            "p50_ms": _percentile(model_latencies, 50),
            "p95_ms": _percentile(model_latencies, 95),
            "recent": list(reversed(models[-20:])),
        },
        "chat_turns": {
            "calls": len(chat_turns),
            "completed": chat_outcomes.get("completed", 0),
            "errors": chat_outcomes.get("error", 0),
            "distinct_users": len({item["user_bucket"] for item in chat_turns}),
            "p50_ms": _percentile(chat_latencies, 50),
            "p95_ms": _percentile(chat_latencies, 95),
            "tool_calls": total_tool_calls,
            "avg_tools_per_turn": (
                round(total_tool_calls / len(chat_turns), 1) if chat_turns else 0.0
            ),
            "outcomes": dict(chat_outcomes.most_common()),
        },
        "operations": {
            "calls": len(operations),
            "errors": sum(1 for item in operations if item["status"] == "error"),
            "by_operation": by_operation,
        },
        "product": {
            "events": len(product_events),
            "sessions": len(session_events),
            "users": len({item["user_bucket"] for item in product_events}),
            "engagement_seconds": round(engagement_seconds),
            "activities": dict(activity_counts.most_common()),
            "funnel": funnel,
            "drop_offs": dict(drop_offs.most_common()),
            "countries": dict(
                Counter(item["country"] for item in session_dimensions).most_common(8)
            ),
            "sources": dict(
                Counter(item["source"] for item in session_dimensions).most_common()
            ),
        },
    }


def reset() -> None:
    with _LOCK:
        _REQUESTS.clear()
        _MODELS.clear()
        _CHAT_TURNS.clear()
        _OPERATIONS.clear()
        _PRODUCT_EVENTS.clear()
