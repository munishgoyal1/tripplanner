from __future__ import annotations

from pathlib import Path

import pytest

from tripplanner import debug_store, storage_cosmos
from tripplanner.trip_models import TripPatch, TripPlan
from tripplanner.trip_repository import TripConflictError, TripPaths, TripRepository


def _repository(tmp_path: Path) -> TripRepository:
    return TripRepository(
        "user-1",
        TripPaths(active=tmp_path / "active_trip.json", history=tmp_path / "trips"),
    )


def test_tolerant_contracts_round_trip_unknown_legacy_fields() -> None:
    raw = {
        "trip_id": "goa",
        "destination": "Goa",
        "legacy_trip_field": {"kept": True},
        "day_wise_itinerary": [
            {
                "day": 1,
                "legacy_day_field": "kept",
                "stops": [{"name": "Fort", "legacy_stop_field": 7}],
            }
        ],
    }

    dumped = TripPlan.model_validate(raw).model_dump(mode="python")

    assert dumped["legacy_trip_field"] == {"kept": True}
    assert dumped["day_wise_itinerary"][0]["legacy_day_field"] == "kept"
    assert dumped["day_wise_itinerary"][0]["stops"][0]["legacy_stop_field"] == 7


def test_typed_patch_preserves_omitted_and_unknown_fields(
    tmp_path, monkeypatch
) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    created = repository.save(
        {
            "trip_id": "goa",
            "destination": "Goa",
            "legacy_trip_field": {"kept": True},
        }
    )
    assert created.revision == 1

    outcome = repository.patch("goa", TripPatch(status="ready"))

    assert outcome.revision == 2
    assert outcome.plan is not None
    dumped = outcome.plan.model_dump(mode="python", exclude_unset=True)
    assert dumped["destination"] == "Goa"
    assert dumped["status"] == "ready"
    assert dumped["legacy_trip_field"] == {"kept": True}
    assert TripPatch.model_validate({"notes": "new", "future": 1}).changes() == {
        "notes": "new",
        "future": 1,
    }


def test_local_repository_stores_one_canonical_plan_and_pointer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    repository = _repository(tmp_path)

    outcome = repository.save(
        {"trip_id": "goa", "destination": "Goa", "legacy": "preserved"}
    )

    assert outcome.revision == 1
    assert repository.load_active() == repository.load("goa")
    assert repository._read_active() == {"trip_id": "goa", "revision": 1}
    assert repository.load("goa")["legacy"] == "preserved"


def test_legacy_full_active_document_remains_readable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    repository = _repository(tmp_path)
    repository.paths.active.parent.mkdir(parents=True, exist_ok=True)
    repository.paths.active.write_text(
        '{"trip_id":"legacy","destination":"Jaipur","unknown":true}',
        encoding="utf-8",
    )

    assert repository.load_active() == {
        "trip_id": "legacy",
        "destination": "Jaipur",
        "unknown": True,
    }


def test_cosmos_mutation_retries_etag_conflict_without_losing_update(
    tmp_path, monkeypatch
) -> None:
    repository = _repository(tmp_path)
    state = {
        "body": {"trip_id": "goa", "revision": 2, "notes": ["first"]},
        "version": '"v2"',
    }
    attempts = 0

    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "read_doc_versioned",
        lambda *_args: storage_cosmos.VersionedDocument(
            body=state["body"], version=state["version"]
        ),
    )

    def replace(_container, _user, _trip_id, body, version):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            state["body"] = {
                "trip_id": "goa",
                "revision": 3,
                "notes": ["first", "concurrent"],
            }
            state["version"] = '"v3"'
            raise storage_cosmos.WriteConflictError("changed")
        assert version == '"v3"'
        state["body"] = body

    monkeypatch.setattr(storage_cosmos, "replace_doc_if_version", replace)
    monkeypatch.setattr(storage_cosmos, "upsert_doc", lambda *_args: None)
    monkeypatch.setattr("tripplanner.trip_repository.debug_store.record_trip", lambda *_: None)

    outcome = repository.mutate(
        "goa",
        lambda current: {
            **(current or {}),
            "notes": [*(current or {}).get("notes", []), "mine"],
        },
    )

    assert attempts == 2
    assert outcome.revision == 4
    assert state["body"]["notes"] == ["first", "concurrent", "mine"]


def test_repeated_cosmos_conflicts_are_explicit(tmp_path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "read_doc_versioned",
        lambda *_args: storage_cosmos.VersionedDocument(
            body={"trip_id": "goa", "revision": 1}, version='"v1"'
        ),
    )
    monkeypatch.setattr(
        storage_cosmos,
        "replace_doc_if_version",
        lambda *_args: (_ for _ in ()).throw(storage_cosmos.WriteConflictError("changed")),
    )

    with pytest.raises(TripConflictError, match="kept changing"):
        repository.mutate("goa", lambda current: current or {})


def test_detached_stale_save_returns_explicit_conflict(tmp_path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    first = repository.save({"trip_id": "goa", "notes": ["first"]})
    assert first.plan is not None
    stale = first.plan.model_dump(mode="python", exclude_unset=True)

    repository.mutate(
        "goa",
        lambda current: {
            **(current or {}),
            "notes": [*(current or {}).get("notes", []), "concurrent"],
        },
    )

    stale["notes"].append("mine")
    with pytest.raises(TripConflictError, match="changed from revision 1 to 2"):
        repository.save(stale)

    assert repository.load("goa")["notes"] == ["first", "concurrent"]


def test_one_trip_update_uses_half_the_previous_cosmos_writes(
    tmp_path, monkeypatch
) -> None:
    repository = _repository(tmp_path)
    writes: list[tuple[str, str, dict]] = []
    current = storage_cosmos.VersionedDocument(
        body={"trip_id": "goa", "revision": 4, "notes": []},
        version="etag-4",
    )
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos, "read_doc_versioned", lambda *_args: current
    )
    monkeypatch.setattr(
        storage_cosmos,
        "replace_doc_if_version",
        lambda container, _user, doc_id, body, _version: writes.append(
            (container, doc_id, body)
        ),
    )
    monkeypatch.setattr(
        storage_cosmos,
        "upsert_doc",
        lambda container, _user, doc_id, body: writes.append(
            (container, doc_id, body)
        ),
    )
    monkeypatch.setattr(debug_store, "record_trip", lambda *_args: None)

    repository.mutate(
        "goa", lambda plan: {**(plan or {}), "notes": ["updated"]}
    )

    assert len(writes) == 2
    assert writes[0][:2] == ("trips", "goa")
    assert writes[1] == (
        "users",
        "active_trip",
        {"trip_id": "goa", "revision": 5},
    )


def test_pointer_failure_cannot_create_a_second_trip_copy(tmp_path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    writes: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "read_doc_versioned", lambda *_args: None)
    monkeypatch.setattr(
        storage_cosmos,
        "create_doc_if_absent",
        lambda container, _user, doc_id, body: writes.append((container, doc_id, body)),
    )

    def fail_pointer(container, _user, doc_id, body):
        writes.append((container, doc_id, body))
        raise OSError("pointer unavailable")

    monkeypatch.setattr(storage_cosmos, "upsert_doc", fail_pointer)

    with pytest.raises(OSError, match="pointer unavailable"):
        repository.save({"trip_id": "goa", "destination": "Goa"})

    assert writes[0][0:2] == ("trips", "goa")
    assert writes[1] == ("users", "active_trip", {"trip_id": "goa", "revision": 1})
    assert sum(1 for container, _doc_id, body in writes if "destination" in body) == 1
