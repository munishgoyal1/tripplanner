from __future__ import annotations

from scripts.prod_cache_sync import (
    PLACES_CONTAINER,
    TOOLS_CONTAINER,
    CachePolicy,
    CacheRecord,
    PlannedWrite,
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
        def read_item(self, *, item, partition_key):
            assert (item, partition_key) == ("p1", "_shared")
            return {
                "id": "p1",
                "user_id": "_shared",
                "entry": {"name": "Place", "__at__": 10},
                "ttl": -1,
                "_etag": "etag",
                "_ts": 20,
            }

    _verify_write(Container(), planned)
