from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts.cosmos_copy import (
    CosmosConnection,
    _portable_item,
    copy_container,
    copy_cosmos,
    verify_container,
)


class FakeContainer:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = deepcopy(items)

    def query_items(self, **_: Any) -> list[dict[str, Any]]:
        return deepcopy(self.items)

    def upsert_item(self, item: dict[str, Any]) -> None:
        key = (item["user_id"], item["id"])
        self.items = [
            existing
            for existing in self.items
            if (existing["user_id"], existing["id"]) != key
        ]
        self.items.append(deepcopy(item))


def test_copy_strips_cosmos_metadata_and_verifies() -> None:
    source = FakeContainer(
        [{"id": "preferences", "user_id": "u1", "name": "Munish", "_etag": "old"}]
    )
    target = FakeContainer([])

    assert copy_container(source, target, "users") == 1
    assert target.items == [{"id": "preferences", "user_id": "u1", "name": "Munish"}]
    assert verify_container(source, target, "users") == 1


def test_verify_rejects_changed_documents() -> None:
    source = FakeContainer([{"id": "one", "user_id": "u1", "value": 1}])
    target = FakeContainer([{"id": "one", "user_id": "u1", "value": 2}])

    with pytest.raises(RuntimeError, match="mismatched=1"):
        verify_container(source, target, "users")


def test_verify_accepts_cosmos_float_round_trip_drift() -> None:
    source = FakeContainer(
        [{"id": "one", "user_id": "u1", "coords": {"lat": 15.587015300000001}}]
    )
    target = FakeContainer(
        [{"id": "one", "user_id": "u1", "coords": {"lat": 15.5870153}}]
    )

    assert verify_container(source, target, "places_cache") == 1


def test_verify_rejects_meaningful_float_change() -> None:
    source = FakeContainer([{"id": "one", "user_id": "u1", "lat": 15.5870153}])
    target = FakeContainer([{"id": "one", "user_id": "u1", "lat": 15.5871153}])

    with pytest.raises(RuntimeError, match="mismatched=1"):
        verify_container(source, target, "places_cache")


def test_dry_run_does_not_write() -> None:
    source = FakeContainer([{"id": "one", "user_id": "u1"}])
    target = FakeContainer([])

    assert copy_container(source, target, "users", dry_run=True) == 1
    assert target.items == []


def test_audit_copy_preserves_remaining_ttl() -> None:
    item = {
        "id": "event-1",
        "user_id": "u1",
        "message": "created",
        "_ts": 1_000,
        "ttl": 100,
    }

    assert _portable_item(item, "audit_events", now=1_040) == {
        "id": "event-1",
        "user_id": "u1",
        "message": "created",
        "ttl": 60,
    }


def test_audit_copy_preserves_permanent_ttl() -> None:
    item = {"id": "event-1", "user_id": "u1", "_ts": 1_000, "ttl": -1}

    assert _portable_item(item, "audit_events", now=1_040)["ttl"] == -1


def test_audit_verify_rejects_permanent_to_expiring_change() -> None:
    source = FakeContainer(
        [{"id": "event-1", "user_id": "u1", "_ts": 1_000, "ttl": -1}]
    )
    target = FakeContainer(
        [{"id": "event-1", "user_id": "u1", "_ts": 1_040, "ttl": 60}]
    )

    with pytest.raises(RuntimeError, match="mismatched=1"):
        verify_container(source, target, "audit_events")


def test_copy_rejects_identical_source_and_target() -> None:
    connection = CosmosConnection("https://localhost:8081", "key", "tripplanner")

    with pytest.raises(ValueError, match="must be different"):
        copy_cosmos(connection, connection, ["users"])
