from __future__ import annotations

import json

import pytest

from tripplanner.json_store import atomic_write_json


def test_atomic_write_json_replaces_existing_document(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(path, {"new": True}, indent=2)

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_json_preserves_existing_file_when_replace_fails(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"old": true}', encoding="utf-8")

    def fail_replace(*_args) -> None:
        raise OSError("locked")

    monkeypatch.setattr("tripplanner.json_store.os.replace", fail_replace)

    with pytest.raises(OSError, match="locked"):
        atomic_write_json(path, {"new": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_json_retries_transient_file_lock(tmp_path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    real_replace = __import__("os").replace
    attempts = 0

    def replace_after_lock(source, destination) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporarily locked")
        real_replace(source, destination)

    monkeypatch.setattr("tripplanner.json_store.os.replace", replace_after_lock)
    monkeypatch.setattr("tripplanner.json_store.time.sleep", lambda _: None)

    atomic_write_json(path, {"saved": True})

    assert attempts == 2
    assert json.loads(path.read_text(encoding="utf-8")) == {"saved": True}
