"""Transport conformance tests for the shared chat-turn lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

import pytest
from langchain_core.messages import BaseMessage

from tripplanner.chat_turn import (
    AdmittedTurn,
    ChatTurnCoordinator,
    ChatTurnDependencies,
    TurnTerminal,
)

Transport = Literal["json", "sse"]


def _coordinator(
    calls: list[tuple[str, Any]],
    *,
    replay: dict[str, str] | None = None,
    over_cap: bool = False,
    reserve_error: Exception | None = None,
    save_result: str | None = "destination-trip",
    save: Callable[..., str | None] | None = None,
) -> ChatTurnCoordinator:
    async def acquire_replay(_user_id: str) -> str:
        calls.append(("acquire_replay", None))
        return "replay-permit"

    async def release_replay(permit: Any) -> None:
        calls.append(("release_replay", permit))

    async def check_replay() -> None:
        calls.append(("check_replay", None))

    async def repair_completed(_request_id: str | None, _replay: dict[str, str]) -> None:
        calls.append(("repair_completed", None))

    async def acquire_chat() -> str:
        calls.append(("acquire_chat", None))
        return "chat-permit"

    async def release_chat(permit: Any) -> None:
        calls.append(("release_chat", permit))

    async def reserve(_history: list[BaseMessage]) -> None:
        calls.append(("reserve", None))
        if reserve_error is not None:
            raise reserve_error

    def save_chat(*args: Any, **kwargs: Any) -> str | None:
        calls.append(("save_chat", (args, kwargs)))
        if save is not None:
            return save(*args, **kwargs)
        return save_result

    return ChatTurnCoordinator(
        ChatTurnDependencies(
            acquire_replay=acquire_replay,
            release_replay=release_replay,
            check_replay=check_replay,
            completed_request=lambda _request_id: replay,
            repair_completed=repair_completed,
            acquire_chat=acquire_chat,
            release_chat=release_chat,
            load_request=lambda _request_id: ("origin-trip", [], None),
            over_cap=lambda _user_id: (
                over_cap,
                {"cost_usd": 2.0, "cap_usd": 1.0},
            ),
            cap_message=lambda _usage: "Budget reached",
            reserve=reserve,
            limit_response=lambda exc: {"error": type(exc).__name__},
            save_chat=save_chat,
            auto_persist_needed=lambda _tools: False,
            auto_persist=lambda _reply: True,
            schedule_learning=lambda user_id, message: calls.append(
                ("schedule_learning", (user_id, message))
            ),
            record_operation=lambda *_args, **kwargs: calls.append(
                ("record_operation", kwargs)
            ),
            record_phase=lambda *_args, **kwargs: calls.append(("record_phase", kwargs)),
            event=lambda name, **fields: calls.append(("event", (name, fields))),
        )
    )


@pytest.mark.parametrize("transport", ["json", "sse"])
@pytest.mark.parametrize("terminal", ["replayed", "capped", "conversation_limited"])
def test_terminal_admission_matrix(transport: Transport, terminal: str) -> None:
    calls: list[tuple[str, Any]] = []
    replay = (
        {"reply": "Saved reply", "agent": "trip", "trip_id": "saved-trip"}
        if terminal == "replayed"
        else None
    )
    coordinator = _coordinator(
        calls,
        replay=replay,
        over_cap=terminal == "capped",
        reserve_error=RuntimeError("limited") if terminal == "conversation_limited" else None,
    )

    result = asyncio.run(
        coordinator.admit(
            started=1.0,
            transport=transport,
            user_id="owner",
            request_id="request-1",
            message="Plan Goa",
        )
    )

    assert isinstance(result, TurnTerminal)
    assert result.outcome == terminal
    assert ("release_replay", "replay-permit") in calls
    if terminal == "replayed":
        assert ("acquire_chat", None) not in calls
    else:
        assert ("release_chat", "chat-permit") in calls


@pytest.mark.parametrize("transport", ["json", "sse"])
def test_completion_matrix_preserves_destination_switch(transport: Transport) -> None:
    calls: list[tuple[str, Any]] = []
    coordinator = _coordinator(calls, save_result="new-destination")
    admitted = asyncio.run(
        coordinator.admit(
            started=1.0,
            transport=transport,
            user_id="owner",
            request_id="request-1",
            message="Switch to Kashmir",
        )
    )
    assert isinstance(admitted, AdmittedTurn)

    completed = asyncio.run(
        coordinator.finalize(
            admitted,
            message="Switch to Kashmir",
            reply="Kashmir is ready",
            agent="trip",
            tool_names={"create_trip_plan"},
            additional_kwargs={"ran_tools": ["create_trip_plan"]},
            proposal_only=False,
        )
    )
    asyncio.run(coordinator.close(admitted))

    assert completed.trip_id == "new-destination"
    assert ("schedule_learning", ("owner", "Switch to Kashmir")) in calls
    assert ("release_chat", "chat-permit") in calls
    operations = [value for name, value in calls if name == "record_operation"]
    assert operations[-1]["outcome"] == "completed"
    assert operations[-1]["transport"] == transport


@pytest.mark.parametrize("transport", ["json", "sse"])
def test_interrupted_save_matrix(transport: Transport) -> None:
    calls: list[tuple[str, Any]] = []

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("storage unavailable")

    coordinator = _coordinator(calls, save=fail_save)
    admitted = asyncio.run(
        coordinator.admit(
            started=1.0,
            transport=transport,
            user_id="owner",
            request_id="request-1",
            message="Plan Goa",
        )
    )
    assert isinstance(admitted, AdmittedTurn)

    persisted = asyncio.run(
        coordinator.persist_interrupted(
            admitted,
            message="Plan Goa",
            partial_reply="Partial",
            error=RuntimeError("model stopped"),
            tool_names={"create_trip_plan"},
        )
    )
    asyncio.run(coordinator.close(admitted))

    assert persisted is False
    events = [value for name, value in calls if name == "event"]
    expected_name = (
        "api_chat_stream_partial_save_error"
        if transport == "sse"
        else "api_chat_partial_save_error"
    )
    assert events[-1] == (
        expected_name,
        {"error": "OSError", "turn_error": "RuntimeError"},
    )
