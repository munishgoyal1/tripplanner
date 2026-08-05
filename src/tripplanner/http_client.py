"""Process-wide pooled HTTP client for outbound provider calls.

``httpx.get``/``httpx.post`` build a throwaway client per call, so every request
rebuilds the TLS context (loading the CA bundle from disk) and opens a fresh
connection. Panel rendering issues dozens of Places calls per destination, and
that per-call setup — not the provider — dominated the switch latency. Sharing
one pooled client keeps the TLS context and keep-alive connections warm.
"""

from __future__ import annotations

import atexit
from threading import Lock
from typing import Any

import httpx

_DEFAULT_TIMEOUT_S = 20
_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16)

_lock = Lock()
_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """Return the shared client, creating it on first use."""
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(timeout=_DEFAULT_TIMEOUT_S, limits=_LIMITS)
            atexit.register(close_client)
        return _client


def close_client() -> None:
    """Drop the shared client; the next call builds a fresh one."""
    global _client
    with _lock:
        client, _client = _client, None
    if client is not None:
        client.close()


def get(url: str, **kwargs: Any) -> httpx.Response:
    return get_client().get(url, **kwargs)


def post(url: str, **kwargs: Any) -> httpx.Response:
    return get_client().post(url, **kwargs)
