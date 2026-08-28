"""Resolve a free-text place string to the country it sits in.

Document readiness needs one fact the trip does not store: whether the journey
crosses a border. The answer comes from Open-Meteo's geocoding endpoint — the
same keyless, quota-free service ``tools/weather.py`` already uses — and is
cached per place string, because a city's country does not change.

A lookup that fails is never cached, so a dropped network call does not turn
into a permanently wrong answer. A lookup that succeeds with no match is
cached, because that string will not start matching later.

The geocoder matches loosely, and its top hit is not the best-known place: it
answers "Goa" with Genoa in Italy and "Bangalore" with a village in Sindh,
while the places a traveller means are absent from the results altogether.
Taking the first row therefore turned a Bengaluru-to-Goa trip into an
international one. A near-miss is not evidence, so a result counts only when
its name matches exactly, it is substantial enough to be the place a bare name
refers to, and it clearly outweighs any same-named rival in another country.
Anything short of that resolves to ``""``, and the caller stays silent.
"""

from __future__ import annotations

import unicodedata
from typing import Any

import httpx

from tripplanner import http_client
from tripplanner.caching import get_cache

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT_S = 8
_RESULT_COUNT = 10

# A bare name identifies a country only when one substantial place answers to
# it; under this, "Goa" resolves to a Philippine municipality of 21,000.
_MIN_POPULATION = 50_000
# ...and the winner must outweigh any same-named place in another country.
_DOMINANCE = 5

# Which country a place sits in does not change, so this is retained for a month
# and re-looked-up only when it falls out.
_cache = get_cache("place-country", default_ttl_seconds=30 * 24 * 60 * 60, volatile=False)


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


def _fold(value: Any) -> str:
    """Compare names without accents or casing, so "Goá" answers to "Goa"."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    ).casefold()


def _population(result: dict[str, Any]) -> int:
    value = result.get("population")
    return value if isinstance(value, int) and value > 0 else 0


def _confident_country(results: list[Any], name: str) -> tuple[str, str]:
    """Country name and ISO code of the one substantial place this name means."""
    target = _fold(name)
    named = [
        result
        for result in results
        if isinstance(result, dict)
        and _fold(result.get("name")) == target
        and str(result.get("country") or "").strip()
    ]
    if not named:
        return ("", "")

    best = max(named, key=_population)
    if _population(best) < _MIN_POPULATION:
        return ("", "")
    country = str(best.get("country")).strip()
    abroad = max(
        (
            _population(result)
            for result in named
            if _fold(result.get("country")) != _fold(country)
        ),
        default=0,
    )
    # Two comparable places of the same name say the trip cannot be placed.
    if abroad * _DOMINANCE > _population(best):
        return ("", "")
    return (country, str(best.get("country_code") or "").strip().upper())


def _lookup(name: str) -> tuple[str, str] | None:
    """Country for one query form. ``("", "")`` means no confident match, ``None``
    means the lookup itself failed."""
    try:
        response = http_client.get(
            _GEOCODE,
            params={
                "name": name,
                "count": _RESULT_COUNT,
                "language": "en",
                "format": "json",
            },
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return _confident_country(results, name)


def _resolve(place: str) -> tuple[str, str]:
    key = _normalize(place).casefold()
    if not key:
        return ("", "")
    cached = _cache.get(key)
    if cached is not None:
        # A JSON-backed cache returns the stored pair as a list, so both
        # backends have to agree on the tuple the callers unpack.
        country, code = cached
        return (str(country), str(code))

    resolved = ("", "")
    complete = False
    for candidate in _candidates(place):
        answer = _lookup(candidate)
        if answer is None:
            continue
        complete = True
        if answer[0]:
            resolved = answer
            break

    # A completed lookup that found nothing is still an answer worth keeping;
    # an incomplete one is not, so the next caller retries it.
    if complete:
        _cache.set(key, resolved)
    return resolved


def resolve_country(place: str) -> str:
    """Country containing ``place``, or ``""`` when it cannot be determined."""
    return _resolve(place)[0]


def resolve_country_code(place: str) -> str:
    """ISO 3166-1 alpha-2 code for ``place``, or ``""`` when unknown."""
    return _resolve(place)[1]


def crosses_border(origin: str, destination: str) -> bool:
    """Whether two resolved country names are known to be different.

    Unknown on either side is not a border. The caller stays silent rather than
    guessing, which is the whole point of asking.
    """
    left = str(origin or "").strip().casefold()
    right = str(destination or "").strip().casefold()
    return bool(left and right and left != right)


def reset_cache() -> None:
    _cache.clear()
