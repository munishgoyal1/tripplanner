"""Persistent public share snapshots for trip plans.

Each share link stores a sanitized snapshot of the trip at share time and maps
it to an opaque token. The snapshot stays stable even if the live trip keeps
changing later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from tripplanner import storage_cosmos
from tripplanner.user_context import get_user_id, set_user_id

_VERSION = "s1"
_SHARED_PARTITION = "_shared"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _secret() -> bytes:
    raw = (
        os.environ.get("WEB_SESSION_SECRET")
        or os.environ.get("CHAINLIT_AUTH_SECRET")
        or "dev-share-secret-do-not-use-in-prod"
    )
    return raw.encode("utf-8")


def _local_snapshot_dir() -> Path:
    from tripplanner.tools import trip_planner

    return trip_planner._TRIPS_DIR / "shared_snapshots"


def _snapshot_path(token: str) -> Path:
    return _local_snapshot_dir() / f"{token}.json"


def _snapshot_token(owner_user_id: str, public_plan: dict[str, Any]) -> str:
    body = json.dumps(public_plan, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), owner_user_id.encode("utf-8") + b"\0" + body, hashlib.sha256).digest()
    return f"{_VERSION}_{_b64u(sig)}"


def _load_snapshot(token: str) -> dict[str, Any] | None:
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc("shared_trips", _SHARED_PARTITION, token)
    path = _snapshot_path(token)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_snapshot(token: str, snapshot: dict[str, Any]) -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc("shared_trips", _SHARED_PARTITION, token, snapshot)
        return
    path = _snapshot_path(token)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def mint_for_active_trip() -> str | None:
    """Persist a sanitized snapshot for the active trip and return its token."""
    from tripplanner.tools import trip_planner
    from tripplanner.web.itinerary_export import build_export_html

    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return None
    public_plan = sanitize_plan(plan)
    token = _snapshot_token(get_user_id(), public_plan)
    snapshot = {
        "token": token,
        "owner_user_id": get_user_id(),
        "created_at": str(plan.get("updated_at") or plan.get("created_at") or ""),
        "plan": public_plan,
        "html": build_export_html(
            public_plan,
            include_photos=True,
            include_map_circuit=True,
            template="detailed",
            auto_print=False,
        ),
    }
    _save_snapshot(token, snapshot)
    return token


def sanitize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Strip owner-only fields before serving to a public viewer."""
    if not plan:
        return {}
    public_keys = {
        "destination",
        "origin",
        "departure_date",
        "return_date",
        "travelers",
        "trip_style",
        "interests",
        "status",
        "selected_flights",
        "selected_hotels",
        "selected_activities",
        "day_wise_itinerary",
        "estimated_total_cost",
        "total_cost",
        "cost_baseline",
        "currency",
        "notes",
        "summary",
        "created_at",
        "updated_at",
    }
    return {k: plan[k] for k in public_keys if k in plan}


def resolve(token: str) -> dict[str, Any] | None:
    """Return the stored snapshot for ``token``, or ``None`` if not found."""
    if not token.startswith(f"{_VERSION}_"):
        return None
    return _load_snapshot(token)


def render_public_html(token: str, current_origin: str = "") -> str | None:
    """Return a self-contained public HTML page for the shared snapshot."""
    snapshot = resolve(token)
    if not snapshot:
        return None
    html = str(snapshot.get("html") or "")
    if not html:
        return None
    continue_href = "/?share=" + token
    if os.environ.get("VITE_DEV_SERVER_URL"):
        continue_href = os.environ["VITE_DEV_SERVER_URL"].rstrip("/") + "/?share=" + token
    elif "localhost:8000" in current_origin or "127.0.0.1:8000" in current_origin:
        continue_href = "http://localhost:5173/?share=" + token
    elif current_origin:
        continue_href = current_origin.rstrip("/") + "/?share=" + token

    banner = (
        "<section style='margin-bottom:16px;padding:12px 14px;border:1px solid #e2e8f0;"
        "border-radius:12px;background:#fff7ed;color:#9a3412;font:14px/1.4 Inter,Segoe UI,sans-serif'>"
        "<strong>Shared snapshot.</strong> This view shows the trip details as they looked when the link was shared."
        f"<div style='margin-top:10px'><a href='{continue_href}' style='display:inline-block;padding:8px 12px;border-radius:999px;background:#e11d48;color:#fff;text-decoration:none;font-weight:600'>Continue exploring this trip</a></div>"
        "</section>"
    )
    return html.replace("<div class='wrap'>", "<div class='wrap'>" + banner, 1)

