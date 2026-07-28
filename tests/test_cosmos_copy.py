from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts import cosmos_copy
from scripts.cosmos_copy import (
    DEFAULT_CONTAINERS,
    CosmosConnection,
    _portable_item,
    _require_recovery_target,
    copy_container,
    copy_cosmos,
    export_backup,
    restore_backup,
    run_backup_recovery_drill,
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


class FakeDatabase:
    def __init__(self, containers: dict[str, FakeContainer]) -> None:
        self.containers = containers

    def list_containers(self) -> list[dict[str, str]]:
        return [{"id": name} for name in self.containers]

    def get_container_client(self, name: str) -> FakeContainer:
        return self.containers[name]


class FakeClient:
    def __init__(self, databases: dict[str, FakeDatabase]) -> None:
        self.databases = databases

    def get_database_client(self, name: str) -> FakeDatabase:
        return self.databases[name]


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


def _recovery_databases() -> tuple[FakeDatabase, FakeDatabase]:
    source = FakeDatabase(
        {
            name: FakeContainer(
                [{"id": f"{name}-1", "user_id": "u1", "value": name}]
            )
            for name in DEFAULT_CONTAINERS
        }
    )
    target = FakeDatabase({name: FakeContainer([]) for name in DEFAULT_CONTAINERS})
    return source, target


def test_recovery_drill_rejects_live_target_database() -> None:
    source_database, target_database = _recovery_databases()

    with pytest.raises(ValueError, match="live canary or production"):
        _require_recovery_target(
            CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
            CosmosConnection("https://target.test", "secret", "tripplanner-canary"),
            source_database,
            target_database,
            list(DEFAULT_CONTAINERS),
        )


def test_recovery_drill_requires_all_containers() -> None:
    source_database, target_database = _recovery_databases()
    del target_database.containers["audit_events"]

    with pytest.raises(RuntimeError, match=r"missing_target=\['audit_events'\]"):
        _require_recovery_target(
            CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
            CosmosConnection("https://target.test", "secret", "tripplanner-recovery"),
            source_database,
            target_database,
            list(DEFAULT_CONTAINERS),
        )


def test_recovery_drill_requires_empty_target() -> None:
    source_database, target_database = _recovery_databases()
    target_database.containers["users"].items.append(
        {"id": "existing", "user_id": "u1"}
    )

    with pytest.raises(RuntimeError, match=r"nonempty_containers=\['users'\]"):
        _require_recovery_target(
            CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
            CosmosConnection("https://target.test", "secret", "tripplanner-recovery"),
            source_database,
            target_database,
            list(DEFAULT_CONTAINERS),
        )


def test_backup_recovery_drill_reports_without_credentials(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    source_database, target_database = _recovery_databases()
    clients = iter(
        [
            FakeClient({"tripplanner-prod": source_database}),
            FakeClient({"tripplanner-recovery": target_database}),
        ]
    )
    monkeypatch.setattr(cosmos_copy, "_client", lambda connection: next(clients))
    source = CosmosConnection(
        "https://source.test", "source-super-secret", "tripplanner-prod"
    )
    target = CosmosConnection(
        "https://target.test", "target-super-secret", "tripplanner-recovery"
    )

    report = run_backup_recovery_drill(source, target, tmp_path / "backup")

    assert report["status"] == "passed"
    assert report["backup"]["total_items"] == len(DEFAULT_CONTAINERS)
    assert report["restore"]["restored_items"] == len(DEFAULT_CONTAINERS)
    assert report["backup"]["source"] == {
        "host": "source.test",
        "database": "tripplanner-prod",
    }
    assert report["restore"]["target"] == {
        "host": "target.test",
        "database": "tripplanner-recovery",
    }
    assert "secret" not in str(report)
    for name in DEFAULT_CONTAINERS:
        assert target_database.containers[name].items == source_database.containers[name].items


def test_recovery_drill_rejects_partial_container_scope() -> None:
    source_database, target_database = _recovery_databases()

    with pytest.raises(ValueError, match="exactly the six default"):
        _require_recovery_target(
            CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
            CosmosConnection("https://target.test", "secret", "tripplanner-recovery"),
            source_database,
            target_database,
            ["users"],
        )


def test_backup_export_rejects_partial_container_scope(tmp_path) -> None:
    with pytest.raises(ValueError, match="exactly the six default"):
        export_backup(
            CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
            tmp_path / "backup",
            ["users"],
        )


def test_recovery_drill_same_coordinates_ignore_key_rotation() -> None:
    source_database, target_database = _recovery_databases()

    with pytest.raises(ValueError, match="must be different"):
        _require_recovery_target(
            CosmosConnection("https://same.test/", "old-key", "tripplanner-recovery"),
            CosmosConnection("https://SAME.test", "new-key", "TRIPPLANNER-RECOVERY"),
            source_database,
            target_database,
            list(DEFAULT_CONTAINERS),
        )


def test_backup_artifact_strips_metadata_and_restores_without_source(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    source_database, target_database = _recovery_databases()
    source_database.containers["users"].items[0]["_etag"] = "private-metadata"
    source_client = FakeClient({"tripplanner-prod": source_database})
    target_client = FakeClient({"tripplanner-restore-drill": target_database})
    clients = iter([source_client, target_client])
    monkeypatch.setattr(cosmos_copy, "_client", lambda connection: next(clients))
    source = CosmosConnection(
        "https://source.test", "source-super-secret", "tripplanner-prod"
    )
    target = CosmosConnection(
        "https://target.test", "target-super-secret", "tripplanner-restore-drill"
    )
    backup_dir = tmp_path / "backup"

    manifest = export_backup(source, backup_dir, list(DEFAULT_CONTAINERS))
    report = restore_backup(backup_dir, target)

    assert manifest["total_items"] == len(DEFAULT_CONTAINERS)
    assert report["status"] == "passed"
    assert report["restored_items"] == len(DEFAULT_CONTAINERS)
    assert "private-metadata" not in (backup_dir / "users.jsonl").read_text()
    assert "super-secret" not in (backup_dir / "manifest.json").read_text()
    assert target_database.containers["users"].items[0] == {
        "id": "users-1",
        "user_id": "u1",
        "value": "users",
    }


def test_restore_rejects_tampered_backup_before_writing(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    source_database, target_database = _recovery_databases()
    source_client = FakeClient({"tripplanner-prod": source_database})
    target_client = FakeClient({"tripplanner-recovery": target_database})
    clients = iter([source_client, target_client])
    monkeypatch.setattr(cosmos_copy, "_client", lambda connection: next(clients))
    backup_dir = tmp_path / "backup"
    export_backup(
        CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
        backup_dir,
        list(DEFAULT_CONTAINERS),
    )
    (backup_dir / "users.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="checksum verification failed for users"):
        restore_backup(
            backup_dir,
            CosmosConnection(
                "https://target.test", "secret", "tripplanner-recovery"
            ),
        )

    assert all(not container.items for container in target_database.containers.values())


def test_restore_rejects_manifest_path_outside_artifact(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    source_database, target_database = _recovery_databases()
    clients = iter(
        [
            FakeClient({"tripplanner-prod": source_database}),
            FakeClient({"tripplanner-recovery": target_database}),
        ]
    )
    monkeypatch.setattr(cosmos_copy, "_client", lambda connection: next(clients))
    backup_dir = tmp_path / "backup"
    export_backup(
        CosmosConnection("https://source.test", "secret", "tripplanner-prod"),
        backup_dir,
        list(DEFAULT_CONTAINERS),
    )
    manifest_path = backup_dir / "manifest.json"
    manifest = cosmos_copy.json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["containers"]["users"]["file"] = "../users.jsonl"
    manifest_path.write_text(cosmos_copy.json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="file reference validation failed for users"):
        restore_backup(
            backup_dir,
            CosmosConnection(
                "https://target.test", "secret", "tripplanner-recovery"
            ),
        )

    assert all(not container.items for container in target_database.containers.values())
