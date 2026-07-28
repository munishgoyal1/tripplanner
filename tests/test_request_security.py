from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.request_limits import ChatAdmission
from tripplanner.web import oauth

_SECRET = "request-security-test-secret"
_GUEST_ID = "web-3d6f0a58-74ec-4f9d-90f4-5676b9b3709f"
_OTHER_GUEST_ID = "web-9be64527-9d9a-431c-a6ce-b1aec7392e8f"


def _hosted(monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    monkeypatch.setenv("WEB_SESSION_SECRET", _SECRET)
    return TestClient(api.app)


def _user_token(user_id: str) -> str:
    return oauth.make_session_token(user_id, "Test User", "test@example.com", "")


def test_signed_cookie_overrides_forged_usage_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.get("/usage", params={"user_id": "google-victim"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "google-owner"


def test_mobile_bearer_overrides_forged_usage_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)

    response = client.get(
        "/usage",
        params={"user_id": "google-victim"},
        headers={"Authorization": f"Bearer {_user_token('google-mobile-owner')}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == "google-mobile-owner"


def test_hosted_api_rejects_invalid_bearer_and_unsigned_account_id(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)

    response = client.get(
        "/usage",
        params={"user_id": "google-victim"},
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401


def test_guest_session_bootstrap_authorizes_only_its_signed_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)
    bootstrap = client.post("/auth/guest/session", json={"user_id": _GUEST_ID})
    token = bootstrap.json()["token"]

    response = client.get(
        "/usage",
        params={"user_id": _OTHER_GUEST_ID},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert bootstrap.status_code == 200
    assert response.status_code == 200
    assert response.json()["user_id"] == _GUEST_ID


def test_hosted_api_rejects_unsigned_guest_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)

    response = client.get("/usage", params={"user_id": _GUEST_ID})

    assert response.status_code == 401


def test_privacy_action_uses_signed_principal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import get_user_id
    from tripplanner.web import chat_store

    observed: list[str] = []
    monkeypatch.setattr(
        trip_planner,
        "clear_all_trip_history",
        lambda: observed.append(get_user_id()) or 0,
    )
    monkeypatch.setattr(chat_store, "clear_all", lambda: 0)
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.post(
        "/account/privacy",
        json={"user_id": "google-victim", "action": "delete_trip_history"},
    )

    assert response.status_code == 200
    assert observed == ["google-owner"]


def test_guest_summary_requires_matching_account_and_guest_sessions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))
    guest_token = oauth.make_guest_token(_GUEST_ID)

    missing_guest = client.get("/account/guest-data-summary", params={"user_id": _GUEST_ID})
    matching_guest = client.get(
        "/account/guest-data-summary",
        params={"user_id": _GUEST_ID},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    wrong_guest = client.get(
        "/account/guest-data-summary",
        params={"user_id": _OTHER_GUEST_ID},
        headers={"Authorization": f"Bearer {guest_token}"},
    )

    assert missing_guest.status_code == 403
    assert matching_guest.status_code == 200
    assert wrong_guest.status_code == 403


def test_chat_message_length_is_bounded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.post("/chat", json={"message": "x" * 12_001, "user_id": "google-owner"})

    assert response.status_code == 422


def test_chat_admission_rejects_overlapping_turn_for_same_user(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CHAT_MAX_CONCURRENT_PER_USER", "1")
    admission = ChatAdmission()

    async def scenario() -> None:
        permit = await admission.acquire("user-1", "127.0.0.1")
        with pytest.raises(HTTPException, match="already in progress") as error:
            await admission.acquire("user-1", "127.0.0.1")
        assert error.value.status_code == 429
        await admission.release(permit)

    asyncio.run(scenario())


def test_chat_admission_enforces_user_request_window(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CHAT_USER_REQUESTS_PER_MINUTE", "1")
    admission = ChatAdmission()

    async def scenario() -> None:
        permit = await admission.acquire("user-1", "127.0.0.1")
        await admission.release(permit)
        with pytest.raises(HTTPException, match="Too many chat requests") as error:
            await admission.acquire("user-1", "127.0.0.1")
        assert error.value.status_code == 429

    asyncio.run(scenario())
