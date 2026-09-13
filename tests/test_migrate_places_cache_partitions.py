"""Moving places_cache rows from the legacy ``_shared`` partition into their buckets."""

from __future__ import annotations

import scripts.migrate_places_cache_partitions as migration
from tripplanner import place_cache_layout as layout


class _CosmosError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"Cosmos status {status_code}")
        self.status_code = status_code


class FakeContainer:
    """Items keyed by (partition, id) with ETags, like a Cosmos container."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}
        self._version = 0
        self.writes = 0

    def put(self, partition: str, body: dict) -> dict:
        self._version += 1
        stored = {**body, "user_id": partition, "_etag": f"v{self._version}"}
        self.items[(partition, body["id"])] = stored
        return stored

    def query_items(self, *, query, parameters, partition_key, response_hook):
        return [
            dict(item)
            for (partition, _item_id), item in list(self.items.items())
            if partition == partition_key
        ]

    def read_item(self, *, item, partition_key, response_hook=None):
        found = self.items.get((partition_key, item))
        if found is None:
            raise _CosmosError(404)
        return dict(found)

    def create_item(self, *, body, response_hook=None):
        if (body["user_id"], body["id"]) in self.items:
            raise _CosmosError(409)
        self.writes += 1
        self.put(body["user_id"], body)

    def replace_item(self, *, item, body, etag, match_condition, response_hook=None):
        if self.items[(body["user_id"], item)]["_etag"] != etag:
            raise _CosmosError(412)
        self.writes += 1
        self.put(body["user_id"], body)

    def delete_item(self, *, item, partition_key, etag, match_condition, response_hook=None):
        current = self.items.get((partition_key, item))
        if current is None:
            raise _CosmosError(404)
        if current["_etag"] != etag:
            raise _CosmosError(412)
        del self.items[(partition_key, item)]


def _place(item_id: str, **entry) -> dict:
    return {"id": item_id, "key": f"{item_id}|goa", "entry": entry}


def test_dry_run_reports_without_writing():
    container = FakeContainer()
    container.put(layout.LEGACY_PARTITION, _place("ab01", name="Taj", __at__=10.0))

    report = migration.migrate(container, apply=False)

    assert report.legacy_rows == 1 and report.created == 1
    assert container.writes == 0
    assert (layout.LEGACY_PARTITION, "ab01") in container.items


def test_legacy_row_moves_to_its_bucket_keeping_stable_forever_ttl():
    container = FakeContainer()
    container.put(layout.LEGACY_PARTITION, {**_place("ab01", name="Taj", __at__=10.0), "ttl": -1})

    report = migration.migrate(container, apply=True)

    assert report.as_dict()["status"] == "passed"
    assert report.created == 1 and report.deleted_legacy == 1
    moved = container.items[(layout.partition("ab01"), "ab01")]
    assert moved["entry"] == {"name": "Taj", "__at__": 10.0}
    assert moved["ttl"] == -1
    assert moved["key"] == "ab01|goa"
    assert (layout.LEGACY_PARTITION, "ab01") not in container.items


def test_already_rehomed_place_merges_each_field_by_its_own_timestamp():
    container = FakeContainer()
    container.put(
        layout.LEGACY_PARTITION,
        _place("ab01", name="old", __at__=10.0, reviews=["legacy review"], __reviews_at__=50.0),
    )
    container.put(layout.partition("ab01"), _place("ab01", name="new", __at__=20.0))

    report = migration.migrate(container, apply=True)

    assert report.merged == 1 and report.deleted_legacy == 1
    entry = container.items[(layout.partition("ab01"), "ab01")]["entry"]
    assert entry["name"] == "new"
    assert entry["reviews"] == ["legacy review"]


def test_legacy_row_rewritten_mid_run_is_left_for_the_next_run():
    container = FakeContainer()
    container.put(layout.LEGACY_PARTITION, _place("ab01", name="Taj", __at__=10.0))
    real_create = container.create_item

    def create_then_older_revision_rewrites_legacy(*, body, response_hook=None):
        real_create(body=body, response_hook=response_hook)
        container.put(layout.LEGACY_PARTITION, _place("ab01", name="Taj v2", __at__=30.0))

    container.create_item = create_then_older_revision_rewrites_legacy

    report = migration.migrate(container, apply=True)

    assert report.skipped_changed == 1 and report.deleted_legacy == 0
    assert container.items[(layout.LEGACY_PARTITION, "ab01")]["entry"]["name"] == "Taj v2"


def test_rerun_after_success_finds_nothing():
    container = FakeContainer()
    container.put(layout.LEGACY_PARTITION, _place("ab01", name="Taj", __at__=10.0))
    migration.migrate(container, apply=True)

    report = migration.migrate(container, apply=True)

    assert report.legacy_rows == 0 and container.writes == 1


def test_pre_sharding_monolithic_document_is_deleted_not_bucketed():
    container = FakeContainer()
    container.put(layout.LEGACY_PARTITION, {"id": "cache", "entries": {}})

    report = migration.migrate(container, apply=True)

    assert report.monolithic_documents == 1
    assert container.items == {}


def test_partition_is_a_stable_bucket_of_the_id():
    item_id = layout.doc_id("taj|goa")
    assert layout.partition(item_id) == layout.partition(item_id.upper())
    assert layout.partition(item_id) == f"place-{item_id[:2]}"
    assert layout.is_place_partition(layout.partition(item_id))
    assert not layout.is_place_partition(layout.LEGACY_PARTITION)
    buckets = {layout.partition(layout.doc_id(f"place {index}|goa")) for index in range(5000)}
    assert len(buckets) == layout.BUCKETS
