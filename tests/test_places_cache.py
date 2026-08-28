"""Tests for the durable Google Places cache (tripplanner.web.places_cache).

The cache keeps place details for a week (persisted across restarts) while
re-resolving the short-lived signed photo URLs on demand. These tests mock the
network layer so they're deterministic and never touch Google or Cosmos.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from tripplanner.validation.harness import EvidenceCollector, harness_scope
from tripplanner.web import places_cache as pc

_REAL_LOOKUP_PLACE = pc._lookup_place


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isolate the cache: tmp store dir, Cosmos off, deterministic network."""
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(pc, "is_configured", lambda: True)

    calls = {"lookup": 0, "photos": 0, "reviews": 0}

    def fake_lookup(name: str, city: str):
        calls["lookup"] += 1
        return {
            "place_id": f"id-{name}",
            "name": name,
            "address": f"{name} address",
            "rating": 4.5,
            "review_count": 100,
            "website": "",
            "editorial_summary": "nice",
            "lat": 1.0,
            "lng": 2.0,
            "photo_refs": [f"places/{name}/photos/a", f"places/{name}/photos/b"],
        }

    def fake_photo_uris(refs, max_width_px: int = 800):
        calls["photos"] += 1
        return [f"https://signed/{r}?t={time.time()}" for r in refs]

    def fake_reviews(place_id: str):
        calls["reviews"] += 1
        return [{"rating": 5, "text": "great", "author": "x"}]

    monkeypatch.setattr(pc, "_lookup_place", fake_lookup)
    monkeypatch.setattr(pc, "_photo_uris", fake_photo_uris)
    monkeypatch.setattr(pc, "_fetch_reviews", fake_reviews)

    pc.clear_cache()
    yield calls
    pc.clear_cache()


def test_details_cached_within_week(_isolate):
    calls = _isolate
    pc.get_summary("Taj", "Goa")
    pc.get_summary("Taj", "Goa")
    assert calls["lookup"] == 1  # second call served from cache


def test_places_cache_emits_miss_and_memory_hit(_isolate):
    with harness_scope("cache", run_id="cache-run"):
        with EvidenceCollector("cache-run", "cache") as collector:
            pc.get_details("Harness-only Place", "Harness City")
            pc.get_details("Harness-only Place", "Harness City")

    results = [
        event.fields["result"]
        for event in collector.evidence.events
        if event.kind == "cache_access"
    ]
    assert results == ["miss", "memory_hit"]


def test_places_cache_emits_forced_refresh(_isolate):
    pc.get_details("Refresh Place", "Refresh City")
    with harness_scope("cache", run_id="refresh-run"):
        with EvidenceCollector("refresh-run", "cache") as collector:
            pc.refresh_details("Refresh Place", "Refresh City")

    assert [event.fields["result"] for event in collector.evidence.events] == ["refresh"]


def test_explicit_airport_lookup_ignores_trip_destination(_isolate, monkeypatch):
    lookups: list[tuple[str, str]] = []

    def fake_lookup(name: str, city: str):
        lookups.append((name, city))
        return {"place_id": "blr", "name": "Kempegowda International Airport Bengaluru"}

    monkeypatch.setattr(pc, "_lookup_place", fake_lookup)

    pc.get_details("Bangalore Airport", "Rajasthan")
    pc.get_details("Bangalore Airport", "")
    pc.get_details("Airport Hotel", "Rajasthan")
    pc.get_details("Airport, Jaipur", "Rajasthan")
    pc.get_details("Bangalore Airport Terminal 1", "Rajasthan")

    assert lookups == [
        ("Bangalore Airport", ""),
        ("Airport Hotel", "Rajasthan"),
        ("Airport, Jaipur", ""),
        ("Bangalore Airport Terminal 1", ""),
    ]


def test_meta_ttl_is_one_week():
    assert pc._META_TTL_S == 7 * 24 * 60 * 60


def test_places_cache_applies_environment_ttl_scale(monkeypatch):
    settings = pc.get_settings()
    monkeypatch.setattr(settings, "cache_ttl_scale", 0.5)

    assert pc._ttl(pc._META_TTL_S) == pc._META_TTL_S // 2
    assert pc._ttl(pc._PHOTO_TTL_S) == pc._PHOTO_TTL_S // 2


def test_remembered_discovery_place_avoids_ui_lookup(_isolate):
    pc.remember_places(
        [
            {
                "place_id": "fort-aguada",
                "name": "Fort Aguada",
                "rating": 4.4,
                "lat": 15.49,
                "lng": 73.77,
                "photo_refs": ["places/fort-aguada/photos/one"],
            }
        ],
        "Goa",
    )

    details = pc.get_details("Fort Aguada", "Goa")

    assert details and details["place_id"] == "fort-aguada"
    assert _isolate["lookup"] == 0


def test_transient_lookup_miss_retries_after_short_ttl(_isolate, monkeypatch):
    calls = {"count": 0}

    def flaky_lookup(name: str, city: str):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return {
            "place_id": "fort-aguada",
            "name": name,
            "lat": 15.49,
            "lng": 73.77,
            "photo_refs": [],
        }

    monkeypatch.setattr(pc, "_lookup_place", flaky_lookup)

    assert pc.get_details("Fort Aguada", "Goa") is None
    assert pc.get_details("Fort Aguada", "Goa") is None
    assert calls["count"] == 1

    entry = pc._CACHE[pc._key("Fort Aguada", "Goa")]
    entry["__at__"] = time.time() - pc._MISS_TTL_S - 1

    details = pc.get_details("Fort Aguada", "Goa")
    assert details and details["place_id"] == "fort-aguada"
    assert calls["count"] == 2


def test_lookup_retries_one_transient_server_error(_isolate, monkeypatch):
    request = httpx.Request("POST", "https://places.googleapis.com/v1/places:searchText")
    responses = iter(
        [
            httpx.Response(500, request=request),
            httpx.Response(
                200,
                request=request,
                json={
                    "places": [
                        {
                            "id": "sunset-cafe",
                            "displayName": {"text": "Sunset Cafe Beach Stay"},
                            "location": {"latitude": 11.98, "longitude": 92.99},
                        }
                    ]
                },
            ),
        ]
    )
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return next(responses)

    monkeypatch.setattr(pc.http_client, "post", fake_post)

    result = _REAL_LOOKUP_PLACE("Sunset Cafe Beach Stay", "Neil Island")

    assert result and result["place_id"] == "sunset-cafe"
    assert calls["count"] == 2


def test_lookup_does_not_retry_client_error(_isolate, monkeypatch):
    request = httpx.Request("POST", "https://places.googleapis.com/v1/places:searchText")
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return httpx.Response(400, request=request)

    monkeypatch.setattr(pc.http_client, "post", fake_post)

    assert _REAL_LOOKUP_PLACE("Missing Place", "Goa") is None
    assert calls["count"] == 1


def test_refresh_details_preserves_known_facts_when_lookup_fails(_isolate, monkeypatch):
    known = pc.get_details("Taj", "Goa")
    monkeypatch.setattr(pc, "_lookup_place", lambda _name, _city: None)

    refreshed, succeeded = pc.refresh_details("Taj", "Goa")

    assert succeeded is False
    assert refreshed and refreshed["place_id"] == known["place_id"]
    assert pc.get_details("Taj", "Goa")["place_id"] == known["place_id"]


def test_refresh_details_replaces_known_facts(_isolate, monkeypatch):
    pc.get_details("Taj", "Goa")
    monkeypatch.setattr(
        pc,
        "_lookup_place",
        lambda name, _city: {
            "place_id": "new-id",
            "name": name,
            "business_status": "CLOSED_TEMPORARILY",
            "lat": 15.49,
            "lng": 73.77,
            "photo_refs": [],
        },
    )

    refreshed, succeeded = pc.refresh_details("Taj", "Goa")

    assert succeeded is True
    assert refreshed and refreshed["place_id"] == "new-id"
    assert pc.get_details("Taj", "Goa")["business_status"] == "CLOSED_TEMPORARILY"


def test_persist_then_reload_restores_details(_isolate, tmp_path):
    pc.get_summary("Taj", "Goa")
    # File written under the tmp TRIPPLANNER_HOME.
    assert pc.flush_writes()
    assert pc._local_path().exists()
    # Simulate a fresh process: wipe in-memory + allow reload.
    pc.clear_cache()
    info = pc.get_summary("Taj", "Goa")
    assert info is not None
    assert info["place_id"] == "id-Taj"
    # No extra lookup beyond the original — restored from disk.
    assert _isolate["lookup"] == 1


def test_photo_urls_not_persisted_but_reresolved(_isolate):
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 1
    # Persisted snapshot must not carry the signed URLs.
    import json

    assert pc.flush_writes()
    raw = json.loads(pc._local_path().read_text(encoding="utf-8"))["entries"]
    entry = raw[pc._key("Taj", "Goa")]
    assert "photo_urls" not in entry
    assert "__photos_at__" not in entry
    assert entry["photo_refs"]  # refs ARE kept for re-resolution
    # Reload → details restored, photos re-resolved (refs survive).
    pc.clear_cache()
    urls = pc.get_photos("Taj", "Goa")
    assert urls
    assert _isolate["lookup"] == 1  # details from disk
    assert _isolate["photos"] == 2  # photos re-signed


def test_photos_resign_after_photo_ttl(_isolate, monkeypatch):
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 1
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 1  # still fresh
    # Age the resolved photo timestamp past the photo TTL.
    entry = pc._CACHE[pc._key("Taj", "Goa")]
    entry["__photos_at__"] = time.time() - pc._PHOTO_TTL_S - 1
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 2  # re-signed, but no new lookup
    assert _isolate["lookup"] == 1


def test_reviews_refresh_on_independent_review_ttl(_isolate, monkeypatch):
    pc.get_summary("Taj", "Goa")
    entry = pc._CACHE[pc._key("Taj", "Goa")]
    entry["__reviews_at__"] = time.time() - 101
    monkeypatch.setattr(pc.get_settings(), "google_places_reviews_cache_ttl_sec", 100)

    pc.get_summary("Taj", "Goa")

    assert _isolate["lookup"] == 1
    assert _isolate["reviews"] == 2


def test_refresh_forces_refetch(_isolate):
    pc.get_summary("Taj", "Goa")
    assert _isolate["lookup"] == 1
    pc.get_summary("Taj", "Goa", refresh=True)
    assert _isolate["lookup"] == 2  # forced re-fetch despite fresh cache


def test_top_places_cached_and_refreshable(_isolate, monkeypatch):
    seen = {"n": 0}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"places": [{"displayName": {"text": "Hotel A"}}]}

    def fake_post(*a, **k):
        seen["n"] += 1
        return FakeResp()

    monkeypatch.setattr(pc.http_client, "post", fake_post)
    assert pc.top_places("Goa", "hotel") == ["Hotel A"]
    assert pc.top_places("Goa", "hotel") == ["Hotel A"]
    assert seen["n"] == 1  # cached
    pc.top_places("Goa", "hotel", refresh=True)
    assert seen["n"] == 2  # forced


def test_evict_keeps_under_cap(_isolate, monkeypatch):
    monkeypatch.setattr(pc, "_MAX_ENTRIES", 3)
    for i in range(6):
        pc.get_summary(f"Place{i}", "Goa")
    assert len(pc._CACHE) <= 3


def test_persist_throttling_falls_back_to_local(_isolate, monkeypatch):
    from tripplanner import storage_cosmos

    class ThrottleError(Exception):
        status_code = 429

    warnings: list[str] = []

    def _throttled_upsert(*args, **kwargs):
        raise ThrottleError("throttled")

    def _capture_warning(msg, *args):
        warnings.append(msg % args if args else msg)

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "upsert_doc", _throttled_upsert)
    monkeypatch.setattr(pc.log, "warning", _capture_warning)

    pc._CACHE[pc._key("Throttle Place", "Goa")] = {"__at__": time.time(), "name": "Throttle Place"}
    pc._persist_retry_after = 0.0

    pc._persist()

    assert pc.flush_writes()
    assert pc._local_path().exists()
    assert warnings == []
    assert pc._persist_retry_after > time.time()


def test_concurrent_cache_updates_and_snapshots_remain_valid(_isolate):
    names = [f"Place {index}" for index in range(40)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        summaries = list(executor.map(lambda name: pc.get_summary(name, "Goa"), names))

    assert all(summary and summary["place_id"] for summary in summaries)
    assert len(pc._CACHE) == len(names)

    import json

    assert pc.flush_writes()
    persisted = json.loads(pc._local_path().read_text(encoding="utf-8"))
    assert set(persisted["entries"]) == {pc._key(name, "Goa") for name in names}


def test_live_snapshot_drops_expired_and_photo_urls(_isolate):
    now = time.time()
    with pc._CACHE_LOCK:
        pc._CACHE.clear()
        pc._CACHE[pc._key("Fresh", "Goa")] = {
            "__at__": now,
            "name": "Fresh",
            "photo_urls": ["u"],
            "__photos_at__": now,
        }
        pc._CACHE[pc._key("Stale", "Goa")] = {
            "__at__": now - pc._META_TTL_S - 1,
            "name": "Stale",
        }
        snap = pc._live_snapshot()
    assert pc._key("Fresh", "Goa") in snap
    assert pc._key("Stale", "Goa") not in snap  # expired entries are never served
    fresh = snap[pc._key("Fresh", "Goa")]
    assert "photo_urls" not in fresh and "__photos_at__" not in fresh


def test_full_warming_snapshot_keeps_signed_photo_data(_isolate, monkeypatch):
    from tripplanner.config import get_settings

    monkeypatch.setattr(get_settings(), "cache_warm_everything", True)
    now = time.time()
    with pc._CACHE_LOCK:
        pc._CACHE.clear()
        pc._CACHE[pc._key("Fresh", "Goa")] = {
            "__at__": now,
            "name": "Fresh",
            "photo_urls": ["https://signed"],
            "__photos_at__": now,
        }
        snapshot = pc._live_snapshot()

    assert snapshot[pc._key("Fresh", "Goa")]["photo_urls"] == ["https://signed"]


def _fake_cosmos(monkeypatch, store: dict) -> None:
    """Point the durable layer at an in-memory sharded store keyed by doc id."""
    from tripplanner import storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda container, partition, doc_id, body: store.__setitem__(doc_id, body),
    )
    monkeypatch.setattr(
        storage_cosmos,
        "read_doc",
        lambda container, partition, doc_id: store.get(doc_id),
    )
    monkeypatch.setattr(
        storage_cosmos,
        "delete_doc",
        lambda container, partition, doc_id: store.pop(doc_id, None),
    )


def test_cosmos_persists_one_document_per_key(_isolate, monkeypatch):
    store: dict = {}
    _fake_cosmos(monkeypatch, store)
    pc.get_summary("Taj", "Goa")
    pc.get_summary("Oberoi", "Goa")
    # One small Cosmos item per place key — not a single shared document.
    assert pc.flush_writes()
    assert pc._doc_id(pc._key("Taj", "Goa")) in store
    assert pc._doc_id(pc._key("Oberoi", "Goa")) in store
    assert pc._COSMOS_DOC_ID not in store  # no monolithic doc
    body = store[pc._doc_id(pc._key("Taj", "Goa"))]
    assert body["key"] == pc._key("Taj", "Goa")
    assert body["entry"]["place_id"] == "id-Taj"


def test_stable_forever_marks_places_cosmos_items_never_expire(_isolate, monkeypatch):
    from tripplanner.config import get_settings

    store: dict = {}
    _fake_cosmos(monkeypatch, store)
    monkeypatch.setattr(get_settings(), "cache_stable_forever", True)

    pc.get_details("Taj", "Goa")

    assert pc.flush_writes()
    body = store[pc._doc_id(pc._key("Taj", "Goa"))]
    assert body["ttl"] == -1


def test_lazy_load_serves_from_cosmos_without_google(_isolate, monkeypatch):
    store: dict = {}
    _fake_cosmos(monkeypatch, store)
    pc.get_summary("Taj", "Goa")
    calls_before = _isolate["lookup"]
    pc.clear_cache()  # simulate a fresh process with an empty L1 cache
    result = pc.get_details("Taj", "Goa")
    assert result and result["place_id"] == "id-Taj"
    assert _isolate["lookup"] == calls_before  # served from Cosmos, no Google lookup


def test_legacy_monolithic_doc_deleted_after_shard_write(_isolate, monkeypatch):
    store: dict = {pc._COSMOS_DOC_ID: {"entries": {"old": {"__at__": time.time()}}}}
    _fake_cosmos(monkeypatch, store)
    pc.get_details("Taj", "Goa")
    assert pc.flush_writes()
    assert pc._COSMOS_DOC_ID not in store  # legacy doc cleaned up after migration




def test_concurrent_same_place_lookup_is_coalesced(_isolate, monkeypatch):
    original_lookup = pc._lookup_place

    def slow_lookup(name: str, city: str):
        time.sleep(0.05)
        return original_lookup(name, city)

    monkeypatch.setattr(pc, "_lookup_place", slow_lookup)

    with ThreadPoolExecutor(max_workers=8) as executor:
        summaries = list(
            executor.map(lambda _: pc.get_details("Taj", "Goa"), range(8))
        )

    assert all(summary and summary["place_id"] == "id-Taj" for summary in summaries)
    assert _isolate["lookup"] == 1



def test_an_entry_without_coordinates_expires_like_a_miss() -> None:
    """A half-worked lookup is not a fact about a place."""
    minutes_old = time.time() - (pc._MISS_TTL_S + 5)
    no_coords = {"name": "Musee d'Orsay", "place_id": "x", "__at__": minutes_old}
    assert not pc._fresh(no_coords)

    located = {**no_coords, "lat": 48.86, "lng": 2.32}
    assert pc._fresh(located)
