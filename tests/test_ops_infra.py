from __future__ import annotations

from tripplanner import storage_cosmos


class _Container:
    def __init__(self, count: int) -> None:
        self.count = count

    def query_items(self, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs == {
            "query": "SELECT VALUE COUNT(1) FROM c",
            "enable_cross_partition_query": True,
        }
        return [self.count]


class _Database:
    def list_containers(self):  # type: ignore[no-untyped-def]
        return [
            {"id": "trips"},
            {"id": "provider_usage", "defaultTtl": 7_776_000},
        ]

    def get_container_client(self, name: str) -> _Container:
        return _Container({"trips": 12, "provider_usage": 31}[name])


def test_operations_inventory_counts_existing_containers_without_secrets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "_client_singleton", lambda: object())
    monkeypatch.setattr(storage_cosmos, "_database", _Database())
    monkeypatch.setattr(
        storage_cosmos,
        "get_settings",
        lambda: type("Settings", (), {"cosmos_database": "tripplanner-prod"})(),
    )

    assert storage_cosmos.operations_inventory() == {
        "enabled": True,
        "database": "tripplanner-prod",
        "containers": [
            {"name": "provider_usage", "records": 31, "default_ttl": 7_776_000},
            {"name": "trips", "records": 12, "default_ttl": None},
        ],
    }
