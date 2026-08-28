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
longer blocks on dozens of sequential round-trips. Outbound calls share the
process-wide pooled HTTP client, and durable (L2) writes are handed to a
background writer, so neither TLS setup nor a slow store shows up as
user-visible latency.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Queue
from threading import Condition, RLock, Thread
from typing import Any

import httpx

from tripplanner import http_client
from tripplanner.config import get_settings
from tripplanner.json_store import atomic_write_json
from tripplanner.tools.google_places import _BASE, is_configured

log = logging.getLogger(__name__)

_MAX_PHOTOS_PER_PLACE = 3
_HTTP_TIMEOUT_S = 10
# Place details (id, rating, address, summary, lat/lng, photo refs, reviews)
# and the top-places lists barely change, so we keep them for a week. Signed
# photo URLs are the exception — Google expires those within ~1h — so they get
# a much shorter TTL and are re-resolved on demand from the long-lived refs.
_META_TTL_S = 7 * 24 * 60 * 60  # 1 week
_MISS_TTL_S = 60  # transient lookup failures must not hide itinerary pins for a week
_PHOTO_TTL_S = 50 * 60  # re-sign photo URLs before Google's ~1h expiry
_MAX_WORKERS = 8
_MAX_ENTRIES = 800  # soft cap; evict the oldest beyond this


def _ttl(seconds: int | float) -> int:
    return get_settings().cache_ttl(seconds)

# Durable L2 store so warm data survives container restarts. Each place is one
# small Cosmos item (keyed by a hash of the cache key) so the store scales well
# past Cosmos's 2 MiB per-item limit; ``_COSMOS_DOC_ID`` is the legacy monolithic
# document we delete once after migrating to the sharded layout.
_COSMOS_CONTAINER = "places_cache"
_COSMOS_PARTITION = "_shared"  # places are global, not per-user
_COSMOS_DOC_ID = "cache"  # legacy single-document store; deleted after first shard write

# Process-wide cache shared across FastAPI request and prefetch threads.
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = RLock()
_KEY_LOCKS = tuple(RLock() for _ in range(64))
_LOAD_LOCK = RLock()
_PERSIST_LOCK = RLock()
_loaded = False
_suppress_persist = 0  # >0 while a batch is in flight (one write at the end)
_dirty_keys: set[str] = set()  # keys awaiting a durable write while a batch is in flight
_persist_retry_after = 0.0
_legacy_doc_cleaned = False

# Durable writes are best-effort, so they run on a single background thread: a
# slow or stalled store must never add latency to the request that warmed the
# cache (a Cosmos read timeout once added ~65s to a destination switch).
_WRITE_QUEUE: Queue[set[str]] = Queue()
_WRITE_CV = Condition()
_writer: Thread | None = None
_queued_writes = 0


def _local_path() -> Path:
    base = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    return base / "places_cache" / "cache.json"


def _load() -> None:
    with _LOAD_LOCK:
        _load_once()


def _load_once() -> None:
    """Populate ``_CACHE`` from the durable store once per process.

    With Cosmos enabled the durable layer is sharded (one item per key) and read
    lazily on demand, so there is no bulk load here. The single-file local store
    (dev / Cosmos disabled) is still loaded eagerly.
    """
    global _loaded
    with _CACHE_LOCK:
        if _loaded:
            return
    try:
        from tripplanner import storage_cosmos

        cosmos_enabled = storage_cosmos.is_enabled()
    except Exception as exc:  # noqa: BLE001 - durable cache is best-effort
        log.warning("places_cache cosmos load failed: %s", exc)
        cosmos_enabled = False
    raw: Any = None
    if not cosmos_enabled:
        try:
            p = _local_path()
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8")).get("entries")
        except Exception as exc:  # noqa: BLE001
            log.warning("places_cache local load failed: %s", exc)
            raw = None
    if not isinstance(raw, dict):
        with _CACHE_LOCK:
            _loaded = True
        return
    now = time.time()
    with _CACHE_LOCK:
        for k, v in raw.items():
            ttl = _ttl(_MISS_TTL_S if _is_miss(v) else _META_TTL_S)
            if isinstance(v, dict) and (now - v.get("__at__", 0.0)) < ttl:
                _CACHE[k] = v
        _loaded = True


def _doc_id(key: str) -> str:
    """Cosmos-safe item id for a cache key (keys contain spaces, '/', '|')."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _persistable(entry: dict[str, Any]) -> dict[str, Any]:
    """Drop volatile signed-photo fields before persisting; they expire within
    ~1h and are re-resolved from the long-lived ``photo_refs`` on reload."""
    return {k: v for k, v in entry.items() if k not in ("photo_urls", "__photos_at__")}


def _live_snapshot() -> dict[str, dict[str, Any]]:
    """Full persist-ready copy of the cache for the single-file local store.

    Drops volatile photo URLs and skips entries whose TTL has already lapsed —
    those are never served, so persisting them only bloats the file. Must be
    called while holding ``_CACHE_LOCK``.
    """
    now = time.time()
    snapshot: dict[str, dict[str, Any]] = {}
    for k, v in _CACHE.items():
        ttl = _ttl(_MISS_TTL_S if _is_miss(v) else _META_TTL_S)
        if (now - v.get("__at__", 0.0)) >= ttl:
            continue
        snapshot[k] = _persistable(v)
    return snapshot


def _durable_read(key: str) -> dict[str, Any] | None:
    """Point-read one key's entry from the sharded Cosmos store (or None)."""
    try:
        from tripplanner import storage_cosmos

        if not storage_cosmos.is_enabled():
            return None
        doc = storage_cosmos.read_doc(_COSMOS_CONTAINER, _COSMOS_PARTITION, _doc_id(key))
    except Exception as exc:  # noqa: BLE001 - durable cache is best-effort
        log.warning("places_cache cosmos load failed: %s", exc)
        return None
    entry = doc.get("entry") if isinstance(doc, dict) else None
    return entry if isinstance(entry, dict) else None


def _cleanup_legacy_doc() -> None:
    """One-time best-effort delete of the pre-sharding monolithic cache doc."""
    global _legacy_doc_cleaned
    if _legacy_doc_cleaned:
        return
    _legacy_doc_cleaned = True
    try:
        from tripplanner import storage_cosmos

        storage_cosmos.delete_doc(_COSMOS_CONTAINER, _COSMOS_PARTITION, _COSMOS_DOC_ID)
    except Exception:  # noqa: BLE001 - orphan cleanup must never break a write
        pass


def _writer_loop() -> None:
    global _queued_writes
    while True:
        try:
            keys = _WRITE_QUEUE.get(timeout=1.0)
        except Empty:
            continue
        try:
            with _PERSIST_LOCK:
                _write_durable(keys)
        except Exception as exc:  # noqa: BLE001 - durable cache is best-effort
            log.warning("places_cache durable write failed: %s", exc)
        finally:
            with _WRITE_CV:
                _queued_writes -= 1
                _WRITE_CV.notify_all()


def _schedule_durable(keys: set[str]) -> None:
    """Hand the keys to the background writer; never blocks the caller."""
    global _writer, _queued_writes
    if not keys:
        return
    with _WRITE_CV:
        if _writer is None:
            _writer = Thread(target=_writer_loop, name="places-cache-writer", daemon=True)
            _writer.start()
            atexit.register(flush_writes)
        _queued_writes += 1
    _WRITE_QUEUE.put(set(keys))


def flush_writes(timeout: float = 10.0) -> bool:
    """Block until queued durable writes drain. Returns False on timeout.

    Used by tests (which assert on the durable store right after a lookup) and
    at interpreter exit so a pending write isn't lost on shutdown.
    """
    with _WRITE_CV:
        if not _queued_writes:
            return True
        deadline = time.time() + timeout
        while _queued_writes:
            remaining = deadline - time.time()
            if remaining <= 0:
                return False
            _WRITE_CV.wait(remaining)
    return True


def _persist_entry(key: str) -> None:
    """Persist a single touched key. Batched writes defer to the block's end."""
    with _CACHE_LOCK:
        if _suppress_persist:
            _dirty_keys.add(key)
            return
    _schedule_durable({key})


def _persist() -> None:
    """Persist every currently cached key (used at the end of a batch)."""
    with _CACHE_LOCK:
        keys = set(_CACHE.keys())
    _schedule_durable(keys)


def _write_durable(keys: set[str]) -> None:
    """Write the given keys durably. Best-effort; never raises.

    Cosmos: one small item per key, so the store scales past the 2 MiB per-item
    limit. On success the legacy monolithic doc is cleaned up once. On throttling
    (429) we back off briefly; on any Cosmos failure we fall back to the
    single-file local store. When Cosmos is disabled (dev) we write only local.
    """
    global _persist_retry_after
    with _CACHE_LOCK:
        entries = {k: _persistable(_CACHE[k]) for k in keys if k in _CACHE}
        retry_after = _persist_retry_after
    now = time.time()
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled() and now >= retry_after:
            ok = True
            for k, entry in entries.items():
                try:
                    storage_cosmos.upsert_doc(
                        _COSMOS_CONTAINER,
                        _COSMOS_PARTITION,
                        _doc_id(k),
                        {"key": k, "entry": entry},
                    )
                except Exception as exc:  # noqa: BLE001
                    if getattr(exc, "status_code", None) == 429:
                        # Throttled: keep the cache warm locally and pause Cosmos
                        # retries so a burst of warming doesn't spam warnings.
                        with _CACHE_LOCK:
                            _persist_retry_after = now + 5 * 60
                    else:
                        log.warning("places_cache cosmos persist failed: %s", exc)
                    ok = False
                    break
            if ok:
                _cleanup_legacy_doc()
                return
    except Exception as exc:  # noqa: BLE001
        log.warning("places_cache cosmos persist failed: %s", exc)
    try:
        with _CACHE_LOCK:
            snapshot = _live_snapshot()
        atomic_write_json(_local_path(), {"entries": snapshot})
    except Exception as exc:  # noqa: BLE001
        log.warning("places_cache local persist failed: %s", exc)


@contextmanager
def _batched_persist():
    """Suppress per-key writes inside the block, then flush them together.

    Warming a destination touches many places; batching collapses the trailing
    per-key persists into one flush of the dirty keys.
    """
    global _suppress_persist
    with _CACHE_LOCK:
        _suppress_persist += 1
    try:
        yield
    finally:
        with _CACHE_LOCK:
            _suppress_persist -= 1
            should_persist = _suppress_persist == 0
            keys = set(_dirty_keys) if should_persist else set()
            if should_persist:
                _dirty_keys.clear()
    _schedule_durable(keys)


def _evict_if_needed() -> None:
    with _CACHE_LOCK:
        if len(_CACHE) <= _MAX_ENTRIES:
            return
        ordered = sorted(_CACHE.items(), key=lambda kv: kv[1].get("__at__", 0.0))
        for k, _ in ordered[: len(_CACHE) - _MAX_ENTRIES]:
            _CACHE.pop(k, None)


def _cache() -> dict[str, dict[str, Any]]:
    """Return the process-wide cache (loaded from the durable store once)."""
    _load()
    return _CACHE


def _is_miss(entry: Any) -> bool:
    return isinstance(entry, dict) and not any(
        key for key in entry if not key.startswith("__")
    )


def _has_location(entry: dict[str, Any]) -> bool:
    return entry.get("lat") is not None and entry.get("lng") is not None


def _fresh(entry: dict[str, Any] | None, ttl: float | None = None) -> bool:
    """Whether a cached entry may still be believed.

    An entry with no coordinates is not knowledge about a place, it is a lookup
    that half-worked, and holding it for a week kept eight Paris stops off the
    map with no request ever being retried. It expires like a miss instead.
    """
    if entry is None:
        return False
    if ttl is None and not _is_miss(entry) and not _has_location(entry):
        ttl = _ttl(_MISS_TTL_S)
    effective_ttl = (
        ttl
        if ttl is not None
        else _ttl(_MISS_TTL_S if _is_miss(entry) else _META_TTL_S)
    )
    return (time.time() - entry.get("__at__", 0.0)) < effective_ttl


def _is_explicit_airport_name(name: str) -> bool:
    normalized = " ".join(str(name or "").strip().lower().split())
    trimmed = normalized.rstrip(".,;:()[]{}")
    padded = f" {trimmed} "
    tokens = trimmed.replace(",", " ").split()
    airport_index = tokens.index("airport") if "airport" in tokens else -1
    suffix = tokens[airport_index + 1 :] if airport_index >= 0 else []
    has_terminal_suffix = bool(suffix) and (
        suffix[0] in {"terminal", "terminals"}
        or (suffix[0].startswith("t") and suffix[0][1:].isdigit())
    )
    return (
        trimmed.endswith(" airport")
        or " international airport " in padded
        or " domestic airport " in padded
        or normalized.startswith("airport,")
        or has_terminal_suffix
    )


def _lookup_city(name: str, city: str) -> str:
    return "" if _is_explicit_airport_name(name) else city


def _key(name: str, city: str) -> str:
    lookup_city = _lookup_city(name, city)
    return f"{(name or '').strip().lower()}|{(lookup_city or '').strip().lower()}"


def _key_lock(key: str) -> RLock:
    return _KEY_LOCKS[hash(key) % len(_KEY_LOCKS)]


def _headers(field_mask: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_settings().google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }


def normalize_place(p: dict[str, Any], name: str = "") -> dict[str, Any]:
    """Shape one Google place into the cached summary every reader expects.

    Pure, so the contract with ``place_facts`` can be tested without a request.
    """
    loc = p.get("location") or {}
    return {
        "place_id": p.get("id", ""),
        "name": p.get("displayName", {}).get("text", name),
        "address": p.get("formattedAddress", ""),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "price_level": p.get("priceLevel"),
        "website": p.get("websiteUri", ""),
        "editorial_summary": p.get("editorialSummary", {}).get("text", ""),
        "business_status": p.get("businessStatus", ""),
        "open_now": (p.get("currentOpeningHours") or {}).get("openNow"),
        "weekday_descriptions": (p.get("regularOpeningHours") or {}).get(
            "weekdayDescriptions", []
        ),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "photo_refs": [ph.get("name") for ph in (p.get("photos") or []) if ph.get("name")],
    }


def _lookup_place(name: str, city: str) -> dict[str, Any] | None:
    """One Text Search call to grab id + photos + summary in a single hit."""
    if not is_configured() or not name:
        return None
    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.rating,"
        "places.userRatingCount,places.priceLevel,places.photos,"
        "places.editorialSummary,places.websiteUri,places.location,"
        "places.businessStatus,places.currentOpeningHours.openNow,"
        "places.regularOpeningHours.weekdayDescriptions"
    )
    for attempt in range(2):
        try:
            resp = http_client.post(
                f"{_BASE}/places:searchText",
                headers=_headers(field_mask),
                json={"textQuery": f"{name} {city}".strip(), "pageSize": 1},
                timeout=_HTTP_TIMEOUT_S,
            )
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            if attempt == 0 and exc.response.status_code >= 500:
                continue
            log.warning("places lookup failed for %s: %s", name, exc)
            return None
        except httpx.HTTPError as exc:
            log.warning("places lookup failed for %s: %s", name, exc)
            return None

    places = resp.json().get("places") or []
    if not places:
        return None
    return normalize_place(places[0], name)


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
        resp = http_client.get(
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
        resp = http_client.get(
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
    lookup_city = _lookup_city(name, city)
    k = _key(name, lookup_city)
    with _CACHE_LOCK:
        fresh_before_lock = not refresh and _fresh(cache.get(k))
    with _key_lock(k):
        with _CACHE_LOCK:
            entry = cache.get(k)
            if not refresh and _fresh(entry):
                _record_cache("memory_hit" if fresh_before_lock else "coalesced_hit")
                return {} if _is_miss(entry) else entry  # type: ignore[return-value]
        if not refresh:
            durable = _durable_read(k)
            if durable is not None and _fresh(durable):
                with _CACHE_LOCK:
                    cache[k] = durable
                    _evict_if_needed()
                    _record_cache("durable_hit")
                return {} if _is_miss(durable) else durable
        _record_cache("refresh" if refresh else "miss")
        info = _lookup_place(name, lookup_city) or {}
        info["__at__"] = time.time()
        with _CACHE_LOCK:
            cache[k] = info
            _evict_if_needed()
        _persist_entry(k)
        return {} if _is_miss(info) else info


def _record_cache(result: str) -> None:
    from tripplanner.observability import app_event

    app_event("cache_access", cache="google_places", result=result)


def get_photos(
    name: str, city: str, max_photos: int = _MAX_PHOTOS_PER_PLACE, *, refresh: bool = False
) -> list[str]:
    """Return up to ``max_photos`` renderable image URLs for ``name``."""
    info = _ensure(name, city, refresh=refresh)
    if not info:
        return []
    with _CACHE_LOCK:
        stale = (time.time() - info.get("__photos_at__", 0.0)) >= _ttl(_PHOTO_TTL_S)
        needs_photos = refresh or "photo_urls" not in info or stale
        refs = list((info.get("photo_refs") or [])[:max_photos])
        current = list(info.get("photo_urls") or [])
    if not needs_photos:
        _record_cache("photo_url_hit")
        return current
    _record_cache("photo_url_refresh" if current else "photo_url_miss")
    photo_urls = _photo_uris(refs)
    with _CACHE_LOCK:
        info["photo_urls"] = photo_urls
        info["__photos_at__"] = time.time()
    return photo_urls


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
        else:
            get_details(name, city, refresh=refresh)
        if max_photos > 0:
            get_photos(name, city, max_photos=max_photos, refresh=refresh)

    with _batched_persist():
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(todo))) as ex:
            list(ex.map(_one, todo))


def get_summary(name: str, city: str, *, refresh: bool = False) -> dict[str, Any] | None:
    """Return the full cached info dict (rating, summary, reviews, etc.)."""
    info = _ensure(name, city, refresh=refresh)
    if not info:
        return None
    with _CACHE_LOCK:
        needs_reviews = refresh or "reviews" not in info
        place_id = info.get("place_id", "")
    if needs_reviews:
        reviews = _fetch_reviews(place_id)
        with _CACHE_LOCK:
            info["reviews"] = reviews
        _persist_entry(_key(name, _lookup_city(name, city)))
    return info


def get_details(name: str, city: str, *, refresh: bool = False) -> dict[str, Any] | None:
    """Return place metadata without the extra reviews request."""
    return _ensure(name, city, refresh=refresh) or None


def refresh_details(name: str, city: str) -> tuple[dict[str, Any] | None, bool]:
    """Refresh place facts without discarding a usable cached entry on failure."""
    cache = _cache()
    lookup_city = _lookup_city(name, city)
    key = _key(name, lookup_city)
    with _key_lock(key):
        with _CACHE_LOCK:
            previous = cache.get(key)
        if previous is None:
            previous = _durable_read(key)
        _record_cache("refresh")
        info = _lookup_place(name, lookup_city)
        if info is None:
            known = previous if previous and not _is_miss(previous) else None
            return known, False
        info["__at__"] = time.time()
        with _CACHE_LOCK:
            cache[key] = info
            _evict_if_needed()
        _persist_entry(key)
        return info, True


def place_coords(name: str, city: str = "") -> tuple[float, float] | None:
    """Return cached (lat, lng) for a place, or None if not found or not configured."""
    if not is_configured():
        return None
    info = _ensure(name, city, refresh=False)
    if info and info.get("lat") and info.get("lng"):
        return (info["lat"], info["lng"])
    return None


def top_places(destination: str, kind: str, n: int = 4, *, refresh: bool = False) -> list[str]:
    """Return the names of the top ``n`` hotels/attractions/restaurants in ``destination``.

    Used by the sidebar as a fallback so the panels fill in with the
    destination's highlights *before* the user has locked any selections.
    ``kind`` is ``"hotel"``, ``"attraction"`` or ``"restaurant"``. Results are
    cached per ``(destination, kind)`` so we only hit Places once.
    """
    if not is_configured() or not destination:
        return []
    cache = _cache()
    ck = f"__top__|{kind}|{destination.strip().lower()}"
    with _key_lock(ck):
        with _CACHE_LOCK:
            entry = cache.get(ck)
            if not refresh and _fresh(entry):
                return entry.get("names", [])  # type: ignore[union-attr]
        if not refresh:
            durable = _durable_read(ck)
            if durable is not None and _fresh(durable):
                with _CACHE_LOCK:
                    cache[ck] = durable
                    _evict_if_needed()
                return durable.get("names", [])

        if kind == "hotel":
            query = f"best hotels in {destination}"
        elif kind == "restaurant":
            query = f"best restaurants in {destination}"
        else:
            query = f"top tourist attractions in {destination}"
        names: list[str] = []
        try:
            resp = http_client.post(
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

        with _CACHE_LOCK:
            cache[ck] = {"names": names, "__at__": time.time()}
            _evict_if_needed()
        _persist_entry(ck)
        return names


def clear_cache() -> None:
    """Drop every cached entry. Useful for tests."""
    global _loaded, _legacy_doc_cleaned, _persist_retry_after
    flush_writes()
    with _CACHE_LOCK:
        _CACHE.clear()
        _dirty_keys.clear()
        _loaded = False
        _legacy_doc_cleaned = False
        _persist_retry_after = 0.0

