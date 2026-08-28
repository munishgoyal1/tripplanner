"""Process-wide outbound HTTP runtime for every remote dependency.

Three latency problems used to be solved once per call site, or not at all:

1. **Connection setup.** ``httpx.get``/``httpx.post`` build a throwaway client per
   call, so every request rebuilds the TLS context (loading the CA bundle from
   disk) and opens a fresh connection. Panel rendering issues dozens of Places
   calls per destination, and that per-call setup — not the provider — dominated
   the switch latency. One pooled client keeps TLS and keep-alive connections warm.
2. **Tail latency.** A generous per-call ``timeout=20`` means one sick dependency
   adds twenty seconds to the turn, repeatedly. The budget belongs to the
   endpoint, not to whichever call site was written last.
3. **Repeat failure.** Once a dependency is failing, every further attempt still
   pays the full timeout. A per-endpoint circuit breaker turns that into an
   immediate miss so the caller falls through to the next source in microseconds.

Everything outbound goes through :func:`get`/:func:`post`/:func:`request`. The
endpoint identity is derived from the URL host, so a newly added provider is
pooled, budgeted, breakered, and measured with no registration step. Tuning it
later is one row in ``_ENDPOINT_POLICIES``.

``CircuitOpenError`` deliberately subclasses ``httpx.HTTPError`` so the existing
``except httpx.HTTPError`` degradation path at every provider call site treats an
open circuit exactly like an unreachable provider.
"""

from __future__ import annotations

import atexit
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

import httpx

from tripplanner.circuit_breaker import (
    DEFAULT_BREAKER_POLICY,
    BreakerPolicy,
    CircuitBreakerRegistry,
)

_LIMITS = httpx.Limits(
    max_connections=64,
    max_keepalive_connections=32,
    keepalive_expiry=60.0,
)


class CircuitOpenError(httpx.HTTPError):
    """Raised instead of calling an endpoint that is currently failing."""


@dataclass(frozen=True)
class EndpointPolicy:
    """Latency budget and failure tolerance for one remote dependency."""

    timeout: httpx.Timeout
    breaker: BreakerPolicy = DEFAULT_BREAKER_POLICY


def _budget(read: float, *, connect: float = 3.0) -> httpx.Timeout:
    return httpx.Timeout(connect=connect, read=read, write=read, pool=connect)


# Default budget for any host not listed below. Deliberately tighter than the
# per-call-site literals it replaces: a remote call that has not answered in
# twelve seconds has failed the planning turn, not slowed it.
_DEFAULT_POLICY = EndpointPolicy(timeout=_budget(12.0))

# Keyed by host suffix; the longest match wins.
_ENDPOINT_POLICIES: dict[str, EndpointPolicy] = {
    # Google Places/Routes sit on the critical path of every panel render.
    "googleapis.com": EndpointPolicy(timeout=_budget(8.0)),
    # Open-Meteo and the FX reference feed must never hold up a turn.
    "open-meteo.com": EndpointPolicy(timeout=_budget(6.0)),
    "frankfurter.dev": EndpointPolicy(timeout=_budget(5.0)),
    # Search and live inventory legitimately take longer to answer.
    "tavily.com": EndpointPolicy(timeout=_budget(15.0)),
    "duffel.com": EndpointPolicy(timeout=_budget(15.0)),
    "liteapi.travel": EndpointPolicy(timeout=_budget(15.0)),
    "amadeus.com": EndpointPolicy(timeout=_budget(15.0)),
    "viator.com": EndpointPolicy(timeout=_budget(15.0)),
    "openrouteservice.org": EndpointPolicy(timeout=_budget(10.0)),
}

# 429 is throttling rather than breakage, but it is still a reason to back off.
_FAILURE_STATUSES = frozenset({429})

_lock = Lock()
_client: httpx.Client | None = None
_breakers = CircuitBreakerRegistry()


def endpoint_for(url: str) -> str:
    """Endpoint identity for ``url`` — the host, without a ``www.`` prefix."""
    host = (urlsplit(str(url)).hostname or "unknown").lower()
    return host[4:] if host.startswith("www.") else host


def _header_value(headers: Any, name: str) -> str:
    if not headers:
        return ""
    match = next(
        (value for key, value in dict(headers).items() if key.lower() == name.lower()),
        "",
    )
    return str(match)


def google_operation(url: str, kwargs: dict[str, Any]) -> tuple[str, str]:
    """Return the billable operation and field-mask class for a Google request."""
    path = urlsplit(str(url)).path
    field_mask = _header_value(kwargs.get("headers"), "X-Goog-FieldMask")
    if path.endswith("/media"):
        return "photo_media", "photo_media"
    if path.endswith("places:searchText"):
        operation = "text_search"
    elif "/places/" in path:
        operation = "place_details"
    elif path.endswith(":computeRoutes"):
        return "compute_routes", "routes_essentials"
    elif path.endswith(":computeRouteMatrix"):
        return "compute_route_matrix", "routes_matrix"
    else:
        return "other", "unknown"

    atmosphere = ("reviews", "editorialSummary")
    pro = ("rating", "userRatingCount", "priceLevel", "websiteUri")
    if any(field in field_mask for field in atmosphere):
        return operation, "enterprise_atmosphere"
    if any(field in field_mask for field in pro):
        return operation, "pro"
    return operation, "essentials"


def policy_for(endpoint: str) -> EndpointPolicy:
    """Longest-suffix policy match, falling back to the default budget."""
    match = ""
    for suffix in _ENDPOINT_POLICIES:
        if (endpoint == suffix or endpoint.endswith("." + suffix)) and len(suffix) > len(match):
            match = suffix
    return _ENDPOINT_POLICIES[match] if match else _DEFAULT_POLICY


def get_client() -> httpx.Client:
    """Return the shared client, creating it on first use."""
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(timeout=_DEFAULT_POLICY.timeout, limits=_LIMITS)
            atexit.register(close_client)
        return _client


def close_client() -> None:
    """Drop the shared client; the next call builds a fresh one."""
    global _client
    with _lock:
        client, _client = _client, None
    if client is not None:
        client.close()


def request(
    method: str, url: str, *, endpoint: str | None = None, **kwargs: Any
) -> httpx.Response:
    """Perform one pooled, budgeted, breakered outbound request."""
    name = endpoint or endpoint_for(url)
    if name in {"places.googleapis.com", "routes.googleapis.com", "maps.googleapis.com"}:
        from tripplanner.places_budget import paid_provider_authorized

        if not paid_provider_authorized():
            raise PermissionError(f"Paid provider access is not authorized for {name}")
    policy = policy_for(name)
    breaker = _breakers.get(name, policy.breaker)
    operation, sku_class = (
        google_operation(url, kwargs) if name.endswith("googleapis.com") else ("", "")
    )
    if not breaker.allow():
        _record(name, "circuit_open", 0.0, None, operation, sku_class)
        raise CircuitOpenError(f"{name} is temporarily unavailable (circuit open)")

    kwargs.setdefault("timeout", policy.timeout)
    started = time.monotonic()
    try:
        response = get_client().request(method, url, **kwargs)
    except Exception as exc:
        breaker.record_failure()
        _record(
            name,
            type(exc).__name__,
            (time.monotonic() - started) * 1000,
            None,
            operation,
            sku_class,
        )
        raise

    if response.status_code >= 500 or response.status_code in _FAILURE_STATUSES:
        breaker.record_failure()
    else:
        breaker.record_success()
    _record(
        name,
        "ok",
        (time.monotonic() - started) * 1000,
        response.status_code,
        operation,
        sku_class,
    )
    return response


def get(url: str, **kwargs: Any) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> httpx.Response:
    return request("POST", url, **kwargs)


def outbound_status() -> dict[str, Any]:
    """Non-secret outbound health, surfaced by ``/providers/status``."""
    return {"endpoints": _breakers.snapshot()}


def reset_breakers_for_tests() -> None:
    _breakers.reset()


def _record(
    endpoint: str,
    status: str,
    duration_ms: float,
    http_status: int | None,
    operation: str = "",
    sku_class: str = "",
) -> None:
    from tripplanner.observability import app_event
    from tripplanner.provider_usage import record_call

    provider = next(
        (
            label
            for suffix, label in (
                ("googleapis.com", "google"),
                ("tavily.com", "tavily"),
                ("duffel.com", "duffel"),
                ("liteapi.travel", "liteapi"),
                ("amadeus.com", "amadeus"),
                ("viator.com", "viator"),
                ("openrouteservice.org", "openrouteservice"),
                ("open-meteo.com", "open_meteo"),
                ("frankfurter.dev", "frankfurter"),
            )
            if endpoint == suffix or endpoint.endswith("." + suffix)
        ),
        endpoint,
    )
    call_status = (
        "ok"
        if status == "ok" and (http_status or 0) < 400
        else f"http_{http_status}"
        if status == "ok" and http_status is not None
        else status
    )
    billable = status != "circuit_open"

    record_call(
        provider=provider,
        operation=operation or "request",
        sku_class=sku_class,
        status=call_status,
        duration_ms=duration_ms,
        http_status=http_status,
        attempted=status != "circuit_open",
        billable=billable,
    )

    app_event(
        "outbound_call",
        endpoint=endpoint,
        status=status,
        http_status=http_status,
        ms=round(duration_ms, 2),
        **(
            {"provider": provider, "operation": operation, "sku_class": sku_class}
            if operation
            else {"provider": provider, "operation": "request"}
        ),
    )
