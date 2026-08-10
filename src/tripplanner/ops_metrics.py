"""Process-local, content-free metrics for the owner operations dashboard."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from datetime import UTC, datetime
from typing import Any

_STARTED_AT = time.time()
_LOCK = threading.Lock()
_REQUESTS: deque[dict[str, Any]] = deque(maxlen=1000)
_MODELS: deque[dict[str, Any]] = deque(maxlen=250)


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


def snapshot() -> dict[str, Any]:
    with _LOCK:
        requests = list(_REQUESTS)
        models = list(_MODELS)

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
    }


def reset() -> None:
    with _LOCK:
        _REQUESTS.clear()
        _MODELS.clear()
