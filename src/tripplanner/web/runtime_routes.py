"""Independent public runtime and diagnostic HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/public/demo-run")
async def public_demo_run(request: Request, region: str = "EU", currency: str = "EUR") -> Response:
    """Return one validated regional artifact without requiring authentication."""
    from tripplanner.public_demo import active_artifact, artifact_etag

    artifact = active_artifact(region, currency)
    etag = artifact_etag(artifact)
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600, stale-if-error=2592000"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(artifact, headers=headers)


@router.get("/providers/status")
async def providers_status() -> dict[str, object]:
    """Expose non-secret provider readiness for MVP diagnostics."""
    from tripplanner import http_client
    from tripplanner.providers.registry import provider_status

    return {"providers": provider_status(), "outbound": http_client.outbound_status()}


@router.get("/metrics/tools")
async def metrics_tools() -> dict:
    """Return per-tool latency + error + cache-hit counters.

    In-process only — accumulated for the lifetime of the current container.
    Intended for live introspection during a session; long-horizon data lives
    in Log Analytics via the structured ``tool_call`` events.
    """
    from tripplanner.observability import tool_metrics_snapshot

    return {"tools": tool_metrics_snapshot()}

