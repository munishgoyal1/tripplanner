"""Owner ops, analytics ingest, and per-user usage HTTP routes."""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from tripplanner.request_identity import require_owner, signed_session
from tripplanner.user_context import set_user_id
from tripplanner.web.http_context import set_request_user as _set_request_user

router = APIRouter()

@router.post("/analytics/event", include_in_schema=False, status_code=204)
async def analytics_event(request: Request) -> Response:
    """Accept one consented, allowlisted, content-free product event."""
    from tripplanner.ops_metrics import record_product_event

    try:
        body = await request.json()
        event = str(body.get("event") or "")
        session_id = str(body.get("session_id") or "")
        source = str(body.get("source") or "unknown")
        page = str(body.get("page") or "other")
        if not re.fullmatch(r"[A-Za-z0-9-]{8,80}", session_id):
            return Response(status_code=204)
        session = signed_session(request)
        record_product_event(
            event,
            session_id,
            user_id=str(session["user_id"]) if session else None,
            source=source,
            page=page,
        )
    except (AttributeError, TypeError, ValueError):
        pass
    return Response(status_code=204)


@router.get("/ops/overview", include_in_schema=False)
async def ops_overview(
    request: Request,
    days: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Return content-free business and engineering metrics to the owner only."""
    session = require_owner(request)
    set_user_id(str(session["user_id"]))

    from datetime import UTC, datetime, timedelta

    from tripplanner.observability import tool_metrics_snapshot
    from tripplanner.ops_metrics import snapshot
    from tripplanner.provider_usage import summary as provider_usage_summary
    from tripplanner.providers.cache import provider_cache_status
    from tripplanner.providers.fares import get_provider_stats
    from tripplanner.tools.trip_planner import list_saved_trips
    from tripplanner.usage import get_usage as get_owner_usage

    now = datetime.now(UTC)
    trips = list_saved_trips()

    def count_since(field: str, days: int) -> int:
        threshold = now - timedelta(days=days)
        count = 0
        for trip in trips:
            try:
                value = datetime.fromisoformat(str(trip.get(field) or "").replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=UTC)
                count += value >= threshold
            except ValueError:
                continue
        return count

    runtime = snapshot()
    runtime["business"] = {
        "new_trips": {
            "today": count_since("created_at", 1),
            "7d": count_since("created_at", 7),
            "30d": count_since("created_at", 30),
        },
        "active_trips": {
            "today": count_since("updated_at", 1),
            "7d": count_since("updated_at", 7),
            "30d": count_since("updated_at", 30),
        },
        "chat_requests": (
            runtime["requests"]["by_route"].get("POST /chat/stream", {}).get("calls", 0)
        ),
        "iterations": sum(1 for trip in trips if trip.get("updated_at")),
        "inventory": {
            "trips": len(trips),
            "flights": sum(int((trip.get("counts") or {}).get("flights", 0)) for trip in trips),
            "hotels": sum(int((trip.get("counts") or {}).get("hotels", 0)) for trip in trips),
            "activities": sum(
                int((trip.get("counts") or {}).get("activities", 0)) for trip in trips
            ),
        },
    }
    usage = get_owner_usage(str(session["user_id"]))
    runtime["usage"] = {
        "month": usage.get("month"),
        "model_calls": usage.get("calls", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "cost_usd": usage.get("cost_usd", 0.0),
    }
    from tripplanner import cost_ledger

    trip_destinations = {
        str(trip["trip_id"]): str(trip.get("destination") or "")
        for trip in trips
        if trip.get("trip_id")
    }
    runtime["cost_ceiling"] = await asyncio.to_thread(cost_ledger.snapshot)
    runtime["trip_costs"] = {
        "aggregate": await asyncio.to_thread(cost_ledger.aggregate),
        "recent": await asyncio.to_thread(cost_ledger.recent_trips, 20, trip_destinations),
    }
    runtime["tools"] = tool_metrics_snapshot()
    provider_stats = get_provider_stats()
    provider_names = set(provider_stats["quote_success"]) | set(provider_stats["quote_failure"])
    runtime["providers"] = {
        provider: {
            "calls": int(provider_stats["quote_success"].get(provider, 0))
            + int(provider_stats["quote_failure"].get(provider, 0)),
            "successes": int(provider_stats["quote_success"].get(provider, 0)),
            "failures": int(provider_stats["quote_failure"].get(provider, 0)),
            "failure_rate": round(
                int(provider_stats["quote_failure"].get(provider, 0))
                / max(
                    1,
                    int(provider_stats["quote_success"].get(provider, 0))
                    + int(provider_stats["quote_failure"].get(provider, 0)),
                ),
                3,
            ),
            "avg_ms": round(float(provider_stats["avg_latency_ms"].get(provider, 0)), 2),
        }
        for provider in sorted(provider_names)
    }
    runtime["cache"] = provider_cache_status()
    try:
        runtime["provider_usage"] = provider_usage_summary(
            days=days,
            start_date=start_date,
            end_date=end_date,
            trip_names={
                str(trip["trip_id"]): str(trip.get("destination") or "")
                for trip in trips
                if trip.get("trip_id")
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from tripplanner.operations_reporting import snapshot as operations_snapshot

    try:
        durable = await asyncio.to_thread(
            operations_snapshot,
            days=days,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    runtime["reporting_period"] = durable["period"]
    runtime["business_activity"] = durable["business"]
    runtime["trip_insights"] = durable["trips"]
    runtime["infra"] = durable["infra"]

    from tripplanner.alert_events import recent as alert_events_recent
    from tripplanner.alert_events import snapshot as alert_events_snapshot

    try:
        runtime["alerts"] = {
            "counts": await asyncio.to_thread(alert_events_snapshot, days),
            "recent": await asyncio.to_thread(alert_events_recent, 50, days),
        }
    except Exception:  # noqa: BLE001 - one dataset must not hide the dashboard
        runtime["alerts"] = {
            "counts": {"period_days": days, "by_signal": {}, "total_fired": 0},
            "recent": [],
        }
    return runtime


@router.get("/usage")
async def usage_for_user(request: Request, user_id: str = "local") -> dict:
    """This month's LLM token + cost usage for ``user_id``, plus the INR ceiling.

    Per-user figures stay USD because they come from the Azure token catalog;
    the ceiling is environment-wide and INR. Both units are named in the field
    names so a caller cannot compare one to the other by accident.
    """
    from tripplanner import cost_ledger
    from tripplanner.usage import get_usage

    resolved_user_id = _set_request_user(request, user_id)
    doc = get_usage(resolved_user_id)
    return {
        "user_id": resolved_user_id,
        "month": doc.get("month"),
        "prompt_tokens": doc.get("prompt_tokens", 0),
        "completion_tokens": doc.get("completion_tokens", 0),
        "calls": doc.get("calls", 0),
        "cost_usd": round(float(doc.get("cost_usd", 0.0)), 4),
        "cost_ceiling": cost_ledger.snapshot(),
    }


