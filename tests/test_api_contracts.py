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
