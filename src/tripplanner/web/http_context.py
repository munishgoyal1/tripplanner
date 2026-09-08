"""Shared request-identity helpers for HTTP routers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request

from tripplanner.request_identity import (
    guard_inspection_write,
    is_hosted,
    require_signed_user,
    resolve_user_id,
)
from tripplanner.user_context import set_user_id
from tripplanner.web import oauth


def set_request_user(request: Request, claimed_user_id: str = "local") -> str:
    user_id = resolve_user_id(request, claimed_user_id)
    guard_inspection_write(request)
    set_user_id(user_id)
    return user_id


def run_agent_background(function: Any, *, route: str, trip_id: str = "") -> None:
    from tripplanner.usage_attribution import usage_scope

    with usage_scope("agent_background", route=route, trip_id=trip_id):
        function()


def document_user(request: Request, claimed_user_id: str) -> str:
    if is_hosted():
        user_id = require_signed_user(request)
        set_user_id(user_id)
        return user_id
    return set_request_user(request, claimed_user_id)


def secure_cookie(request: Request) -> bool:
    return oauth.redirect_uri(str(request.base_url)).startswith("https://")


def mobile_auth_redirect(target: str, token: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.scheme not in {"tripplanner", "exp"}:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["session"] = token
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )
