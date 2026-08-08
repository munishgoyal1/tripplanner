"""The receipt stream: one line per tool call whose work is verifiable."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from tripplanner import api
from tripplanner import usage as usage_mod
from tripplanner.graph import app_graph
from tripplanner.request_limits import chat_admission

_COMPARISON = json.dumps(
    {
        "decision_id": "dec_transport_lisbon_porto_2026_05_04",
        "subject": "Lisbon to Porto",
        "chosen": "Train",
        "priced": "full",
        "options": [{"id": "opt_train"}, {"id": "opt_air"}],
    }
)


def _events(text: str, name: str) -> list[dict]:
    frames = []
    for block in text.split("\n\n"):
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:]
        if event == name and data:
            frames.append(json.loads(data))
    return frames


@pytest.fixture
def streamed(monkeypatch) -> str:  # type: ignore[no-untyped-def]
    async def fake_stream(*_args, **_kwargs):
        for tool, output in (
            ("compare_transport_options", _COMPARISON),
            ("compare_transport_options", "Lisbon and Porto are too close to compare."),
            ("save_trip_context", "saved"),
        ):
            yield {"event": "on_tool_start", "name": tool, "run_id": tool, "data": {}}
            yield {
                "event": "on_tool_end",
                "name": tool,
                "run_id": tool,
                "data": {"output": output},
            }

    monkeypatch.setattr(app_graph, "astream_events", fake_stream)
    monkeypatch.setattr(api, "_completed_chat_request", lambda _request_id: None)
    monkeypatch.setattr(api, "_load_chat_request", lambda _request_id: (None, [], None))
    monkeypatch.setattr(api, "_save_chat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(usage_mod, "is_over_cap", lambda _user_id: (False, {}))
    asyncio.run(chat_admission.reset())
    try:
        response = TestClient(api.app).post(
            "/chat/stream",
            json={"user_id": "alice", "message": "plan porto", "request_id": "r-1"},
        )
    finally:
        asyncio.run(chat_admission.reset())
    assert response.status_code == 200
    return response.text


def test_only_verifiable_work_produces_a_receipt(streamed: str) -> None:
    receipts = _events(streamed, "receipt")

    assert len(receipts) == 1
    assert receipts[0]["text"] == "Compared 2 ways from Lisbon to Porto"
    assert receipts[0]["decision_id"] == "dec_transport_lisbon_porto_2026_05_04"
    assert receipts[0]["seq"] == 1
    assert receipts[0]["at"].count(":") == 1


def test_the_existing_tool_events_are_unchanged(streamed: str) -> None:
    tools = _events(streamed, "tool")

    assert [t["phase"] for t in tools] == ["start", "end"] * 3
    assert {t["name"] for t in tools} == {"compare_transport_options", "save_trip_context"}
