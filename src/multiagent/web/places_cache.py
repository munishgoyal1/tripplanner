"""Process-level cache for Google Places lookups used by the trip panel.

Why a separate module? The graph's ``@tool`` functions in
``multiagent.tools.google_places`` return formatted strings designed for an
LLM to read. The frontend needs structured dicts and image URLs. Rather than
parse LLM-formatted output, this module hits the Places API (v1) directly and
caches by ``(name, city)``.

The cache is a module-level dict shared across the FastAPI process. Each entry
carries a timestamp and expires after ``_TTL_S`` so signed photo URLs (which
Google expires within an hour or so) don't go stale.

Lookups are parallelized: ``prefetch`` warms many places at once and photos
for a single place are fetched concurrently, so switching destinations no
longer blocks on dozens of sequential round-trips.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from multiagent.config import get_settings
from multiagent.tools.google_places import _BASE, is_configured

log = logging.getLogger(__name__)

_MAX_PHOTOS_PER_PLACE = 3
_HTTP_TIMEOUT_S = 10
_TTL_S = 30 * 60  # signed photo URIs go stale within ~1h; refresh well before
_MAX_WORKERS = 8

# Process-wide cache (shared across FastAPI requests; safe under the GIL).
_CACHE: dict[str, dict[str, Any]] = {}


def _cache() -> dict[str, dict[str, Any]]:
    """Return the process-wide cache."""
    return _CACHE


def _fresh(entry: dict[str, Any] | None) -> bool:
    return entry is not None and (time.time() - entry.get("__at__", 0.0)) < _TTL_S


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


def _photo_uris(refs: list[str], max_width_px: int = 800) -> list[str]:
    """Resolve several photo references to URLs concurrently (order kept)."""
    refs = [r for r in refs if r]
    if not refs:
        return []
    if len(refs) == 1:
        uri = _photo_uri(refs[0], max_width_px)
        return [uri] if uri else []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(refs))) as ex:
        uris = list(ex.map(lambda r: _photo_uri(r, max_width_px), refs))
    return [u for u in uris if u]


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

    Always returns a dict — empty `{}` for known-misses so we don't retry
    within the TTL window."""
    cache = _cache()
    k = _key(name, city)
    entry = cache.get(k)
    if _fresh(entry):
        return entry  # type: ignore[return-value]
    info = _lookup_place(name, city) or {}
    info["__at__"] = time.time()
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
        info["photo_urls"] = _photo_uris((info.get("photo_refs") or [])[:max_photos])
    return info.get("photo_urls") or []


def prefetch(
    names: list[str],
    city: str,
    *,
    max_photos: int = _MAX_PHOTOS_PER_PLACE,
    with_reviews: bool = True,
) -> None:
    """Warm the cache for many places concurrently.

    Switching destinations needs a lookup + photos (+ reviews) for every
    place. Doing that serially is dozens of blocking round-trips; fanning the
    places out across a thread pool collapses it to roughly the latency of the
    slowest single place.
    """
    todo = list(dict.fromkeys(n for n in names if n))
    if not todo:
        return

    def _one(name: str) -> None:
        if with_reviews:
            get_summary(name, city)  # populates lookup + reviews
        get_photos(name, city, max_photos=max_photos)  # populates lookup + photos

    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(todo))) as ex:
        list(ex.map(_one, todo))


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
    entry = cache.get(ck)
    if _fresh(entry):
        return entry.get("names", [])  # type: ignore[union-attr]

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

    cache[ck] = {"names": names, "__at__": time.time()}
    return names


def clear_cache() -> None:
    """Drop every cached entry. Useful for tests."""
    _CACHE.clear()
