from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import scripts.prod_cache_sync as cache_sync
from scripts.prod_cache_sync import (
    PLACES_CONTAINER,
    TOOLS_CONTAINER,
    ActivityMetrics,
    CachePolicy,
    CacheRecord,
    PlannedWrite,
    Snapshot,
    _verify_write,
    merge_place_documents,
    plan_direction,
    prepare_for_destination,
)


def _policy(**values: str) -> CachePolicy:
    return CachePolicy(
        {
            "CACHE_TTL_SCALE": "1",
            "CACHE_STABLE_FOREVER": "0",
            "CACHE_VOLATILE_FOREVER": "0",
            "CACHE_WARM_EVERYTHING": "1",
            **values,
        }
    )


def test_place_merge_keeps_newest_metadata_reviews_and_photos_independently():
    local = CacheRecord(
        body={
            "id": "p1",
            "user_id": "_shared",
            "entry": {
                "name": "new metadata",
                "__at__": 30,
                "reviews": ["old reviews"],
                "__reviews_at__": 10,
                "photo_urls": ["new photo"],
                "__photos_at__": 40,
            },
        }
    )
    prod = CacheRecord(
        body={
            "id": "p1",
            "user_id": "_shared",
            "entry": {
                "name": "old metadata",
                "__at__": 20,
                "reviews": ["new reviews"],
                "__reviews_at__": 50,
                "photo_urls": ["old photo"],
                "__photos_at__": 5,
            },
        }
    )

    merged = merge_place_documents(local, prod).body["entry"]

    assert merged["name"] == "new metadata"
    assert merged["reviews"] == ["new reviews"]
    assert merged["photo_urls"] == ["new photo"]


def test_tool_legacy_cosmos_timestamp_becomes_stable_cached_at():
    record = CacheRecord(
        body={"id": "web_search-abc", "user_id": "_global_", "result": "value"},
        source_ts=100,
    )

    prepared = prepare_for_destination(
        TOOLS_CONTAINER,
        record,
        _policy(CACHE_VOLATILE_FOREVER="1"),
        now=200,
    )

    assert prepared and prepared["cached_at"] == 100
    assert prepared["expires_at"] == -1
    assert prepared["ttl"] == -1


def test_expired_entries_are_skipped_instead_of_rejuvenated():
    source = {
        "p1": CacheRecord(
            body={
                "id": "p1",
                "user_id": "_shared",
                "entry": {"name": "old", "__at__": 10},
            }
        )
    }
    policy = _policy(GOOGLE_PLACES_METADATA_CACHE_TTL_SEC="20")

    writes, stale = plan_direction(PLACES_CONTAINER, source, {}, policy, now=31)

    assert writes == []
    assert stale == 1


def test_plan_is_merge_only_and_writes_only_changed_rows():
    older = CacheRecord(
        body={
            "id": "p1",
            "user_id": "_shared",
            "entry": {"name": "old", "__at__": 10},
            "ttl": -1,
        },
        etag="etag-old",
    )
    newer = CacheRecord(
        body={
            "id": "p1",
            "user_id": "_shared",
            "entry": {"name": "new", "__at__": 20},
            "ttl": -1,
        }
    )
    untouched = CacheRecord(
        body={
            "id": "only-target",
            "user_id": "_shared",
            "entry": {"name": "target only", "__at__": 15},
            "ttl": -1,
        }
    )

    writes, stale = plan_direction(
        PLACES_CONTAINER,
        {"p1": newer},
        {"p1": older, "only-target": untouched},
        _policy(CACHE_STABLE_FOREVER="1"),
        now=100,
    )

    assert stale == 0
    assert len(writes) == 1
    assert writes[0].item_id == "p1"
    assert writes[0].etag == "etag-old"
    assert writes[0].body["entry"]["name"] == "new"


def test_tool_entry_uses_destination_ttl_without_refreshing_observation_time():
    record = CacheRecord(
        body={
            "id": "get_place_reviews-abc",
            "user_id": "_global_",
            "result": "value",
            "cached_at": 100,
            "expires_at": -1,
            "ttl": -1,
        }
    )

    prepared = prepare_for_destination(
        TOOLS_CONTAINER,
        record,
        _policy(GOOGLE_PLACES_REVIEWS_CACHE_TTL_SEC="300"),
        now=200,
    )

    assert prepared and prepared["cached_at"] == 100
    assert prepared["expires_at"] == 400
    assert "ttl" not in prepared


def test_write_verification_ignores_cosmos_system_fields():
    planned = PlannedWrite(
        container="places_cache",
        partition="_shared",
        item_id="p1",
        body={"entry": {"name": "Place", "__at__": 10}, "ttl": -1},
    )

    class Container:
        def read_item(self, *, item, partition_key, response_hook):
            assert (item, partition_key) == ("p1", "_shared")
            response_hook({"x-ms-request-charge": "1.25"}, None)
            return {
                "id": "p1",
                "user_id": "_shared",
                "entry": {"name": "Place", "__at__": 10},
                "ttl": -1,
                "_etag": "etag",
                "_ts": 20,
            }

    metrics = _verify_write(Container(), planned)

    assert metrics.request_units == 1.25
    assert metrics.requests == 1
    assert metrics.payload_bytes > 0


def test_write_verification_accepts_cosmos_float_round_trip_drift():
    planned = PlannedWrite(
        container="places_cache",
        partition="_shared",
        item_id="p1",
        body={"entry": {"lng": 12.471670699999999}},
    )

    class Container:
        def read_item(self, *, item, partition_key, response_hook):
            return {
                "id": item,
                "user_id": partition_key,
                "entry": {"lng": 12.4716707},
            }

    _verify_write(Container(), planned)


def test_write_verification_rejects_meaningful_float_change():
    planned = PlannedWrite(
        container="places_cache",
        partition="_shared",
        item_id="p1",
        body={"entry": {"lng": 12.4716707}},
    )

    class Container:
        def read_item(self, *, item, partition_key, response_hook):
            return {
                "id": item,
                "user_id": partition_key,
                "entry": {"lng": 12.4717707},
            }

    with pytest.raises(RuntimeError, match="Verification failed"):
        _verify_write(Container(), planned)


def _sync_args(tmp_path, checkpoint):
    config = tmp_path / "cache.env"
    config.write_text(
        "CACHE_WARM_EVERYTHING=0\nCACHE_STABLE_FOREVER=1\n",
        encoding="utf-8",
    )
    return SimpleNamespace(
        apply=True,
        checkpoint=str(checkpoint),
        direction="push",
        full_scan=False,
        local_config=str(config),
        local_database="tripplanner-cache",
        prod_config=str(config),
        prod_endpoint="https://example.documents.azure.com:443/",
        watermark_overlap_seconds=300,
    )


def _seed_checkpoint(path, args, watermark=100):
    checkpoint = cache_sync._empty_checkpoint(args)
    checkpoint["sources"]["local"][PLACES_CONTAINER] = watermark
    cache_sync._save_checkpoint(path, checkpoint)


def _stub_sync_databases(monkeypatch):
    class Database:
        def get_container_client(self, _name):
            return object()

    local = Database()
    production = Database()

    class ProductionClient:
        def get_database_client(self, _name):
            return production

    monkeypatch.setattr(cache_sync, "_local_client", lambda: object())
    monkeypatch.setattr(cache_sync, "_local_database", lambda _client, _name: local)
    monkeypatch.setattr(cache_sync, "_production_client", lambda _endpoint: ProductionClient())
    return local, production


def _stub_incremental_scan(monkeypatch, expected_watermark=100):
    source = {
        item_id: CacheRecord(
            body={
                "id": item_id,
                "user_id": "_shared",
                "entry": {"name": item_id, "__at__": 150},
                "ttl": -1,
            },
            source_ts=200,
        )
        for item_id in ("p1", "p2")
    }

    def changed_snapshot(
        _source_database,
        _target_database,
        _container,
        watermark,
        overlap_seconds,
    ):
        assert watermark == expected_watermark
        assert overlap_seconds == 300
        return (
            Snapshot(source, 200, 0, False, ActivityMetrics()),
            {},
            ActivityMetrics(),
            ActivityMetrics(),
        )

    monkeypatch.setattr(cache_sync, "_changed_snapshot", changed_snapshot)


def test_partial_failure_keeps_checkpoint_and_reports_completed_delta(
    tmp_path, monkeypatch
):
    checkpoint_path = tmp_path / "checkpoint.json"
    args = _sync_args(tmp_path, checkpoint_path)
    _seed_checkpoint(checkpoint_path, args)
    checkpoint_before = checkpoint_path.read_bytes()
    _stub_sync_databases(monkeypatch)
    _stub_incremental_scan(monkeypatch)
    calls = 0

    def fail_second_write(_container, planned, metrics):
        nonlocal calls
        calls += 1
        metrics.requests += 1
        metrics.request_units += 2
        metrics.add_payload(planned.body)
        if calls == 2:
            raise RuntimeError("interrupted")
        return "inserted", metrics

    def verify(_container, _planned, metrics):
        metrics.requests += 1
        metrics.request_units += 1
        return metrics

    monkeypatch.setattr(cache_sync, "_write", fail_second_write)
    monkeypatch.setattr(cache_sync, "_verify_write", verify)

    report = cache_sync.synchronize(args)

    activity = report["containers"][PLACES_CONTAINER]["local_to_production"]
    assert report["status"] == "failed"
    assert report["written"] == 1
    assert report["checkpoint"]["advanced"] is False
    assert report["checkpoint"]["reason"] == "run_failed"
    assert checkpoint_path.read_bytes() == checkpoint_before
    assert [item["status"] for item in activity["delta_activity"]] == [
        "verified",
        "failed",
    ]
    assert activity["write_metrics"]["request_units"] == 4
    assert activity["verification_metrics"]["request_units"] == 1


def test_successful_incremental_run_advances_checkpoint(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    args = _sync_args(tmp_path, checkpoint_path)
    _seed_checkpoint(checkpoint_path, args)
    _stub_sync_databases(monkeypatch)
    _stub_incremental_scan(monkeypatch)

    def write(_container, planned, metrics):
        metrics.requests += 1
        metrics.add_payload(planned.body)
        return "inserted", metrics

    monkeypatch.setattr(cache_sync, "_write", write)
    monkeypatch.setattr(
        cache_sync,
        "_verify_write",
        lambda _container, _planned, metrics: metrics,
    )

    report = cache_sync.synchronize(args)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert report["checkpoint"]["advanced"] is True
    assert checkpoint["sources"]["local"][PLACES_CONTAINER] == 200


def test_etag_conflict_keeps_checkpoint_for_conservative_retry(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    args = _sync_args(tmp_path, checkpoint_path)
    _seed_checkpoint(checkpoint_path, args)
    checkpoint_before = checkpoint_path.read_bytes()
    _stub_sync_databases(monkeypatch)
    _stub_incremental_scan(monkeypatch)

    class ConflictError(RuntimeError):
        status_code = 412

    monkeypatch.setattr(
        cache_sync,
        "_write",
        lambda _container, _planned, _metrics: (_ for _ in ()).throw(
            ConflictError("changed concurrently")
        ),
    )

    report = cache_sync.synchronize(args)

    activity = report["containers"][PLACES_CONTAINER]["local_to_production"]
    assert report["status"] == "partial"
    assert report["conflicts"] == 2
    assert report["checkpoint"]["advanced"] is False
    assert report["checkpoint"]["reason"] == "conflicts_detected"
    assert checkpoint_path.read_bytes() == checkpoint_before
    assert [item["status"] for item in activity["delta_activity"]] == [
        "conflict",
        "conflict",
    ]


def test_cache_policy_change_invalidates_checkpoint(tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    args = _sync_args(tmp_path, checkpoint_path)
    _seed_checkpoint(checkpoint_path, args)
    policy_path = tmp_path / "cache.env"
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8") + "CACHE_TTL_SCALE=2\n",
        encoding="utf-8",
    )

    checkpoint, state = cache_sync._load_checkpoint(checkpoint_path, args)

    assert state == "scope_mismatch"
    assert checkpoint["sources"] == {"local": {}, "production": {}}
