from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.tools import trip_history, trip_planner
from tripplanner.web import trip_feedback


def test_feedback_appends_and_updates_trip_rollup(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    active_path = tmp_path / "active.json"
    history_dir = tmp_path / "trips"
    feedback_dir = tmp_path / "feedback" / "local"
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", active_path)
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", history_dir)
    monkeypatch.setattr(trip_history, "_ACTIVE_TRIP_FILE", active_path)
    monkeypatch.setattr(trip_history, "_TRIP_HISTORY_DIR", history_dir)
    monkeypatch.setattr(trip_feedback, "_LOCAL_ROOT", tmp_path / "feedback")
    monkeypatch.setattr(trip_planner.storage_cosmos, "is_enabled", lambda: False)
    active_path.write_text(
        json.dumps({"trip_id": "lisbon", "destination": "Lisbon", "updated_at": "r14"}),
        encoding="utf-8",
    )

    client = TestClient(api.app)
    first = client.post("/trip/feedback", json={"sentiment": "up"})

    assert first.status_code == 200
    feedback_id = first.json()["feedback"]["feedback_id"]
    second = client.post(
        "/trip/feedback",
        json={"feedback_id": feedback_id, "rating": 4, "comment": " Day 3 is too long. "},
    )
    assert second.status_code == 200
    assert second.json()["feedback"]["count"] == 1
    saved = json.loads((history_dir / "lisbon.json").read_text(encoding="utf-8"))
    assert saved["feedback"]["last_rating"] == 4
    assert json.loads(active_path.read_text(encoding="utf-8")) == {
        "trip_id": "lisbon",
        "revision": 2,
    }
    submissions = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in feedback_dir.glob("*.json")
    ]
    assert len(submissions) == 1
    commented = next(item for item in submissions if item["comment"])
    assert commented["comment"] == "Day 3 is too long."
    assert commented["trip_revision"]


def test_feedback_rejects_an_empty_submission() -> None:
    response = TestClient(api.app).post("/trip/feedback", json={})

    assert response.status_code == 422


def test_deleting_a_trip_removes_its_feedback(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(trip_feedback, "_LOCAL_ROOT", tmp_path / "feedback")
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", tmp_path / "trips")
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", tmp_path / "active.json")
    monkeypatch.setattr(trip_history, "_TRIP_HISTORY_DIR", tmp_path / "trips")
    monkeypatch.setattr(trip_history, "_ACTIVE_TRIP_FILE", tmp_path / "active.json")
    monkeypatch.setattr(trip_planner.storage_cosmos, "is_enabled", lambda: False)
    trip_feedback.append(
        trip_id="lisbon",
        trip_revision="r14",
        sentiment="down",
        rating=None,
        comment=None,
        surface="toolbar-pill",
        client="web",
        identified=False,
    )

    assert trip_planner.delete_saved_trip("lisbon") is True
    assert list((tmp_path / "feedback" / "local").glob("*.json")) == []
