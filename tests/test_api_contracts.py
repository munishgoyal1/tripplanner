from __future__ import annotations

from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.api_contracts import ChatRequest


def test_api_reexports_chat_contract() -> None:
    assert api.ChatRequest is ChatRequest


def test_chat_request_validation_is_preserved() -> None:
    client = TestClient(api.app)

    response = client.post("/chat", json={"message": "x" * 12_001})

    assert response.status_code == 422
