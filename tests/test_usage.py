"""Tests for src/tripplanner/usage.py — per-user monthly LLM cost cap."""

from __future__ import annotations

import importlib

import pytest

from tripplanner import usage as usage_mod


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    # Sandboxed local storage and a fresh env on every test.
    monkeypatch.setenv("TRIPPLANNER_HOME", str(tmp_path))
    monkeypatch.setattr("tripplanner.storage_cosmos.is_enabled", lambda: False)
    # Re-import to clear the module-level _DEFAULT_RATE cache (none currently,
    # but be safe if we add one later).
    importlib.reload(usage_mod)
    yield


def test_cost_for_known_model_uses_listed_rates():
    # gpt-4.1: 0.003 prompt / 0.012 completion per 1K tokens.
    cost = usage_mod.cost_for("gpt-4.1", prompt_tokens=1000, completion_tokens=1000)
    assert cost == pytest.approx(0.003 + 0.012)


def test_cost_for_unknown_model_uses_default_rate():
    cost = usage_mod.cost_for("never-heard-of-it", prompt_tokens=1000, completion_tokens=1000)
    # Default = 0.001 + 0.003.
    assert cost == pytest.approx(0.004)


def test_cost_for_mini_prefix_beats_parent_prefix():
    # gpt-4.1-mini must match before gpt-4.1.
    mini = usage_mod.cost_for("gpt-4.1-mini", prompt_tokens=1000, completion_tokens=1000)
    full = usage_mod.cost_for("gpt-4.1", prompt_tokens=1000, completion_tokens=1000)
    assert mini < full


def test_record_usage_persists_and_accumulates():
    usage_mod.record_usage("alice", model="gpt-4o-mini", prompt_tokens=500, completion_tokens=1500)
    doc1 = usage_mod.get_usage("alice")
    assert doc1["prompt_tokens"] == 500
    assert doc1["completion_tokens"] == 1500
    assert doc1["calls"] == 1
    assert doc1["cost_usd"] > 0

    usage_mod.record_usage("alice", model="gpt-4o-mini", prompt_tokens=200, completion_tokens=300)
    doc2 = usage_mod.get_usage("alice")
    assert doc2["prompt_tokens"] == 700
    assert doc2["completion_tokens"] == 1800
    assert doc2["calls"] == 2
    assert doc2["cost_usd"] > doc1["cost_usd"]


def test_get_usage_returns_zeros_for_new_user():
    doc = usage_mod.get_usage("nobody")
    assert doc["prompt_tokens"] == 0
    assert doc["completion_tokens"] == 0
    assert doc["cost_usd"] == 0.0
    assert doc["calls"] == 0


def test_usage_is_per_user():
    usage_mod.record_usage("alice", model="gpt-4o", prompt_tokens=1000, completion_tokens=1000)
    usage_mod.record_usage("bob", model="gpt-4o", prompt_tokens=2000, completion_tokens=2000)
    assert usage_mod.get_usage("alice")["calls"] == 1
    assert usage_mod.get_usage("bob")["calls"] == 1
    assert usage_mod.get_usage("alice")["prompt_tokens"] == 1000
    assert usage_mod.get_usage("bob")["prompt_tokens"] == 2000


def test_is_over_cap_false_under_cap(monkeypatch):
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "5")
    usage_mod.record_usage("alice", model="gpt-4o-mini", prompt_tokens=100, completion_tokens=100)
    over, _ = usage_mod.is_over_cap("alice")
    assert over is False


def test_is_over_cap_true_when_cost_exceeds(monkeypatch):
    # Tiny cap so a single small call trips it.
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "0.0001")
    usage_mod.record_usage("alice", model="gpt-4o", prompt_tokens=1000, completion_tokens=1000)
    over, doc = usage_mod.is_over_cap("alice")
    assert over is True
    assert doc["cost_usd"] >= 0.0001


def test_cap_disabled_when_zero_or_negative(monkeypatch):
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "0")
    usage_mod.record_usage("alice", model="gpt-4", prompt_tokens=100000, completion_tokens=100000)
    over, _ = usage_mod.is_over_cap("alice")
    assert over is False


def test_cap_message_contains_amounts(monkeypatch):
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "10")
    doc = {"month": "202606", "cost_usd": 12.5}
    msg = usage_mod.cap_message(doc)
    assert "$12.50" in msg
    assert "$10.00" in msg
    assert "202606" in msg


def test_get_cap_usd_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("MONTHLY_LLM_COST_CAP_USD", raising=False)
    assert usage_mod.get_cap_usd() == 20.0


def test_get_cap_usd_falls_back_on_bad_value(monkeypatch):
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "not-a-number")
    assert usage_mod.get_cap_usd() == 20.0


def test_record_usage_zero_tokens_still_records_call():
    # Some models return zero usage on a cached lookup; we still increment
    # ``calls`` so the metric is honest.
    usage_mod.record_usage("alice", model="gpt-4o", prompt_tokens=0, completion_tokens=0)
    doc = usage_mod.get_usage("alice")
    assert doc["calls"] == 1
    assert doc["cost_usd"] == 0.0


def test_usage_endpoint_returns_current_bucket(monkeypatch):
    from fastapi.testclient import TestClient

    from tripplanner.api import app

    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "5")
    usage_mod.record_usage("alice", model="gpt-4o", prompt_tokens=500, completion_tokens=500)
    client = TestClient(app)
    resp = client.get("/usage", params={"user_id": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "alice"
    assert body["calls"] == 1
    assert body["prompt_tokens"] == 500
    assert body["cap_usd"] == 5.0
    assert body["over_cap"] is False


def test_chat_endpoint_returns_cap_message_when_over(monkeypatch):
    from fastapi.testclient import TestClient

    from tripplanner import api

    # Cap so low any prior call would trip it; record a small call first.
    monkeypatch.setenv("MONTHLY_LLM_COST_CAP_USD", "0.0001")
    usage_mod.record_usage("alice", model="gpt-4o", prompt_tokens=1000, completion_tokens=1000)
    operations = []
    monkeypatch.setattr(
        api, "_record_chat_operation", lambda *_args, **kwargs: operations.append(kwargs)
    )
    client = TestClient(api.app)
    resp = client.post("/chat", json={"user_id": "alice", "message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent"] == "cap"
    assert "budget" in body["reply"].lower() or "reached" in body["reply"].lower()
    assert operations == [
        {"user_id": "alice", "transport": "json", "outcome": "capped"}
    ]


def test_completed_chat_request_replays_when_over_cap(monkeypatch):
    from fastapi.testclient import TestClient

    from tripplanner import api

    async def reject_admission(*_args, **_kwargs):
        raise AssertionError("completed replay reached chat admission")

    replay = {"reply": "Persisted reply", "agent": "trip", "trip_id": "goa"}
    operations = []
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: replay)
    monkeypatch.setattr(api, "acquire_chat", reject_admission)
    monkeypatch.setattr(
        api, "_record_chat_operation", lambda *_args, **kwargs: operations.append(kwargs)
    )
    monkeypatch.setattr(usage_mod, "is_over_cap", lambda _user_id: (True, {}))
    client = TestClient(api.app)

    response = client.post(
        "/chat",
        json={"user_id": "alice", "message": "plan goa", "request_id": "request-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Persisted reply",
        "agent": "trip",
        "trip_id": "goa",
    }
    assert operations == [
        {"user_id": "alice", "transport": "json", "outcome": "replayed"}
    ]


def test_completed_stream_request_replays_when_over_cap(monkeypatch):
    from fastapi.testclient import TestClient

    from tripplanner import api

    async def reject_admission(*_args, **_kwargs):
        raise AssertionError("completed replay reached chat admission")

    replay = {"reply": "Persisted reply", "agent": "trip", "trip_id": "goa"}
    operations = []
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: replay)
    monkeypatch.setattr(api, "acquire_chat", reject_admission)
    monkeypatch.setattr(
        api, "_record_chat_operation", lambda *_args, **kwargs: operations.append(kwargs)
    )
    monkeypatch.setattr(usage_mod, "is_over_cap", lambda _user_id: (True, {}))
    client = TestClient(api.app)

    response = client.post(
        "/chat/stream",
        json={"user_id": "alice", "message": "plan goa", "request_id": "request-1"},
    )

    assert response.status_code == 200
    assert '"reply": "Persisted reply"' in response.text
    assert '"agent": "trip"' in response.text
    assert operations == [
        {"user_id": "alice", "transport": "sse", "outcome": "replayed"}
    ]


def test_stream_surfaces_partial_turn_save_failure(monkeypatch):
    import asyncio

    from fastapi.testclient import TestClient

    from tripplanner import api
    from tripplanner.graph import app_graph
    from tripplanner.request_limits import chat_admission

    async def fail_stream(*_args, **_kwargs):
        raise RuntimeError("model interrupted")
        yield

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(app_graph, "astream_events", fail_stream)
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _request_id: (None, [], None))
    monkeypatch.setattr(api, "_save_chat", lambda *_args, **_kwargs: 1 / 0)
    monkeypatch.setattr(api, "app_event", lambda name, **fields: events.append((name, fields)))
    monkeypatch.setattr(usage_mod, "is_over_cap", lambda _user_id: (False, {}))
    asyncio.run(chat_admission.reset())

    try:
        response = TestClient(api.app).post(
            "/chat/stream",
            json={"user_id": "alice", "message": "plan goa", "request_id": "request-1"},
        )
    finally:
        asyncio.run(chat_admission.reset())

    assert response.status_code == 200
    assert "Trip changes may still have been applied" in response.text
    assert (
        "api_chat_stream_partial_save_error",
        {"error": "ZeroDivisionError", "turn_error": "RuntimeError"},
    ) in events


def test_sync_chat_retry_replaces_interrupted_attempt(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from langchain_core.messages import AIMessage

    from tripplanner import api
    from tripplanner.graph import app_graph
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store

    monkeypatch.setattr(chat_store, "_resolve_dir", lambda: tmp_path / "chats")
    calls = 0

    def invoke(_state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("model interrupted")
        return {"messages": [AIMessage(content="Goa is ready")], "current_agent": "trip"}

    monkeypatch.setattr(app_graph, "invoke", invoke)
    operations = []
    monkeypatch.setattr(
        api, "_record_chat_operation", lambda *_args, **kwargs: operations.append(kwargs)
    )
    client = TestClient(api.app)
    request = {
        "user_id": "sync-retry-user",
        "message": "plan goa",
        "request_id": "sync-retry-request",
    }

    with pytest.raises(RuntimeError, match="model interrupted"):
        client.post("/chat", json=request)
    response = client.post("/chat", json=request)

    assert response.status_code == 200
    assert response.json()["reply"] == "Goa is ready"
    assert len(operations) == 2
    error_operation = operations[0]
    exception = error_operation.pop("exception")
    assert isinstance(exception, RuntimeError)
    assert str(exception) == "model interrupted"
    assert error_operation == {
        "user_id": "sync-retry-user",
        "transport": "json",
        "outcome": "error",
    }
    assert operations[1] == {
        "user_id": "sync-retry-user",
        "transport": "json",
        "outcome": "completed",
    }
    set_user_id("anon")
    assert [
        {"role": row["role"], "text": row["text"]}
        for row in chat_store.transcript(None)
    ] == [
        {"role": "user", "text": "plan goa"},
        {"role": "assistant", "text": "Goa is ready"},
    ]
    set_user_id("local")



