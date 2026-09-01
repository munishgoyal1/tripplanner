"""Resolve the authoritative user identity for API requests."""

from __future__ import annotations

import os
import re

from fastapi import HTTPException, Request

from tripplanner.web import oauth

_ANONYMOUS_ID = re.compile(
    r"^(?:web|mobile)-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HOSTED_ENVIRONMENTS = {"canary", "prod", "production"}


def is_hosted() -> bool:
    return os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower() in _HOSTED_ENVIRONMENTS


def is_anonymous_id(user_id: str) -> bool:
    return bool(_ANONYMOUS_ID.fullmatch((user_id or "").strip()))


def bearer_session(request: Request) -> dict[str, str] | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return oauth.read_session(token.strip())
    return None


def signed_session(request: Request) -> dict[str, str] | None:
    cookie_session = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if cookie_session and cookie_session.get("session_kind") != "guest":
        return cookie_session
    bearer = bearer_session(request)
    if bearer:
        return bearer
    return cookie_session


#: Lets a local developer read another identity's trips without disturbing their
#: own sign-in. Ignored outright when hosted, where the session is the only
#: acceptable authority.
INSPECT_HEADER = "x-inspect-user"


def inspect_override(request: Request) -> str | None:
    """The identity a local inspector asked to read, if any."""
    if is_hosted():
        return None
    return (request.headers.get(INSPECT_HEADER) or "").strip() or None


#: Choosing which trip to look at, and taking a copy to edit, are the only
#: writes inspection may perform. Everything else would make the corpus drift
#: because somebody opened it.
_INSPECT_WRITABLE_PATHS = frozenset({"/trips/switch", "/trip/fork", "/debug/audit/open"})


def guard_inspection_write(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not inspect_override(request):
        return
    if request.url.path.rstrip("/") in _INSPECT_WRITABLE_PATHS:
        return
    raise HTTPException(
        status_code=409,
        detail="This trip is being inspected and is read-only. Take a copy to edit it.",
    )


def resolve_user_id(request: Request, claimed_user_id: str = "local") -> str:
    """Return the signed principal, or a constrained anonymous/local identity.

    A valid session is authoritative even when a stale client still sends its
    previous guest id. Hosted callers cannot claim authenticated identities by
    supplying a user_id parameter; anonymous ids remain unguessable capabilities
    for the login-less product path.
    """
    # Deliberately ahead of the session: the whole point is to look at a trip
    # that belongs to someone else while staying signed in as yourself.
    override = inspect_override(request)
    if override:
        return override

    session = signed_session(request)
    if session:
        return str(session["user_id"])

    claimed = (claimed_user_id or "local").strip() or "local"
    if not is_hosted():
        return claimed
    if is_anonymous_id(claimed) and not oauth.signing_enabled():
        return claimed
    raise HTTPException(status_code=401, detail="Authentication required.")


def require_signed_user(request: Request) -> str:
    session = signed_session(request)
    if not session or session.get("session_kind") == "guest":
        raise HTTPException(status_code=401, detail="Sign in is required.")
    return str(session["user_id"])


def require_owner(request: Request) -> dict[str, str]:
    session = signed_session(request)
    owner_email = os.getenv("OPS_DASHBOARD_OWNER_EMAIL", "munishgoyal@aitripplanner.co")
    if (
        session
        and session.get("session_kind") != "guest"
        and str(session.get("email") or "").strip().casefold()
        == owner_email.strip().casefold()
    ):
        return session
    # A local run has no Google-signed email to match and nobody to hide the
    # console from, so requiring one only locks the owner out of their own machine.
    if not is_hosted():
        return session or {"user_id": "local", "email": owner_email}
    raise HTTPException(status_code=404, detail="Not found.")


def require_guest_capability(request: Request, guest_id: str) -> None:
    session = bearer_session(request)
    if (
        not session
        or session.get("session_kind") != "guest"
        or session.get("user_id") != guest_id
    ):
        raise HTTPException(status_code=403, detail="Guest ownership could not be verified.")
