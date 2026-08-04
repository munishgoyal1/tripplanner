"""Tests for the durable Google Places cache (tripplanner.web.places_cache).

The cache keeps place details for a week (persisted across restarts) while
re-resolving the short-lived signed photo URLs on demand. These tests mock the
network layer so they're deterministic and never touch Google or Cosmos.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tripplanner.web import places_cache as pc


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


def test_persist_then_reload_restores_details(_isolate, tmp_path):
    pc.get_summary("Taj", "Goa")
    # File written under the tmp TRIPPLANNER_HOME.
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

    monkeypatch.setattr(pc.httpx, "post", fake_post)
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

    class FakeThrottle(Exception):
        status_code = 429

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "upsert_doc", lambda *args, **kwargs: (_ for _ in ()).throw(FakeThrottle("throttled")))
    warnings: list[str] = []
    monkeypatch.setattr(pc.log, "warning", lambda msg, *args: warnings.append(msg % args if args else msg))

    pc._CACHE[pc._key("Throttle Place", "Goa")] = {"__at__": time.time(), "name": "Throttle Place"}
    pc._persist_retry_after = 0.0

    pc._persist()

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


def test_bounded_for_cosmos_passthrough_under_cap(_isolate):
    snapshot = {"a": {"__at__": 1.0, "name": "A"}}
    assert pc._bounded_for_cosmos(snapshot) == snapshot


def test_bounded_for_cosmos_drops_oldest_over_cap(_isolate, monkeypatch):
    import json

    monkeypatch.setattr(pc, "_COSMOS_MAX_BYTES", 400)
    snapshot = {f"k{i}": {"__at__": float(i), "blob": "x" * 100} for i in range(6)}
    bounded = pc._bounded_for_cosmos(snapshot)
    doc_bytes = len(json.dumps({"entries": bounded}, separators=(",", ":")).encode())
    assert doc_bytes <= pc._COSMOS_MAX_BYTES
    assert bounded  # keeps at least the newest entries
    assert "k5" in bounded  # newest survive
    assert "k0" not in bounded  # oldest dropped
    assert set(bounded).issubset(set(snapshot))


def test_persist_stays_under_cosmos_cap(_isolate, monkeypatch):
    import json

    from tripplanner import storage_cosmos

    monkeypatch.setattr(pc, "_COSMOS_MAX_BYTES", 500)
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    captured: dict = {}
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda container, partition, doc_id, doc: captured.__setitem__("doc", doc),
    )
    now = time.time()
    with pc._CACHE_LOCK:
        for i in range(10):
            pc._CACHE[f"k{i}"] = {"__at__": now + i, "blob": "y" * 80}
    pc._persist_retry_after = 0.0
    pc._persist()
    body = json.dumps(captured["doc"], separators=(",", ":")).encode()
    assert len(body) <= pc._COSMOS_MAX_BYTES



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

