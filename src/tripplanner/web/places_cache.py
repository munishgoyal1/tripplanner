"""Process-level cache for Google Places lookups used by the trip panel.

Why a separate module? The graph's ``@tool`` functions in
``tripplanner.tools.google_places`` return formatted strings designed for an
LLM to read. The frontend needs structured dicts and image URLs. Rather than
parse LLM-formatted output, this module hits the Places API (v1) directly and
caches by ``(name, city)``.

The cache has two layers: a process-wide dict (hot L1) and a durable store
(L2) so warm data survives container restarts (ACA scales to zero). Place
details barely change, so they're kept for a week; the only short-lived part
is the signed photo URL, which Google expires within ~1h, so those are
re-resolved on demand from the long-lived photo references.

Lookups are parallelized: ``prefetch`` warms many places at once and photos
for a single place are fetched concurrently, so switching destinations no
longer blocks on dozens of sequential round-trips.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

from tripplanner.config import get_settings
from tripplanner.tools.google_places import _BASE, is_configured

log = logging.getLogger(__name__)

_MAX_PHOTOS_PER_PLACE = 3
_HTTP_TIMEOUT_S = 10
# Place details (id, rating, address, summary, lat/lng, photo refs, reviews)
# and the top-places lists barely change, so we keep them for a week. Signed
# photo URLs are the exception — Google expires those within ~1h — so they get
# a much shorter TTL and are re-resolved on demand from the long-lived refs.
_META_TTL_S = 7 * 24 * 60 * 60  # 1 week
_PHOTO_TTL_S = 50 * 60  # re-sign photo URLs before Google's ~1h expiry
_MAX_WORKERS = 8
_MAX_ENTRIES = 800  # soft cap; evict the oldest beyond this

# Durable L2 store so warm data survives container restarts.
_COSMOS_CONTAINER = "places_cache"
_COSMOS_PARTITION = "_shared"  # places are global, not per-user
_COSMOS_DOC_ID = "cache"

# Process-wide cache (shared across FastAPI requests; safe under the GIL).
_CACHE: dict[str, dict[str, Any]] = {}
_loaded = False
_suppress_persist = 0  # >0 while a batch is in flight (one write at the end)


def _local_path() -> Path:
    base = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    return base / "places_cache" / "cache.json"


def _load() -> None:
    """Populate ``_CACHE`` from the durable store once per process."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    raw: Any = None
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            doc = storage_cosmos.read_doc(
                _COSMOS_CONTAINER, _COSMOS_PARTITION, _COSMOS_DOC_ID
            )
            raw = (doc or {}).get("entries")
    except Exception as exc:  # noqa: BLE001 - durable cache is best-effort
        log.warning("places_cache cosmos load failed: %s", exc)
        raw = None
    if raw is None:
        try:
            p = _local_path()
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8")).get("entries")
        except Exception as exc:  # noqa: BLE001
            log.warning("places_cache local load failed: %s", exc)
            raw = None
    if not isinstance(raw, dict):
        return
    now = time.time()
    for k, v in raw.items():
        if isinstance(v, dict) and (now - v.get("__at__", 0.0)) < _META_TTL_S:
            _CACHE[k] = v


def _persist() -> None:
    """Write ``_CACHE`` to the durable store. Best-effort; never raises.

    Signed photo URLs are dropped before persisting — they expire within ~1h,
    so re-resolving from the long-lived ``photo_refs`` on reload is correct.
    """
    if _suppress_persist:
        return
    snapshot: dict[str, Any] = {}
    for k, v in _CACHE.items():
        snapshot[k] = {
            kk: vv for kk, vv in v.items() if kk not in ("photo_urls", "__photos_at__")
        }
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            storage_cosmos.upsert_doc(
                _COSMOS_CONTAINER,
                _COSMOS_PARTITION,
                _COSMOS_DOC_ID,
                {"entries": snapshot},
            )
            return
    except Exception as exc:  # noqa: BLE001
        log.warning("places_cache cosmos persist failed: %s", exc)
    try:
        p = _local_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"entries": snapshot}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("places_cache local persist failed: %s", exc)


@contextmanager
def _batched_persist():
    """Suppress per-entry writes inside the block, then persist once at the end.

    Warming a destination touches many places; without this each miss would
    rewrite the whole durable doc. Batch them into a single trailing write.
    """
    global _suppress_persist
    _suppress_persist += 1
    try:
        yield
    finally:
        _suppress_persist -= 1
    if _suppress_persist == 0:
        _persist()


def _evict_if_needed() -> None:
    if len(_CACHE) <= _MAX_ENTRIES:
        return
    ordered = sorted(_CACHE.items(), key=lambda kv: kv[1].get("__at__", 0.0))
    for k, _ in ordered[: len(_CACHE) - _MAX_ENTRIES]:
        _CACHE.pop(k, None)


def _cache() -> dict[str, dict[str, Any]]:
    """Return the process-wide cache (loaded from the durable store once)."""
    _load()
    return _CACHE


def _fresh(entry: dict[str, Any] | None, ttl: float = _META_TTL_S) -> bool:
    return entry is not None and (time.time() - entry.get("__at__", 0.0)) < ttl


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
        "places.websiteUri,places.location"
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
    loc = p.get("location") or {}
    return {
        "place_id": p.get("id", ""),
        "name": p.get("displayName", {}).get("text", name),
        "address": p.get("formattedAddress", ""),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "website": p.get("websiteUri", ""),
        "editorial_summary": p.get("editorialSummary", {}).get("text", ""),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
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


def _ensure(name: str, city: str, *, refresh: bool = False) -> dict[str, Any]:
    """Return cached info for ``(name, city)``; populate on first request.

    Always returns a dict — empty `{}` for known-misses so we don't retry
    within the TTL window. Pass ``refresh=True`` to force a re-fetch."""
    cache = _cache()
    k = _key(name, city)
    entry = cache.get(k)
    if not refresh and _fresh(entry):
        return entry  # type: ignore[return-value]
    info = _lookup_place(name, city) or {}
    info["__at__"] = time.time()
    cache[k] = info
    _evict_if_needed()
    _persist()
    return info


def get_photos(
    name: str, city: str, max_photos: int = _MAX_PHOTOS_PER_PLACE, *, refresh: bool = False
) -> list[str]:
    """Return up to ``max_photos`` renderable image URLs for ``name``."""
    info = _ensure(name, city, refresh=refresh)
    if not info:
        return []
    stale = (time.time() - info.get("__photos_at__", 0.0)) >= _PHOTO_TTL_S
    if refresh or "photo_urls" not in info or stale:
        info["photo_urls"] = _photo_uris((info.get("photo_refs") or [])[:max_photos])
        info["__photos_at__"] = time.time()
    return info.get("photo_urls") or []


def prefetch(
    names: list[str],
    city: str,
    *,
    max_photos: int = _MAX_PHOTOS_PER_PLACE,
    with_reviews: bool = True,
    refresh: bool = False,
) -> None:
    """Warm the cache for many places concurrently.

    Switching destinations needs a lookup + photos (+ reviews) for every
    place. Doing that serially is dozens of blocking round-trips; fanning the
    places out across a thread pool collapses it to roughly the latency of the
    slowest single place. Durable writes are batched into one trailing persist.
    """
    todo = list(dict.fromkeys(n for n in names if n))
    if not todo:
        return

    def _one(name: str) -> None:
        if with_reviews:
            get_summary(name, city, refresh=refresh)  # populates lookup + reviews
        get_photos(name, city, max_photos=max_photos, refresh=refresh)  # + photos

    with _batched_persist():
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(todo))) as ex:
            list(ex.map(_one, todo))


def get_summary(name: str, city: str, *, refresh: bool = False) -> dict[str, Any] | None:
    """Return the full cached info dict (rating, summary, reviews, etc.)."""
    info = _ensure(name, city, refresh=refresh)
    if not info:
        return None
    if refresh or "reviews" not in info:
        info["reviews"] = _fetch_reviews(info.get("place_id", ""))
        _persist()
    return info


def place_coords(name: str, city: str = "") -> tuple[float, float] | None:
    """Return cached (lat, lng) for a place, or None if not found or not configured."""
    if not is_configured():
        return None
    info = _ensure(name, city, refresh=False)
    if info and info.get("lat") and info.get("lng"):
        return (info["lat"], info["lng"])
    return None


def top_places(destination: str, kind: str, n: int = 4, *, refresh: bool = False) -> list[str]:
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
    if not refresh and _fresh(entry):
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
    _evict_if_needed()
    _persist()
    return names


def clear_cache() -> None:
    """Drop every cached entry. Useful for tests."""
    global _loaded
    _CACHE.clear()
    _loaded = False

