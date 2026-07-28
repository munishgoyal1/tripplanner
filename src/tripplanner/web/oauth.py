"""Google OAuth 2.0 (Authorization Code flow) for the React SPA backend.

Why this exists
---------------
The Chainlit app (``web/app.py``) gets "Sign in with Google" for free from
Chainlit's built-in OAuth. The standalone SPA talks to plain FastAPI
(``api.py``), which has no such machinery — so we implement the standard
authorization-code flow here with nothing but the stdlib and ``httpx``
(already a dependency). No Authlib, no SessionMiddleware.

Identity reuse (the important part)
-----------------------------------
We deliberately reuse the **same environment variables** and the **same user
identifier scheme** as the Chainlit app:

* ``OAUTH_GOOGLE_CLIENT_ID`` / ``OAUTH_GOOGLE_CLIENT_SECRET`` — the Google
  app credentials (identical to what Chainlit reads).
* identifier ``google-<sub>`` — the same string ``web/app.py`` produces.

So a user who signed in with Google on the Chainlit app and one who signs in
on the SPA resolve to the *same* ``user_id``, and their preferences and trips
carry across both frontends with zero migration.

Sessions
--------
After a successful login we drop a signed, HttpOnly cookie (``mg_session``)
containing the identifier + display name. It's signed with HMAC-SHA256 using
``CHAINLIT_AUTH_SECRET`` (falling back to ``WEB_SESSION_SECRET``) — the same
secret family the Chainlit app already requires for auth. No server-side
session store needed for the personal-use footprint.

Dev vs prod redirect URI
------------------------
Google must redirect back to a URI you've whitelisted in the Cloud console.
Set ``OAUTH_REDIRECT_BASE`` to the public base that fronts ``/auth/...``:

* Dev (through the Vite proxy, keeps everything same-origin on :5173)::

      OAUTH_REDIRECT_BASE=http://localhost:5173/api
      # register http://localhost:5173/api/auth/callback/google in Google console

* Prod (single origin serving both SPA and API)::

      OAUTH_REDIRECT_BASE=https://your-app.example.com/api

If unset, the redirect URI is derived from the incoming request, which works
when the SPA and API share an origin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

SESSION_COOKIE = "mg_session"
_STATE_COOKIE = "mg_oauth_state"
_SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
_STATE_MAX_AGE = 600  # 10 minutes to complete the round-trip


# ---------------------------------------------------------------------------
# configuration helpers
# ---------------------------------------------------------------------------
def _client_id() -> str:
    return os.environ.get("OAUTH_GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.environ.get("OAUTH_GOOGLE_CLIENT_SECRET", "")


def is_enabled() -> bool:
    """True when Google OAuth is fully configured (creds + signing secret)."""
    return bool(_client_id() and _client_secret() and _secret())


def signing_enabled() -> bool:
    return bool(_secret())


def _secret() -> bytes:
    raw = os.environ.get("CHAINLIT_AUTH_SECRET") or os.environ.get("WEB_SESSION_SECRET")
    return raw.encode("utf-8") if raw else b""


def redirect_uri(request_base_url: str) -> str:
    """The Google callback URI. Prefers ``OAUTH_REDIRECT_BASE`` so it matches
    whatever is whitelisted in the Google console; else derives from the
    request (works when SPA + API share an origin)."""
    base = os.environ.get("OAUTH_REDIRECT_BASE", "").rstrip("/")
    if not base:
        base = request_base_url.rstrip("/")
    return f"{base}/auth/callback/google"


# ---------------------------------------------------------------------------
# signed-token helpers (stdlib only)
# ---------------------------------------------------------------------------
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload: dict[str, Any]) -> str:
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def _unsign(token: str) -> dict[str, Any] | None:
    secret = _secret()
    if not secret or not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# ---------------------------------------------------------------------------
# session cookie
# ---------------------------------------------------------------------------
def make_session_token(identifier: str, name: str, email: str, picture: str) -> str:
    return _sign(
        {
            "sub": identifier,
            "kind": "user",
            "name": name,
            "email": email,
            "picture": picture,
            "exp": int(time.time()) + _SESSION_MAX_AGE,
        }
    )


def make_guest_token(identifier: str) -> str:
    if not identifier.startswith(("web-", "mobile-")):
        raise ValueError("Guest identifiers must use a guest prefix.")
    return _sign(
        {
            "sub": identifier,
            "kind": "guest",
            "exp": int(time.time()) + _SESSION_MAX_AGE,
        }
    )


def read_session(token: str | None) -> dict[str, Any] | None:
    """Return ``{user_id, display_name, email, picture}`` or ``None``."""
    payload = _unsign(token or "")
    if not payload or not payload.get("sub"):
        return None
    return {
        "user_id": payload["sub"],
        "display_name": payload.get("name") or "",
        "email": payload.get("email") or "",
        "picture": payload.get("picture") or "",
        "session_kind": payload.get("kind") or "user",
    }


# ---------------------------------------------------------------------------
# flow steps
# ---------------------------------------------------------------------------
def build_authorize_url(callback_uri: str, post_login: str) -> tuple[str, str]:
    """Return ``(authorize_url, state_token)``.

    ``state_token`` is a signed cookie value carrying the CSRF nonce and the
    SPA path to return to; verify it in :func:`exchange_code`.
    """
    nonce = secrets.token_urlsafe(24)
    state_token = _sign(
        {"n": nonce, "r": post_login, "exp": int(time.time()) + _STATE_MAX_AGE}
    )
    params = {
        "client_id": _client_id(),
        "redirect_uri": callback_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": nonce,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}", state_token


def verify_state(state_cookie: str | None, returned_state: str) -> str | None:
    """Validate the state nonce; return the post-login redirect path or None."""
    payload = _unsign(state_cookie or "")
    if not payload:
        return None
    if not returned_state or not hmac.compare_digest(payload.get("n", ""), returned_state):
        return None
    return payload.get("r") or "/"


async def exchange_code(code: str, callback_uri: str) -> dict[str, Any]:
    """Swap an auth code for the user's Google profile.

    Returns ``{identifier, name, email, picture}``. Raises on failure.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            _TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": callback_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise RuntimeError("Google did not return an access token")

        info_res = await client.get(
            _USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_res.raise_for_status()
        info = info_res.json()

    sub = info.get("sub")
    if not sub:
        raise RuntimeError("Google userinfo missing 'sub'")
    return {
        "identifier": f"google-{sub}",  # same scheme as the Chainlit app
        "name": info.get("name") or info.get("given_name") or "",
        "email": info.get("email") or "",
        "picture": info.get("picture") or "",
    }
