from __future__ import annotations

import asyncio
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner.request_identity import require_owner
from tripplanner.request_limits import ChatAdmission, ReplayLookupAdmission, chat_admission
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


def test_owner_guard_accepts_configured_verified_email(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPS_DASHBOARD_OWNER_EMAIL", "owner@example.com")
    client = _hosted(monkeypatch)
    client.cookies.set(
        oauth.SESSION_COOKIE,
        oauth.make_session_token("google-owner", "Owner", "OWNER@example.com", ""),
    )

    @api.app.get("/_test/owner-guard/allowed")
    async def owner_guard_allowed(request: Request):
        return {"user_id": require_owner(request)["user_id"]}

    response = client.get("/_test/owner-guard/allowed")

    assert response.status_code == 200
    assert response.json() == {"user_id": "google-owner"}


@pytest.mark.parametrize("identity", ["missing", "guest", "non_owner"])
def test_owner_guard_hides_route_from_every_other_identity(monkeypatch, identity: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPS_DASHBOARD_OWNER_EMAIL", "owner@example.com")
    client = _hosted(monkeypatch)
    if identity == "guest":
        client.cookies.set(oauth.SESSION_COOKIE, oauth.make_guest_token(_GUEST_ID))
    elif identity == "non_owner":
        client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-other"))

    @api.app.get(f"/_test/owner-guard/{identity}")
    async def owner_guard_hidden(request: Request):
        return require_owner(request)

    response = client.get(f"/_test/owner-guard/{identity}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


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


def test_preferences_replace_explicit_lists_and_preserve_concurrent_fields(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import user_preferences

    current = user_preferences.load_preferences()
    current["interests"] = ["old interest"]
    current["dislikes"] = ["old dislike"]
    current["planning_mode"] = "concurrent value"
    stored: dict = {}

    def mutate(apply):
        updated = apply(current)
        assert updated is not None
        stored.update(updated)
        return updated

    monkeypatch.setattr(user_preferences, "load_preferences", lambda: current)
    monkeypatch.setattr(user_preferences, "mutate_preferences", mutate)
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.post(
        "/preferences",
        json={
            "user_id": "google-victim",
            "interests": [],
            "dislikes": ["red-eye flights"],
        },
    )

    assert response.status_code == 200
    assert stored["interests"] == []
    assert stored["dislikes"] == ["red-eye flights"]
    assert stored["planning_mode"] == "concurrent value"


def test_preferences_round_trip_planning_mode(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import user_preferences

    state = user_preferences.load_preferences()

    def load():
        return state

    def mutate(apply):
        updated = apply(state)
        assert updated is not None
        state.update(updated)
        return state

    monkeypatch.setattr(user_preferences, "load_preferences", load)
    monkeypatch.setattr(user_preferences, "mutate_preferences", mutate)
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    before = client.get("/preferences")
    saved = client.post(
        "/preferences",
        json={"planning_mode": "interactive", "user_id": "google-owner"},
    )
    after = client.get("/preferences")

    assert before.json()["planning_mode"] == "direct"
    assert saved.status_code == 200
    assert after.json()["planning_mode"] == "interactive"


def test_preferences_round_trip_localization(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import user_preferences

    state = user_preferences.load_preferences()

    monkeypatch.setattr(user_preferences, "load_preferences", lambda: state)
    monkeypatch.setattr(
        user_preferences,
        "mutate_preferences",
        lambda apply: state.update(apply(state) or {}) or state,
    )
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    saved = client.post(
        "/preferences",
        json={
            "display_currency": "INR",
            "display_region": "India",
            "display_language": "en",
            "user_id": "google-owner",
        },
    )
    after = client.get("/preferences")

    assert saved.status_code == 200
    assert after.json()["display_currency"] == "INR"
    assert after.json()["display_region"] == "India"


def test_preferences_reports_stale_profile_summary_edit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import user_preferences

    current = user_preferences.load_preferences()
    current["profile_summary"] = "Concurrent summary"
    current["profile_summary_updated_at"] = "2026-07-28T13:00:00"
    monkeypatch.setattr(user_preferences, "load_preferences", lambda: current)
    monkeypatch.setattr(
        user_preferences,
        "mutate_preferences",
        lambda apply: apply(current) or current,
    )
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.post(
        "/preferences",
        json={
            "user_id": "google-owner",
            "profile_summary": "Stale correction",
            "profile_summary_updated_at": "2026-07-28T12:00:00",
            "planning_mode": "interactive",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": "profile summary changed while settings were open",
        "profile_summary": "Concurrent summary",
        "profile_summary_updated_at": "2026-07-28T13:00:00",
    }
    assert current["planning_mode"] == "direct"


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


def test_guest_summary_discovers_preference_only_data(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import trip_planner, user_preferences

    preferences = user_preferences.load_preferences()
    preferences["trip_style"] = "relaxed"
    monkeypatch.setattr(trip_planner, "list_saved_trips", lambda: [])
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: None)
    monkeypatch.setattr(user_preferences, "load_preferences", lambda: preferences)
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.get(
        "/account/guest-data-summary",
        params={"user_id": _GUEST_ID},
        headers={"Authorization": f"Bearer {oauth.make_guest_token(_GUEST_ID)}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "has_data": True,
        "trip_count": 0,
        "has_preferences": True,
    }


def test_guest_migration_preserves_account_fields_and_unions_lists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tripplanner.tools import trip_planner, user_preferences
    from tripplanner.user_context import get_user_id

    guest = user_preferences.load_preferences()
    guest["profile"]["display_name"] = "Guest name"
    guest["profile"]["home_city"] = "Bengaluru"
    guest["planning_mode"] = "direct"
    guest["interests"] = ["food"]
    account = user_preferences.load_preferences()
    account["profile"]["display_name"] = "OAuth name"
    account["planning_mode"] = "interactive"
    account["interests"] = ["museums"]
    stored = {"google-owner": account}

    monkeypatch.setattr(trip_planner, "list_saved_trips", lambda: [])
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: None)

    def load_preferences():
        source = guest if get_user_id() == _GUEST_ID else stored["google-owner"]
        return copy.deepcopy(source)

    def mutate_preferences(apply):
        current = copy.deepcopy(stored["google-owner"])
        updated = apply(current)
        if updated is not None:
            stored["google-owner"] = updated
        return copy.deepcopy(stored["google-owner"])

    monkeypatch.setattr(user_preferences, "load_preferences", load_preferences)
    monkeypatch.setattr(user_preferences, "mutate_preferences", mutate_preferences)
    client = _hosted(monkeypatch)
    client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))

    response = client.post(
        "/account/migrate-guest",
        json={"guest_id": _GUEST_ID, "user_id": "google-victim"},
        headers={"Authorization": f"Bearer {oauth.make_guest_token(_GUEST_ID)}"},
    )

    assert response.status_code == 200
    assert response.json()["copied_prefs"] is True
    assert stored["google-owner"]["profile"]["display_name"] == "OAuth name"
    assert stored["google-owner"]["profile"]["home_city"] == "Bengaluru"
    assert stored["google-owner"]["planning_mode"] == "interactive"
    assert stored["google-owner"]["interests"] == ["museums", "food"]


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


def test_live_chat_requests_enforce_same_user_concurrency(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from langchain_core.messages import AIMessage

    from tripplanner import usage
    from tripplanner.graph import app_graph

    entered_model = threading.Event()
    release_model = threading.Event()

    def invoke(_state):  # type: ignore[no-untyped-def]
        entered_model.set()
        assert release_model.wait(timeout=2)
        return {"messages": [AIMessage(content="ready")], "current_agent": "trip"}

    monkeypatch.setenv("CHAT_MAX_CONCURRENT_PER_USER", "1")
    monkeypatch.setenv("CHAT_USER_REQUESTS_PER_MINUTE", "10")
    monkeypatch.setattr(app_graph, "invoke", invoke)
    monkeypatch.setattr(usage, "is_over_cap", lambda _user_id: (False, {}))
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _request_id: (None, [], None))
    monkeypatch.setattr(api, "_save_chat", lambda *_args, **_kwargs: "trip-1")
    asyncio.run(chat_admission.reset())

    def post_chat(request_id: str):  # type: ignore[no-untyped-def]
        client = _hosted(monkeypatch)
        client.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))
        return client.post(
            "/chat",
            json={"message": "plan goa", "request_id": request_id},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(post_chat, "request-1")
            assert entered_model.wait(timeout=2)
            overlapping = post_chat("request-2")
            assert overlapping.status_code == 429
            assert "already in progress" in overlapping.json()["detail"]
            release_model.set()
            assert first.result(timeout=2).status_code == 200

        follow_up = post_chat("request-3")
        assert follow_up.status_code == 200
    finally:
        release_model.set()
        asyncio.run(chat_admission.reset())


def test_live_chat_blocks_workspace_mutation_until_release(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from langchain_core.messages import AIMessage

    from tripplanner import usage
    from tripplanner.graph import app_graph
    from tripplanner.web import trip_operations

    entered_model = threading.Event()
    release_model = threading.Event()

    def invoke(_state):  # type: ignore[no-untyped-def]
        entered_model.set()
        assert release_model.wait(timeout=2)
        return {"messages": [AIMessage(content="ready")], "current_agent": "trip"}

    monkeypatch.setattr(app_graph, "invoke", invoke)
    monkeypatch.setattr(usage, "is_over_cap", lambda _user_id: (False, {}))
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _request_id: (None, [], None))
    monkeypatch.setattr(api, "_save_chat", lambda *_args, **_kwargs: "trip-1")
    monkeypatch.setattr(trip_operations, "select", lambda *_args, **_kwargs: {"ok": True})
    asyncio.run(chat_admission.reset())

    def client() -> TestClient:
        result = _hosted(monkeypatch)
        result.cookies.set(oauth.SESSION_COOKIE, _user_token("google-owner"))
        return result

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(
                client().post,
                "/chat",
                json={"message": "plan goa", "request_id": "request-1"},
            )
            assert entered_model.wait(timeout=2)
            blocked = client().post(
                "/trip/select",
                json={"kind": "attraction", "name": "Fort Aguada"},
            )
            assert blocked.status_code == 409
            assert "active Assistant request" in blocked.json()["detail"]
            release_model.set()
            assert first.result(timeout=2).status_code == 200

        succeeded = client().post(
            "/trip/select",
            json={"kind": "attraction", "name": "Fort Aguada"},
        )
        assert succeeded.status_code == 200
        assert succeeded.json() == {"ok": True}
    finally:
        release_model.set()
        asyncio.run(chat_admission.reset())


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


def test_replay_lookup_enforces_separate_request_window(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CHAT_REPLAY_LOOKUPS_PER_MINUTE", "1")
    admission = ReplayLookupAdmission()

    async def scenario() -> None:
        await admission.check("user-1", "127.0.0.1")
        with pytest.raises(HTTPException, match="retry checks") as error:
            await admission.check("user-1", "127.0.0.1")
        assert error.value.status_code == 429

    asyncio.run(scenario())


def test_replay_access_and_workspace_changes_are_mutually_exclusive() -> None:
    admission = ChatAdmission()

    async def scenario() -> None:
        replay = await admission.acquire_replay_access("user-1")
        with pytest.raises(HTTPException, match="active Assistant request") as error:
            await admission.acquire_workspace_exclusive(["user-1"])
        assert error.value.status_code == 409
        await admission.release_replay_access(replay)

        workspace = await admission.acquire_workspace_exclusive(["user-1"])
        with pytest.raises(HTTPException, match="workspace update") as error:
            await admission.acquire("user-1", "127.0.0.1")
        assert error.value.status_code == 409
        with pytest.raises(HTTPException, match="workspace update"):
            await admission.acquire_replay_access("user-1")
        await admission.release_workspace_exclusive(workspace)

    asyncio.run(scenario())
