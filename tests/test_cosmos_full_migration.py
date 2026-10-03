from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import cosmos_copy as copy


class Container:
    def __init__(self, items=(), ttl=None):
        self.items = list(deepcopy(items))
        self.ttl = ttl
        self.writes = 0

    def read(self):
        schema = {"partitionKey": {"paths": ["/user_id"], "kind": "Hash"}}
        if self.ttl is not None:
            schema["defaultTtl"] = self.ttl
        return schema

    def query_items(self, **kwargs):
        return deepcopy(self.items)

    def upsert_item(self, item):
        self.writes += 1
        self.items = [row for row in self.items if copy._item_key(row) != copy._item_key(item)]
        self.items.append({**item, "_ts": 2000})


def database(containers):
    return SimpleNamespace(
        list_containers=lambda: [{"id": name} for name in containers],
        get_container_client=containers.__getitem__,
    )


def setup(monkeypatch, source, target):
    src = copy.CosmosConnection("https://source.documents.azure.com", "source-key", "prod")
    dst = copy.CosmosConnection("https://target.documents.azure.com", "target-key", "prod")
    monkeypatch.setattr(
        copy,
        "_client",
        lambda coordinates: SimpleNamespace(
            get_database_client=lambda name: database(source if coordinates == src else target)
        ),
    )
    monkeypatch.setattr(copy.time, "time", lambda: 2000)
    return src, dst


def test_full_copy_discovers_new_containers_and_preserves_expiry(monkeypatch, tmp_path):
    item = {"id": "a", "user_id": "u", "_ts": 1900, "value": 4}
    source = {"future_container": Container([item], ttl=300)}
    target = {"future_container": Container([], ttl=300)}
    src, dst = setup(monkeypatch, source, target)
    assert copy.copy_all_containers(src, dst, target_backup_dir=tmp_path / "backup") == 1
    assert target["future_container"].items[0]["ttl"] == 200
    assert source["future_container"].writes == 0
    assert (tmp_path / "backup" / "manifest.json").is_file()


@pytest.mark.parametrize("problem", ["extra", "schema", "missing"])
def test_target_conflicts_block_before_any_write(monkeypatch, tmp_path, problem):
    source = {"trips": Container([{"id": "a", "user_id": "u"}])}
    target = {"trips": Container()}
    if problem == "extra":
        target["trips"].items = [{"id": "old-target-only", "user_id": "u"}]
    elif problem == "schema":
        target["trips"].ttl = 300
    else:
        target = {}
    src, dst = setup(monkeypatch, source, target)
    with pytest.raises(RuntimeError):
        copy.copy_all_containers(src, dst, target_backup_dir=tmp_path / "backup")
    assert all(container.writes == 0 for container in target.values())
    assert source["trips"].writes == 0


def test_same_coordinates_rejected_even_with_different_keys():
    src = copy.CosmosConnection("https://example.documents.azure.com/", "readonly-key", "prod")
    dst = copy.CosmosConnection("https://EXAMPLE.documents.azure.com", "write-key", "prod")
    with pytest.raises(ValueError, match="different"):
        copy.copy_all_containers(src, dst, target_backup_dir=Path("unused"))


def test_snapshot_required_and_failure_blocks_writes(monkeypatch, tmp_path):
    source = {"trips": Container([{"id": "a", "user_id": "u"}])}
    target = {"trips": Container()}
    src, dst = setup(monkeypatch, source, target)
    with pytest.raises(ValueError, match="snapshot"):
        copy.copy_all_containers(src, dst, target_backup_dir=None)
    (tmp_path / "existing").write_text("preserved")
    with pytest.raises(ValueError, match="empty"):
        copy.copy_all_containers(src, dst, target_backup_dir=tmp_path)
    assert target["trips"].writes == 0


@pytest.mark.parametrize("mode", ["dry_run", "verify_only"])
def test_read_only_modes_do_not_write_or_snapshot(monkeypatch, mode):
    item = {"id": "a", "user_id": "u"}
    source, target = {"trips": Container([item])}, {"trips": Container([item])}
    src, dst = setup(monkeypatch, source, target)
    assert copy.copy_all_containers(src, dst, target_backup_dir=None, **{mode: True}) == 1
    assert target["trips"].writes == 0


def test_source_uses_readonly_key_and_its_own_cli_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        copy, "_az_output", lambda *args, **kwargs: calls.append((args, kwargs)) or "x"
    )
    copy._azure_connection(
        "rg", "account", "db", "sub", azure_config_dir="source-cache", read_only=True
    )
    assert all(kwargs == {"azure_config_dir": "source-cache"} for _, kwargs in calls)
    assert "primaryReadonlyMasterKey" in calls[1][0]
    assert "read-only-keys" in calls[1][0]


def test_snapshot_preserves_overwritten_target_body(monkeypatch, tmp_path):
    import json

    source = {"trips": Container([{"id": "a", "user_id": "u", "value": "source"}])}
    target = {"trips": Container([{"id": "a", "user_id": "u", "value": "previous-target"}])}
    src, dst = setup(monkeypatch, source, target)
    copy.copy_all_containers(src, dst, target_backup_dir=tmp_path / "snapshot")
    manifest = json.loads((tmp_path / "snapshot/manifest.json").read_text())
    entry = manifest["containers"]["trips"]
    path = tmp_path / "snapshot" / entry["file"]
    assert copy._sha256(path) == entry["sha256"]
    assert json.loads(path.read_text())["value"] == "previous-target"
    assert target["trips"].items[0]["value"] == "source"
