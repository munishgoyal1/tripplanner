from __future__ import annotations

from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.web import oauth


def test_mobile_auth_redirect_adds_signed_session_only_to_native_schemes() -> None:
    target = api._mobile_auth_redirect("tripplanner://auth?source=expo", "signed-token")

    assert target == "tripplanner://auth?source=expo&session=signed-token"
    assert api._mobile_auth_redirect("https://evil.example/auth", "signed-token") is None


def test_mobile_session_validates_signed_token(monkeypatch) -> None:
    monkeypatch.setenv("WEB_SESSION_SECRET", "test-secret")
    token = oauth.make_session_token("google-123", "Munish", "m@example.com", "")

    response = TestClient(api.app).get("/auth/mobile/session", params={"token": token})

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user_id": "google-123",
        "display_name": "Munish",
        "email": "m@example.com",
        "picture": "",
    }


def test_mobile_session_rejects_invalid_token() -> None:
    response = TestClient(api.app).get("/auth/mobile/session", params={"token": "invalid"})

    assert response.status_code == 401
    assert response.json() == {"authenticated": False}