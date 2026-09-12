"""Tests for the durable Google Places cache (tripplanner.web.places_cache).

The cache keeps place details for a week (persisted across restarts) while
re-resolving the short-lived signed photo URLs on demand. These tests mock the
network layer so they're deterministic and never touch Google or Cosmos.
"""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx
import pytest

from tripplanner.places_budget import places_budget_scope
from tripplanner.validation.harness import EvidenceCollector, harness_scope
from tripplanner.web import places_cache as pc

_REAL_LOOKUP_PLACE = pc._lookup_place
_REAL_PHOTO_URIS = pc._photo_uris


@pytest.fixture(autouse=True)
def _authorized():
    """Every test here exercises cache mechanics, which needs a paid scope.

    Whether a *caller* gets one is an HTTP-layer policy (``route_may_spend``),
    not a property of the cache, so it is granted by default and the tests that
    are about the read-only path drop it explicitly with ``_read_only``.
    """
    with places_budget_scope("user_interaction"):
        yield


@contextmanager
def _read_only():
    """Run the block as a read-only caller: no paid-provider authorization."""
    from tripplanner import places_budget

    token = places_budget._BUDGET.set(None)
    try:
        yield
    finally:
        places_budget._BUDGET.reset(token)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isolate the cache: tmp store dir, Cosmos off, deterministic network."""
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    from tripplanner import secondary_cache, storage_cosmos

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(secondary_cache, "read_doc", lambda *_args: None)
    monkeypatch.setattr(secondary_cache, "merge_write", lambda *_args: False)
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
            "__photo_refs_schema": pc._PHOTO_REFS_SCHEMA,
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

    pc._shutting_down.clear()
    pc.clear_cache()
    yield calls
    pc.clear_cache()
    pc._shutting_down.clear()


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
    cache_events = [
        event.fields for event in collector.evidence.events if event.kind == "cache_access"
    ]
    assert {event["place"] for event in cache_events} == {"Harness-only Place"}
    assert {event["city"] for event in cache_events} == {"Harness City"}


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
    assert pc._ttl(pc._PHOTO_TTL_S) == settings.google_places_photo_url_cache_ttl_sec // 2


def test_stable_cache_does_not_make_misses_or_signed_photos_permanent(monkeypatch):
    settings = pc.get_settings()
    monkeypatch.setattr(settings, "cache_stable_forever", True)

    assert pc._ttl(pc._META_TTL_S) == -1
    assert pc._ttl(pc._MISS_TTL_S) == settings.google_places_miss_cache_ttl_sec
    assert pc._ttl(pc._PHOTO_TTL_S) == settings.google_places_photo_url_cache_ttl_sec


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
    assert details["__photo_refs_schema"] == pc._PHOTO_REFS_SCHEMA
    assert _isolate["lookup"] == 0


def test_photos_refresh_legacy_entry_with_unversioned_refs(_isolate, _authorized):
    key = pc._key("Legacy Place", "Paris")
    pc._CACHE[key] = {
        "place_id": "legacy-id",
        "name": "Legacy Place",
        "rating": 4.5,
        "photo_refs": [],
        "__at__": time.time(),
    }

    photos = pc.get_photos("Legacy Place", "Paris")

    assert len(photos) == 1
    assert _isolate["lookup"] == 1
    assert _isolate["photos"] == 1


def test_photos_do_not_refresh_entry_with_known_empty_refs(_isolate, _authorized):
    key = pc._key("No Photo Place", "Paris")
    pc._CACHE[key] = {
        "place_id": "no-photo-id",
        "name": "No Photo Place",
        "photo_refs": [],
        "__photo_refs_schema": pc._PHOTO_REFS_SCHEMA,
        "__at__": time.time(),
    }

    cache_events = []
    original = pc._record_cache
    pc._record_cache = lambda result, **fields: cache_events.append((result, fields))
    try:
        assert pc.get_photos("No Photo Place", "Paris") == []
        assert pc.get_photos("No Photo Place", "Paris") == []
    finally:
        pc._record_cache = original
    assert _isolate["lookup"] == 0
    assert not any(result == "photo_url_hit" for result, _fields in cache_events)


def test_prefetch_cache_hits_do_not_serialize_on_logging(_isolate, _authorized, monkeypatch):
    """Regression: _record_cache (app_event -> flight_recorder's synchronous,
    fsync-based write, tens of ms in production) must run outside _CACHE_LOCK.
    Otherwise prefetch()'s worker pool serializes on that lock and a warm
    multi-place prefetch takes seconds instead of the intended one slow-item's
    worth of wall time. Simulated here with a monkeypatched delay standing in
    for that real disk-I/O cost."""
    names = [f"Place{i}" for i in range(8)]
    for name in names:
        pc.get_details(name, "Goa")  # warm the cache: each becomes a hit below

    delay = 0.1
    real_record_cache = pc._record_cache

    def slow_record_cache(*args, **kwargs):
        time.sleep(delay)
        return real_record_cache(*args, **kwargs)

    monkeypatch.setattr(pc, "_record_cache", slow_record_cache)

    start = time.perf_counter()
    pc.prefetch(names, "Goa", max_photos=0, with_reviews=False)
    elapsed = time.perf_counter() - start

    # Serialized (logging inside the lock): ~len(names) * delay (0.8s).
    # Parallel (logging outside the lock): close to one `delay` (0.2s-0.3s).
    assert elapsed < delay * len(names) * 0.75


def test_lookup_place_propagates_circuit_open_instead_of_swallowing_it(
    _isolate, _authorized, monkeypatch
):
    def fake_post(*args, **kwargs):
        raise pc.http_client.CircuitOpenError("places.googleapis.com is temporarily unavailable")

    monkeypatch.setattr(pc.http_client, "post", fake_post)

    with pytest.raises(pc.http_client.CircuitOpenError):
        _REAL_LOOKUP_PLACE("Some Place", "Goa")


def test_ensure_does_not_cache_or_persist_a_circuit_open_lookup(_isolate, _authorized, monkeypatch):
    """Regression: a breaker-open failure is transient infra state, not
    "this place doesn't exist" -- caching/persisting it as a miss wastes a
    durable write per failed place during exactly the kind of provider outage
    that also floods logs (see the prefetch rate-limit fix alongside this)."""

    def raising_lookup(_name, _city):
        raise pc.http_client.CircuitOpenError("circuit open")

    monkeypatch.setattr(pc, "_lookup_place", raising_lookup)
    persisted = {"count": 0}
    real_persist = pc._persist_entry

    def counting_persist(key):
        persisted["count"] += 1
        return real_persist(key)

    monkeypatch.setattr(pc, "_persist_entry", counting_persist)

    result = pc._ensure("Circuit Broken Place", "Goa")

    assert result == {}
    assert persisted["count"] == 0
    assert pc._key("Circuit Broken Place", "Goa") not in pc._cache()


def test_pace_blocks_once_the_configured_quota_is_reached(_isolate, monkeypatch):
    clock = {"t": 0.0}
    sleeps: list[float] = []
    monkeypatch.setattr(pc.time, "monotonic", lambda: clock["t"])

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    monkeypatch.setattr(pc.time, "sleep", fake_sleep)
    monkeypatch.setattr(
        pc.billing_guardrails, "gcp_quota_per_minute", lambda *a, **k: 2
    )
    pc._rate_windows.clear()

    pc._pace("SearchTextRequestPerMinutePerProject", default=30)
    pc._pace("SearchTextRequestPerMinutePerProject", default=30)
    assert not sleeps  # first two calls fit the quota of 2/minute immediately

    pc._pace("SearchTextRequestPerMinutePerProject", default=30)
    assert sleeps  # third call within the same window had to wait


def test_pace_abandons_a_wait_immediately_once_shutdown_begins(_isolate, monkeypatch):
    """Regression: a worker thread blocked here previously held up process
    exit for as long as its remaining quota wait -- concurrent.futures.thread
    joins every ThreadPoolExecutor worker at interpreter exit with no
    timeout, and pacing correctness deliberately makes that wait minutes,
    not milliseconds, on a large trip. api.py's shutdown event now calls
    begin_shutdown() so a worker still waiting here bails out at once."""
    clock = {"t": 0.0}
    sleeps: list[float] = []
    monkeypatch.setattr(pc.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(pc.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(pc.billing_guardrails, "gcp_quota_per_minute", lambda *a, **k: 1)
    pc._rate_windows.clear()

    pc._pace("SearchTextRequestPerMinutePerProject", default=30)  # uses up the only slot

    pc.begin_shutdown()
    pc._pace("SearchTextRequestPerMinutePerProject", default=30)

    assert not sleeps  # returned immediately instead of waiting out the window
    # _shutting_down is a process-wide Event, not test-scoped state -- clear it
    # so later tests in this module don't inherit a "shutting down" process.
    pc._shutting_down.clear()


def test_pace_reports_a_wait_that_crosses_the_visibility_threshold(_isolate, monkeypatch):
    """Regression: a quota-exhausted burst previously made _pace() block
    silently for tens of seconds with zero console/log output, which made a
    throttled trip switch look identical to the app being stuck. A wait that
    crosses _PACE_LOG_THRESHOLD_MS must now surface one app_event."""
    clock = {"t": 0.0}
    monkeypatch.setattr(pc.time, "monotonic", lambda: clock["t"])

    def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    monkeypatch.setattr(pc.time, "sleep", fake_sleep)
    monkeypatch.setattr(pc.billing_guardrails, "gcp_quota_per_minute", lambda *a, **k: 1)
    pc._rate_windows.clear()
    # A prior test in this module (test_pace_abandons_a_wait_immediately_once_
    # shutdown_begins) sets this process-wide Event and never clears it.
    pc._shutting_down.clear()

    events: list[tuple[str, dict]] = []
    from tripplanner import observability

    monkeypatch.setattr(
        observability, "app_event", lambda kind, **fields: events.append((kind, fields))
    )

    pc._pace("SearchTextRequestPerMinutePerProject", default=30)  # uses up the only slot
    pc._pace("SearchTextRequestPerMinutePerProject", default=30)  # waits out the full window

    assert len(events) == 1
    kind, fields = events[0]
    assert kind == "provider_pacing"
    assert fields["quota_id"] == "SearchTextRequestPerMinutePerProject"
    assert fields["ms"] >= pc._PACE_LOG_THRESHOLD_MS


def test_pace_stays_quiet_for_a_short_wait(_isolate, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(pc.time, "monotonic", lambda: clock["t"])

    def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    monkeypatch.setattr(pc.time, "sleep", fake_sleep)
    # Window resets almost immediately, so any wait stays well under the
    # visibility threshold.
    monkeypatch.setattr(pc, "_RATE_WINDOW_SEC", 0.05)
    monkeypatch.setattr(pc.billing_guardrails, "gcp_quota_per_minute", lambda *a, **k: 1)
    pc._rate_windows.clear()
    pc._shutting_down.clear()

    events: list[tuple[str, dict]] = []
    from tripplanner import observability

    monkeypatch.setattr(
        observability, "app_event", lambda kind, **fields: events.append((kind, fields))
    )

    pc._pace("SearchTextRequestPerMinutePerProject", default=30)
    pc._pace("SearchTextRequestPerMinutePerProject", default=30)

    assert not events


def test_pace_reads_the_real_environment_quota(_isolate, monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    pc.billing_guardrails.reset_cache_for_tests()
    limit = pc.billing_guardrails.gcp_quota_per_minute(
        "places.googleapis.com", "SearchTextRequestPerMinutePerProject", default=999
    )
    # canary's configured per-minute text-search quota, from
    # infra/billing-guardrails.json -- not the fallback default.
    assert limit != 999


def test_places_executor_paths_preserve_usage_attribution(_isolate, monkeypatch):
    from tripplanner.usage_attribution import current_attribution, usage_scope

    observed = []
    monkeypatch.setattr(pc, "_photo_uris", _REAL_PHOTO_URIS)
    monkeypatch.setattr(
        pc,
        "_photo_uri",
        lambda ref, _width=800: (
            observed.append(current_attribution().interaction_id) or f"https://photos/{ref}"
        ),
    )
    monkeypatch.setattr(
        pc,
        "get_summary",
        lambda *_args, **_kwargs: observed.append(current_attribution().interaction_id),
    )
    monkeypatch.setattr(pc, "get_photos", lambda *_args, **_kwargs: [])

    with usage_scope("user_trip", interaction_id="turn-parallel"):
        assert len(pc._photo_uris(["one", "two"])) == 2
        pc.prefetch(["A", "B"], "Goa", max_photos=0)

    assert observed == ["turn-parallel"] * 4


def test_incomplete_lookup_is_not_cached_and_retries_immediately(_isolate, monkeypatch):
    """A lookup that never got an answer must not be remembered as one.

    Caching it would state a fact nobody established; the next request should
    simply try again rather than wait out a TTL.
    """
    calls = {"count": 0}

    def flaky_lookup(name: str, city: str):
        calls["count"] += 1
        if calls["count"] == 1:
            raise pc.PlaceLookupUnavailableError("network went away")
        return {
            "place_id": "fort-aguada",
            "name": name,
            "lat": 15.49,
            "lng": 73.77,
            "photo_refs": [],
        }

    monkeypatch.setattr(pc, "_lookup_place", flaky_lookup)

    assert pc.get_details("Fort Aguada", "Goa") is None
    assert pc._key("Fort Aguada", "Goa") not in pc._CACHE

    details = pc.get_details("Fort Aguada", "Goa")
    assert details and details["place_id"] == "fort-aguada"
    assert calls["count"] == 2


def test_absent_place_is_remembered_and_never_re_searched(_isolate, monkeypatch):
    """"Google has no such place" is knowledge, and keeps the metadata TTL.

    Itinerary stops like "Hotel TBD, Srinagar" used to be re-searched every
    sixty seconds for the life of the trip because an absent place and a failed
    lookup were stored identically.
    """
    calls = {"count": 0}

    def absent_lookup(name: str, city: str):
        calls["count"] += 1
        return None

    monkeypatch.setattr(pc, "_lookup_place", absent_lookup)

    assert pc.get_details("Nowhere At All", "Goa") is None
    assert pc.get_details("Nowhere At All", "Goa") is None
    assert calls["count"] == 1

    entry = pc._CACHE[pc._key("Nowhere At All", "Goa")]
    assert pc._is_absent(entry)

    # Well past the short retry window that used to apply here.
    entry["__at__"] = time.time() - pc._MISS_TTL_S - 1
    assert pc.get_details("Nowhere At All", "Goa") is None
    assert calls["count"] == 1


def test_names_that_cannot_be_places_are_never_looked_up(_isolate, monkeypatch):
    """An activity or a gap is not somewhere to search for."""
    monkeypatch.setattr(
        pc, "_lookup_place", lambda *_a, **_k: pytest.fail("should not reach a paid lookup")
    )

    for name in (
        "Drive: Srinagar to Gulmarg",
        "Hotel TBD, Srinagar",
        "Pahalgam hotel check-in",
        "Srinagar Airport to Hotel transfer",
        "Free time",
    ):
        assert pc.get_details(name, "Kashmir") is None

    # Real places still resolve.
    assert pc.is_lookupable_place_name("Gulmarg Gondola")
    assert pc.is_lookupable_place_name("The Troutbeat / Pahalgam lunch")


def test_lookup_retries_one_transient_server_error(_isolate, _authorized, monkeypatch):
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


def test_lookup_does_not_retry_client_error(_isolate, _authorized, monkeypatch):
    request = httpx.Request("POST", "https://places.googleapis.com/v1/places:searchText")
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return httpx.Response(400, request=request)

    monkeypatch.setattr(pc.http_client, "post", fake_post)

    # A client error is an incomplete lookup, not "no such place".
    with pytest.raises(pc.PlaceLookupUnavailableError):
        _REAL_LOOKUP_PLACE("Missing Place", "Goa")
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
    entry["__photos_at__"] = time.time() - pc._ttl(pc._PHOTO_TTL_S) - 1
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 2  # re-signed, but no new lookup
    assert _isolate["lookup"] == 1


def test_photo_urls_survive_179_days(_isolate, monkeypatch):
    monkeypatch.setattr(pc.get_settings(), "google_places_photo_url_cache_ttl_sec", 15552000)
    monkeypatch.setattr(pc.get_settings(), "cache_ttl_scale", 1)
    pc.get_photos("Taj", "Goa")
    entry = pc._CACHE[pc._key("Taj", "Goa")]
    entry["__photos_at__"] = time.time() - 179 * 24 * 60 * 60
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 1
    entry["__photos_at__"] = time.time() - 181 * 24 * 60 * 60
    pc.get_photos("Taj", "Goa")
    assert _isolate["photos"] == 2


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


def test_top_places_cached_and_refreshable(_isolate, _authorized, monkeypatch):
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
        # Same as prefetch() does: a worker thread inherits no context variables,
        # so each context is copied here, on the calling thread, and carries the
        # caller's paid-provider authorization into the worker.
        futures = [
            executor.submit(contextvars.copy_context().run, pc.get_summary, name, "Goa")
            for name in names
        ]
        summaries = [future.result() for future in futures]

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


def test_primary_miss_serves_and_promotes_fresh_secondary(_isolate, monkeypatch):
    from tripplanner import secondary_cache

    primary: dict = {}
    _fake_cosmos(monkeypatch, primary)
    key = pc._key("Taj", "Goa")
    observed_at = time.time() - 10
    secondary_entry = {
        "place_id": "central-taj",
        "name": "Taj",
        "lat": 15.0,
        "lng": 73.0,
        "__at__": observed_at,
    }
    monkeypatch.setattr(
        secondary_cache,
        "read_doc",
        lambda container, doc_id: {"key": key, "entry": secondary_entry},
    )

    result = pc.get_details("Taj", "Goa")

    assert result and result["place_id"] == "central-taj"
    assert result["__at__"] == observed_at
    assert _isolate["lookup"] == 0
    assert pc.flush_writes()
    assert primary[pc._doc_id(key)]["entry"]["__at__"] == observed_at


def test_provider_result_writes_secondary_best_effort(_isolate, monkeypatch):
    from tripplanner import secondary_cache

    primary: dict = {}
    _fake_cosmos(monkeypatch, primary)
    writes: list[tuple[str, str, dict]] = []

    def capture_secondary(container: str, doc_id: str, body: dict) -> bool:
        assert doc_id in primary
        writes.append((container, doc_id, body))
        return False

    monkeypatch.setattr(
        secondary_cache,
        "merge_write",
        capture_secondary,
    )

    result = pc.get_details("Taj", "Goa")

    assert result and result["place_id"] == "id-Taj"
    assert pc.flush_writes()
    assert writes[0][0] == "places_cache"
    assert writes[0][2]["entry"]["place_id"] == "id-Taj"


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
        futures = [
            executor.submit(contextvars.copy_context().run, pc.get_details, "Taj", "Goa")
            for _ in range(8)
        ]
        summaries = [future.result() for future in futures]

    assert all(summary and summary["place_id"] == "id-Taj" for summary in summaries)
    assert _isolate["lookup"] == 1


def test_an_entry_without_coordinates_expires_like_a_miss() -> None:
    """A half-worked lookup is not a fact about a place."""
    minutes_old = time.time() - (pc._MISS_TTL_S + 5)
    no_coords = {"name": "Musee d'Orsay", "place_id": "x", "__at__": minutes_old}
    assert not pc._fresh(no_coords)

    located = {**no_coords, "lat": 48.86, "lng": 2.32}
    assert pc._fresh(located)


def test_read_only_caller_serves_the_cache_and_never_looks_up(_isolate):
    """The reload case: a finished trip is rendered without buying anything."""
    pc.get_details("Taj", "Goa")
    assert _isolate["lookup"] == 1

    with _read_only():
        again = pc.get_details("Taj", "Goa")

    assert again and again["place_id"] == "id-Taj"
    assert _isolate["lookup"] == 1


def test_read_only_caller_never_looks_up_an_unknown_place(_isolate):
    with _read_only():
        assert pc.get_details("Never Seen", "Goa") is None

    assert _isolate["lookup"] == 0
    assert pc._key("Never Seen", "Goa") not in pc._CACHE  # nothing invented


def test_read_only_caller_serves_a_lapsed_entry_rather_than_nothing(_isolate):
    """A lapsed TTL means "re-check when someone is paying", not "forget it".

    Half-resolved entries (no coordinates) lapse after a minute, so a read-only
    view that dropped them would lose a rating and a photo it already owns.
    """
    key = pc._key("Half Known", "Goa")
    pc._CACHE[key] = {
        "place_id": "half-id",
        "name": "Half Known",
        "rating": 4.2,
        "__at__": time.time() - pc._MISS_TTL_S - 5,
    }

    with _read_only():
        served = pc.get_details("Half Known", "Goa")

    assert served and served["rating"] == 4.2
    assert _isolate["lookup"] == 0


def test_read_only_caller_records_its_decision_without_a_provider_event(_isolate):
    with harness_scope("cache", run_id="read-only-run"):
        with EvidenceCollector("read-only-run", "cache") as collector:
            with _read_only():
                pc.get_details("Unknown Place", "Goa")

    results = [
        event.fields["result"]
        for event in collector.evidence.events
        if event.kind == "cache_access"
    ]
    assert results == ["read_only_miss"]


def test_photo_urls_are_not_stamped_when_resolution_is_declined(_isolate, monkeypatch):
    """Recording "no photos" for a call that never happened hid the place's
    photo for the whole 180-day photo TTL."""
    pc.get_photos("Taj", "Goa")
    key = pc._key("Taj", "Goa")
    before = pc._CACHE[key]["photo_urls"]
    assert before

    monkeypatch.setattr(pc, "_photo_uris", lambda *_args, **_kwargs: [])
    with pc._CACHE_LOCK:
        pc._CACHE[key]["__photos_at__"] = 0.0  # force a re-resolve

    photos = pc.get_photos("Taj", "Goa")

    assert photos == before
    assert pc._CACHE[key]["photo_urls"] == before


def test_absent_reviews_are_not_cached_when_the_fetch_fails(_isolate, monkeypatch):
    monkeypatch.setattr(pc, "_fetch_reviews", lambda _place_id: None)

    summary = pc.get_summary("Taj", "Goa")

    assert summary is not None
    assert "reviews" not in pc._CACHE[pc._key("Taj", "Goa")]


def test_top_places_read_only_serves_cached_names(_isolate, monkeypatch):
    posts: list[str] = []

    def fake_post(url, **kwargs):
        posts.append(url)
        return httpx.Response(
            200,
            json={"places": [{"displayName": {"text": "Hotel A"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(pc.http_client, "post", fake_post)

    assert pc.top_places("Goa", "hotel") == ["Hotel A"]
    with _read_only():
        assert pc.top_places("Goa", "hotel") == ["Hotel A"]
        assert pc.top_places("Kerala", "hotel") == []

    assert len(posts) == 1


def test_top_places_does_not_cache_a_failed_lookup(_isolate, monkeypatch):
    """Caching the empty list recorded "this destination has no hotels"."""
    attempts: list[str] = []

    def failing_post(url, **kwargs):
        attempts.append(url)
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(pc.http_client, "post", failing_post)

    assert pc.top_places("Goa", "hotel") == []
    assert pc.top_places("Goa", "hotel") == []

    assert len(attempts) == 2  # retried, not remembered as an answer
