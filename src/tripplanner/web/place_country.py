"""Resolve a free-text place string to the country it sits in.

Document readiness needs one fact the trip does not store: whether the journey
crosses a border. The answer comes from Open-Meteo's geocoding endpoint — the
same keyless, quota-free service ``tools/weather.py`` already uses — and is
cached per place string, because a city's country does not change.

A lookup that fails is never cached, so a dropped network call does not turn
into a permanently wrong answer. A lookup that succeeds with no match is
cached, because that string will not start matching later.
"""

from __future__ import annotations

from threading import Lock

import httpx

from tripplanner import http_client

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT_S = 8

_cache: dict[str, str] = {}
_lock = Lock()


def _normalize(place: str) -> str:
    return " ".join(str(place or "").split())


def _candidates(place: str) -> list[str]:
    """Query forms to try, in order.

    Neither end of a place string is reliably the city: a trip's ``origin`` is
    often "Indiranagar, Bengaluru" while its ``destination`` is often "Paris,
    France". Trying the whole string first and then each part covers both
    without having to guess which shape we were handed.
    """
    text = _normalize(place)
    if not text:
        return []
    parts = [part.strip() for part in text.split(",") if part.strip()]
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in [text, *reversed(parts)]:
        key = candidate.casefold()
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)
    return ordered


def _lookup(name: str) -> str | None:
    """Country for one query form. ``""`` means no match, ``None`` means the
    lookup itself failed."""
    try:
        response = http_client.get(
            _GEOCODE,
            params={"name": name, "count": 1, "language": "en", "format": "json"},
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    if not results:
        return ""
    return str(results[0].get("country") or "").strip()


def resolve_country(place: str) -> str:
    """Country containing ``place``, or ``""`` when it cannot be determined."""
    key = _normalize(place).casefold()
    if not key:
        return ""
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached

    resolved = ""
    complete = False
    for candidate in _candidates(place):
        answer = _lookup(candidate)
        if answer is None:
            continue
        complete = True
        if answer:
            resolved = answer
            break

    if complete:
        with _lock:
            _cache[key] = resolved
    return resolved


def crosses_border(origin: str, destination: str) -> bool:
    """Whether two resolved country names are known to be different.

    Unknown on either side is not a border. The caller stays silent rather than
    guessing, which is the whole point of asking.
    """
    left = str(origin or "").strip().casefold()
    right = str(destination or "").strip().casefold()
    return bool(left and right and left != right)


def reset_cache() -> None:
    with _lock:
        _cache.clear()
