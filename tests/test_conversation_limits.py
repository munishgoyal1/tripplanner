from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from tripplanner import api, conversation_limits, usage
from tripplanner.conversation_limits import ConversationLimitError
from tripplanner.graph import app_graph
from tripplanner.tools import trip_planner
from tripplanner.web import oauth

_SECRET = "conversation-limit-test-secret"


@pytest.fixture(autouse=True)
def local_ledger(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr(conversation_limits.storage_cosmos, "is_enabled", lambda: False)
    for name in conversation_limits._ENV_NAMES.values():
        monkeypatch.setenv(name, "0")


def test_classifies_new_update_and_kickoff_continuation() -> None:
    assert conversation_limits.classify_conversation([], "Plan a trip to Goa", {}) == "new_trip"
    assert (
        conversation_limits.classify_conversation([], "Hello there", {})
        == "existing_trip_turn"
    )
    assert conversation_limits.classify_conversation(
        [],
        "Plan another trip to Jaipur",
        {"destination": "Goa"},
    ) == "new_trip"
    history = [
        HumanMessage(content="Plan a trip to Goa"),
        AIMessage(
            content="Please confirm",
            additional_kwargs={"ran_tools": ["request_trip_input"]},
        ),
    ]
    assert conversation_limits.classify_conversation(
        history,
        "Two adults from Mumbai",
        {},
    ) == "continuation"


def test_reservation_enforces_each_window_and_deduplicates_retry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CHAT_NEW_TRIP_LIMIT_DAILY", "2")
    monkeypatch.setenv("CHAT_NEW_TRIP_LIMIT_WEEKLY", "3")
    monkeypatch.setenv("CHAT_NEW_TRIP_LIMIT_LIFETIME", "4")
    now = datetime(2026, 8, 28, 12, tzinfo=UTC)

    assert conversation_limits.reserve(
        "new_trip", user_id="u1", request_id="r1", now=now
    )
    assert not conversation_limits.reserve(
        "new_trip", user_id="u1", request_id="r1", now=now
    )
    assert conversation_limits.reserve(
        "new_trip", user_id="u2", request_id="r2", now=now
    )
    with pytest.raises(ConversationLimitError) as error:
        conversation_limits.reserve(
            "new_trip", user_id="u3", request_id="r3", now=now
        )
    assert error.value.window == "daily"
    assert error.value.as_detail()["resets_at"] == "2026-08-29T00:00:00Z"

    next_day = datetime(2026, 8, 29, 12, tzinfo=UTC)
    assert conversation_limits.reserve(
        "new_trip", user_id="u3", request_id="r3", now=next_day
    )
    with pytest.raises(ConversationLimitError) as error:
        conversation_limits.reserve(
            "new_trip", user_id="u4", request_id="r4", now=next_day
        )
    assert error.value.window == "weekly"


def test_weekly_rollover_preserves_lifetime_limit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CHAT_EXISTING_TRIP_TURN_LIMIT_WEEKLY", "1")
    monkeypatch.setenv("CHAT_EXISTING_TRIP_TURN_LIMIT_LIFETIME", "2")

    assert conversation_limits.reserve(
        "existing_trip_turn",
        user_id="u1",
        request_id="r1",
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert conversation_limits.reserve(
        "existing_trip_turn",
        user_id="u1",
        request_id="r2",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    with pytest.raises(ConversationLimitError) as error:
        conversation_limits.reserve(
            "existing_trip_turn",
            user_id="u1",
            request_id="r3",
            now=datetime(2026, 9, 7, tzinfo=UTC),
        )
    assert error.value.window == "lifetime"
    assert error.value.resets_at is None


def test_continuation_does_not_write_ledger() -> None:
    assert not conversation_limits.reserve(
        "continuation", user_id="u1", request_id="r1"
    )
    assert conversation_limits.snapshot()["lifetime"]["categories"]["new_trip"][
        "used"
    ] == 0


def test_json_and_sse_reject_before_model_execution(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    monkeypatch.setenv("WEB_SESSION_SECRET", _SECRET)
    monkeypatch.setenv("CHAT_NEW_TRIP_LIMIT_DAILY", "1")
    monkeypatch.setattr(usage, "is_over_cap", lambda _user_id: (False, {}))
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _request_id: (None, [], None))
    monkeypatch.setattr(trip_planner, "load_active_trip_dict", lambda: None)

    def unexpected_model_call(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("quota rejection must happen before model execution")

    monkeypatch.setattr(app_graph, "invoke", unexpected_model_call)
    monkeypatch.setattr(app_graph, "astream_events", unexpected_model_call)
    conversation_limits.reserve(
        "new_trip", user_id="google-owner", request_id="seed"
    )

    client = TestClient(api.app)
    client.cookies.set(
        oauth.SESSION_COOKIE,
        oauth.make_session_token("google-owner", "Owner", "owner@example.com", ""),
    )
    for route in ("/chat", "/chat/stream"):
        response = client.post(
            route,
            json={"message": "Plan a trip to Goa", "request_id": f"blocked-{route}"},
        )
        assert response.status_code == 429
        assert response.json()["code"] == "conversation_limit_reached"
        assert response.json()["category"] == "new_trip"
        assert response.json()["window"] == "daily"
