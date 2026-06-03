"""Per-session cache for Google Places lookups used by the right-rail sidebar.

Why a separate module? The graph's ``@tool`` functions in
``multiagent.tools.google_places`` return formatted strings designed for an
LLM to read. The sidebar needs structured dicts and image URLs we can pass
into ``cl.Image``. Rather than parse LLM-formatted output, this module hits
the Places API (v1) directly and caches by ``(name, city)``.

Per-user, per-session cache lives in ``cl.user_session`` under the key
``"places_cache"``. It's cleared on chat restart (Chainlit lifecycle), which
keeps signed photo URLs from going stale (Google photo URIs expire within
an hour or so).

Outside a Chainlit request (e.g. unit tests) the cache falls back to a
module-level dict so the helpers stay importable.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from multiagent.config import get_settings
from multiagent.tools.google_places import _BASE, is_configured

log = logging.getLogger(__name__)

_MAX_PHOTOS_PER_PLACE = 3
_HTTP_TIMEOUT_S = 10

# Fallback cache for non-Chainlit contexts (tests, scripts).
_FALLBACK_CACHE: dict[str, dict[str, Any]] = {}


def _cache() -> dict[str, dict[str, Any]]:
    """Return the session-scoped cache, or a process-wide fallback."""
    try:
        import chainlit as cl

        c = cl.user_session.get("places_cache")
        if c is None:
            c = {}
            cl.user_session.set("places_cache", c)
        return c
    except Exception:
        return _FALLBACK_CACHE


def _key(name: str, city: str) -> str:
    return f"{(name or '').strip().lower()}|{(city or '').strip().lower()}"


def _headers(field_mask: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_settings().google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _lookup_place(name: str, city: str) -> dict[str, Any] | None:
    """One Text Search call to grab id + photos + summary in a single hit."""
    if not is_configured() or not name:
        return None
    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.rating,"
        "places.userRatingCount,places.photos,places.editorialSummary,"
        "places.websiteUri"
    )
    try:
        resp = httpx.post(
            f"{_BASE}/places:searchText",
            headers=_headers(field_mask),
            json={"textQuery": f"{name} {city}".strip(), "pageSize": 1},
            timeout=_HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("places lookup failed for %s: %s", name, exc)
        return None

    places = resp.json().get("places") or []
    if not places:
        return None
    p = places[0]
    return {
        "place_id": p.get("id", ""),
        "name": p.get("displayName", {}).get("text", name),
        "address": p.get("formattedAddress", ""),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "website": p.get("websiteUri", ""),
        "editorial_summary": p.get("editorialSummary", {}).get("text", ""),
        "photo_refs": [
            ph.get("name") for ph in (p.get("photos") or []) if ph.get("name")
        ],
    }


def _photo_uri(photo_ref: str, max_width_px: int = 800) -> str | None:
    """Convert a ``places/.../photos/...`` reference into a renderable URL.

    Uses ``skipHttpRedirect=true`` so we get back JSON with ``photoUri``
    instead of following the binary redirect ourselves.
    """
    if not photo_ref or not is_configured():
        return None
    try:
        resp = httpx.get(
            f"{_BASE}/{photo_ref}/media",
            params={
                "key": get_settings().google_places_api_key,
                "maxWidthPx": max_width_px,
                "skipHttpRedirect": "true",
            },
            timeout=_HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("places photo URI fetch failed: %s", exc)
        return None
    return resp.json().get("photoUri")


def _fetch_reviews(place_id: str) -> list[dict[str, Any]]:
    if not place_id or not is_configured():
        return []
    try:
        resp = httpx.get(
            f"{_BASE}/places/{place_id}",
            headers=_headers("reviews"),
            timeout=_HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("places reviews fetch failed: %s", exc)
        return []
    reviews = resp.json().get("reviews") or []
    out: list[dict[str, Any]] = []
    for r in reviews[:5]:
        text = (r.get("text", {}).get("text", "") or "").strip()
        if not text:
            continue
        out.append(
            {
                "rating": r.get("rating"),
                "text": text[:300],
                "author": r.get("authorAttribution", {}).get("displayName", ""),
            }
        )
    return out


def _ensure(name: str, city: str) -> dict[str, Any]:
    """Return cached info for ``(name, city)``; populate on first request.

    Always returns a dict — empty `{}` for known-misses so we don't retry."""
    cache = _cache()
    k = _key(name, city)
    if k in cache:
        return cache[k]
    info = _lookup_place(name, city) or {}
    cache[k] = info
    return info


def get_photos(
    name: str, city: str, max_photos: int = _MAX_PHOTOS_PER_PLACE
) -> list[str]:
    """Return up to ``max_photos`` renderable image URLs for ``name``."""
    info = _ensure(name, city)
    if not info:
        return []
    if "photo_urls" not in info:
        urls: list[str] = []
        for ref in (info.get("photo_refs") or [])[:max_photos]:
            uri = _photo_uri(ref)
            if uri:
                urls.append(uri)
        info["photo_urls"] = urls
    return info.get("photo_urls") or []


def get_summary(name: str, city: str) -> dict[str, Any] | None:
    """Return the full cached info dict (rating, summary, reviews, etc.)."""
    info = _ensure(name, city)
    if not info:
        return None
    if "reviews" not in info:
        info["reviews"] = _fetch_reviews(info.get("place_id", ""))
    return info


def top_places(destination: str, kind: str, n: int = 4) -> list[str]:
    """Return the names of the top ``n`` hotels/attractions in ``destination``.

    Used by the sidebar as a fallback so the panels fill in with the
    destination's highlights *before* the user has locked any selections.
    ``kind`` is ``"hotel"`` or ``"attraction"``. Results are cached per
    ``(destination, kind)`` so we only hit Places once.
    """
    if not is_configured() or not destination:
        return []
    cache = _cache()
    ck = f"__top__|{kind}|{destination.strip().lower()}"
    if ck in cache:
        return cache[ck].get("names", [])

    query = (
        f"best hotels in {destination}"
        if kind == "hotel"
        else f"top tourist attractions in {destination}"
    )
    names: list[str] = []
    try:
        resp = httpx.post(
            f"{_BASE}/places:searchText",
            headers=_headers("places.displayName,places.rating"),
            json={"textQuery": query, "pageSize": max(n, 1)},
            timeout=_HTTP_TIMEOUT_S,
        )
        resp.raise_for_status()
        for p in (resp.json().get("places") or [])[:n]:
            name = p.get("displayName", {}).get("text")
            if name:
                names.append(name)
    except httpx.HTTPError as exc:
        log.warning("top_places lookup failed for %s: %s", destination, exc)

    cache[ck] = {"names": names}
    return names


def clear_cache() -> None:
    """Drop every cached entry. Useful for tests."""
    try:
        import chainlit as cl

        cl.user_session.set("places_cache", {})
    except Exception:
        pass
    _FALLBACK_CACHE.clear()
