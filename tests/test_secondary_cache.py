"""Tests for the optional shared secondary durable cache."""

from __future__ import annotations

import time

import pytest

from tripplanner import secondary_cache
from tripplanner.config import get_settings


class _CosmosError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"Cosmos status {status_code}")
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _reset_secondary_cache():
    secondary_cache.reset_client_for_tests()
    yield
    secondary_cache.reset_client_for_tests()


def test_disabled_cache_never_opens_a_connection(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "secondary_durable_cache_enabled", False)
    monkeypatch.setattr(
        secondary_cache,
        "_container",
        lambda _name: pytest.fail("disabled cache attempted a connection"),
    )

    assert secondary_cache.read_doc("places_cache", "place") is None
    assert not secondary_cache.merge_write("tool_cache", "tool", {"result": "x"})


def test_cache_boundary_rejects_application_containers():
    with pytest.raises(ValueError, match="unsupported shared cache container"):
        secondary_cache._container("trips")


def test_primary_key_fallback_requires_the_same_loopback_emulator(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "cosmos_key", "primary-key")
    monkeypatch.setattr(settings, "cosmos_endpoint", "https://localhost:8081")
    monkeypatch.setattr(settings, "cosmos_emulator", True)
    monkeypatch.setattr(
        settings, "secondary_durable_cache_endpoint", "https://localhost:8081"
    )
    monkeypatch.setattr(settings, "secondary_durable_cache_emulator", True)

    assert secondary_cache._shared_emulator_key() == "primary-key"

    monkeypatch.setattr(settings, "cosmos_endpoint", "https://account.documents.azure.com")
    monkeypatch.setattr(settings, "cosmos_emulator", False)

    assert secondary_cache._shared_emulator_key() == ""


def test_read_failure_opens_circuit_and_fails_open(monkeypatch):
    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(
        secondary_cache,
        "_container",
        lambda _name: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert secondary_cache.read_doc("places_cache", "place") is None
    assert secondary_cache._disabled_until > time.monotonic()


def test_place_write_merges_independent_evidence_with_etag(monkeypatch):
    current = {
        "id": "place",
        "user_id": "_shared",
        "_etag": "version-1",
        "key": "taj|goa",
        "entry": {
            "name": "new metadata",
            "__at__": 200.0,
            "reviews": ["old review"],
            "__reviews_at__": 100.0,
        },
    }
    incoming = {
        "key": "taj|goa",
        "entry": {
            "name": "old metadata",
            "__at__": 100.0,
            "reviews": ["new review"],
            "__reviews_at__": 300.0,
        },
    }
    replaced: list[dict] = []

    class FakeContainer:
        def read_item(self, **_kwargs):
            return current

        def replace_item(self, **kwargs):
            replaced.append(kwargs)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.merge_write("places_cache", "place", incoming)
    assert replaced[0]["etag"] == "version-1"
    merged = replaced[0]["body"]["entry"]
    assert merged["name"] == "new metadata"
    assert merged["reviews"] == ["new review"]
    assert merged["__at__"] == 200.0
    assert merged["__reviews_at__"] == 300.0


def test_tool_write_keeps_newer_cached_result(monkeypatch):
    current = {
        "id": "tool",
        "user_id": "_global_",
        "_etag": "version-1",
        "result": "newer",
        "cached_at": 200.0,
        "expires_at": -1,
    }
    replaced: list[dict] = []

    class FakeContainer:
        def read_item(self, **_kwargs):
            return current

        def replace_item(self, **kwargs):
            replaced.append(kwargs)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.merge_write(
        "tool_cache",
        "tool",
        {"result": "older", "cached_at": 100.0, "expires_at": -1},
    )
    assert replaced[0]["body"]["result"] == "newer"
    assert replaced[0]["body"]["cached_at"] == 200.0


def test_etag_conflict_rereads_and_merges_concurrent_place_evidence(monkeypatch):
    versions = iter(
        [
            {
                "_etag": "v1",
                "entry": {"name": "current", "__at__": 200.0},
            },
            {
                "_etag": "v2",
                "entry": {
                    "name": "current",
                    "__at__": 200.0,
                    "photo_urls": ["new-photo"],
                    "__photos_at__": 300.0,
                },
            },
        ]
    )
    replaced: list[dict] = []

    class FakeContainer:
        def read_item(self, **_kwargs):
            return next(versions)

        def replace_item(self, **kwargs):
            replaced.append(kwargs)
            if len(replaced) == 1:
                raise _CosmosError(412)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.merge_write(
        "places_cache",
        "place",
        {
            "entry": {
                "name": "older",
                "__at__": 100.0,
                "reviews": ["new-review"],
                "__reviews_at__": 400.0,
            }
        },
    )
    merged = replaced[1]["body"]["entry"]
    assert replaced[1]["etag"] == "v2"
    assert merged["name"] == "current"
    assert merged["photo_urls"] == ["new-photo"]
    assert merged["reviews"] == ["new-review"]


def test_place_read_falls_back_to_legacy_shared_partition(monkeypatch):
    from tripplanner import place_cache_layout

    reads: list[str] = []

    class FakeContainer:
        def read_item(self, *, item, partition_key):
            reads.append(partition_key)
            if partition_key == place_cache_layout.LEGACY_PARTITION:
                return {"id": item, "user_id": partition_key, "entry": {"name": "legacy"}}
            raise _CosmosError(404)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.read_doc("places_cache", "ab12") == {"entry": {"name": "legacy"}}
    assert reads == [place_cache_layout.partition("ab12"), "_shared"]


def test_first_bucketed_write_merges_the_legacy_copy(monkeypatch):
    """Re-homing a place must not drop reviews only its legacy row still holds."""
    from tripplanner import place_cache_layout

    created: list[dict] = []
    legacy = {
        "id": "ab12",
        "user_id": "_shared",
        "entry": {"name": "legacy", "__at__": 100.0, "reviews": ["kept"], "__reviews_at__": 150.0},
    }

    class FakeContainer:
        def read_item(self, *, item, partition_key):
            if partition_key == place_cache_layout.LEGACY_PARTITION:
                return legacy
            raise _CosmosError(404)

        def create_item(self, *, body):
            created.append(body)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.merge_write(
        "places_cache", "ab12", {"key": "taj|goa", "entry": {"name": "fresh", "__at__": 200.0}}
    )
    assert created[0]["user_id"] == place_cache_layout.partition("ab12")
    assert created[0]["entry"]["name"] == "fresh"
    assert created[0]["entry"]["reviews"] == ["kept"]


def test_tool_cache_keeps_its_global_partition(monkeypatch):
    partitions: list[str] = []

    class FakeContainer:
        def read_item(self, *, item, partition_key):
            partitions.append(partition_key)
            raise _CosmosError(404)

    monkeypatch.setattr(secondary_cache, "_available", lambda: True)
    monkeypatch.setattr(secondary_cache, "_container", lambda _name: FakeContainer())

    assert secondary_cache.read_doc("tool_cache", "web_search-abc") is None
    assert partitions == ["_global_"]
