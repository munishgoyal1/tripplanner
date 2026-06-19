"""Thin HTTP client for Amadeus Self-Service APIs.

Handles OAuth2 token management and provides get/post helpers.
Uses test environment by default; set AMADEUS_BASE_URL for production.

Sign up free: https://developers.amadeus.com  (2 000 calls/month free)
"""

from __future__ import annotations

import time

import httpx

from tripplanner.config import get_settings

_token_cache: dict = {"token": "", "expires_at": 0.0}


def _base_url() -> str:
    s = get_settings()
    return s.amadeus_base_url


def _get_token() -> str:
    """Get a valid OAuth2 token, refreshing if expired."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    s = get_settings()
    if not s.amadeus_api_key or not s.amadeus_api_secret:
        raise RuntimeError(
            "Amadeus API credentials not configured. "
            "Set AMADEUS_API_KEY and AMADEUS_API_SECRET in .env. "
            "Sign up free at https://developers.amadeus.com"
        )

    resp = httpx.post(
        f"{_base_url()}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": s.amadeus_api_key,
            "client_secret": s.amadeus_api_secret,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data["expires_in"]
    return _token_cache["token"]


def is_configured() -> bool:
    """Check whether Amadeus API credentials are set."""
    s = get_settings()
    return bool(s.amadeus_api_key and s.amadeus_api_secret)


def get(path: str, params: dict | None = None) -> dict:
    """GET request to Amadeus API."""
    token = _get_token()
    resp = httpx.get(
        f"{_base_url()}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def post(path: str, body: dict) -> dict:
    """POST request to Amadeus API."""
    token = _get_token()
    resp = httpx.post(
        f"{_base_url()}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

