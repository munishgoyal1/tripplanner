"""Read-only share-link tokens for trip plans (#6.3).

Mints opaque, unguessable tokens that bind ``(owner_user_id, trip_created_at)``
under an HMAC. Anyone with the token can view a sanitized snapshot of the
plan — no chat history, no preferences, no PII beyond what's already in the
trip itself.

Tokens are stateless: no Cosmos write is needed at mint time. Re-minting for
the same trip yields the same token (idempotent, share-friendly).

Owner can revoke by changing the server secret (``WEB_SESSION_SECRET``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from tripplanner.user_context import get_user_id, set_user_id

_VERSION = "v1"


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


def mint_token(owner_user_id: str, trip_created_at: str) -> str:
    """Build an opaque share token for ``(owner, trip)``.

    Format: ``v1.<b64u(payload_json)>.<b64u(hmac-sha256)>``.
    """
    payload = {"u": owner_user_id, "c": trip_created_at}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()
    return f"{_VERSION}.{_b64u(body)}.{_b64u(sig)}"


def verify_token(token: str) -> dict[str, str] | None:
    """Parse + verify a share token. Returns the payload or ``None``."""
    if not token or token.count(".") != 2:
        return None
    version, body_b64, sig_b64 = token.split(".", 2)
    if version != _VERSION:
        return None
    try:
        body = _b64u_decode(body_b64)
        sig = _b64u_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        return None
    expected = hmac.new(_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "u" not in payload or "c" not in payload:
        return None
    return {"u": str(payload["u"]), "c": str(payload["c"])}


def mint_for_active_trip() -> str | None:
    """Mint a token for the active trip of the current user. ``None`` if no plan."""
    from tripplanner.tools import trip_planner

    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return None
    created = str(plan.get("created_at") or "")
    if not created:
        return None
    return mint_token(get_user_id(), created)


def _find_plan(owner_user_id: str, trip_created_at: str) -> dict[str, Any] | None:
    """Locate the plan for ``(owner, created_at)`` — active first, then archive."""
    from tripplanner import storage_cosmos
    from tripplanner.tools import trip_planner

    prev = get_user_id()
    try:
        set_user_id(owner_user_id)
        active = trip_planner.load_active_trip_dict()
        if active and str(active.get("created_at") or "") == trip_created_at:
            return active
        if storage_cosmos.is_enabled():
            for doc in storage_cosmos.query_docs("trips", owner_user_id):
                if str(doc.get("created_at") or "") == trip_created_at:
                    return doc
        else:
            from pathlib import Path

            trips_dir = Path.home() / ".tripplanner" / "users" / owner_user_id / "trips"
            if trips_dir.exists():
                for path in trips_dir.glob("*.json"):
                    try:
                        doc = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if str(doc.get("created_at") or "") == trip_created_at:
                        return doc
    finally:
        set_user_id(prev)
    return None


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
        "currency",
        "notes",
        "summary",
    }
    return {k: plan[k] for k in public_keys if k in plan}


def resolve(token: str) -> dict[str, Any] | None:
    """Verify ``token`` and return the sanitized plan, or ``None`` if invalid."""
    payload = verify_token(token)
    if not payload:
        return None
    plan = _find_plan(payload["u"], payload["c"])
    if not plan:
        return None
    return sanitize_plan(plan)

