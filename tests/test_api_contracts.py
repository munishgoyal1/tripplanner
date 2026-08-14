from __future__ import annotations

from fastapi.testclient import TestClient

from tripplanner import api, http_client
from tripplanner.api_contracts import ChatRequest


def test_api_reexports_chat_contract() -> None:
    assert api.ChatRequest is ChatRequest


def test_chat_request_validation_is_preserved() -> None:
    client = TestClient(api.app)

    response = client.post("/chat", json={"message": "x" * 12_001})

    assert response.status_code == 422


def test_provider_status_exposes_readiness_without_secrets(monkeypatch) -> None:
    monkeypatch.setattr(
        "tripplanner.providers.registry.provider_status",
        lambda: [
            {
                "name": "openrouteservice",
                "configured": True,
                "active": True,
                "access": "active_free_or_sandbox",
            }
        ],
    )
    client = TestClient(api.app)
    http_client.reset_breakers_for_tests()

    response = client.get("/providers/status")

    assert response.status_code == 200
    assert response.json() == {
        "providers": [
            {
                "name": "openrouteservice",
                "configured": True,
                "active": True,
                "access": "active_free_or_sandbox",
            }
        ],
        "outbound": {"endpoints": {}},
    }


def test_deleting_a_non_active_trip_does_not_wait_on_an_in_progress_chat(monkeypatch) -> None:
    """The reported defect: deleting an unrelated saved trip returned 409 while
    a chat turn was in progress for the active trip, even though only the
    active trip is mutated by that turn."""
    from tripplanner.request_limits import chat_admission

    monkeypatch.setattr(
        "tripplanner.tools.trip_planner.active_trip_id", lambda: "active-trip"
    )
    monkeypatch.setattr(
        "tripplanner.tools.trip_planner.delete_saved_trip", lambda trip_id: True
    )
    monkeypatch.setattr("tripplanner.tools.trip_planner.list_saved_trips", lambda: [])
    monkeypatch.setattr("tripplanner.web.chat_store.clear", lambda trip_id: None)

    client = TestClient(api.app)
    chat_admission._active_users["local"] = 1
    try:
        response = client.post(
            "/trips/delete", json={"trip_id": "other-trip", "user_id": "local"}
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        response = client.post(
            "/trips/delete", json={"trip_id": "active-trip", "user_id": "local"}
        )
        assert response.status_code == 409
    finally:
        chat_admission._active_users.pop("local", None)
