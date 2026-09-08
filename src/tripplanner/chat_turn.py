"""Transport-neutral orchestration for one admitted chat turn."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

Transport = Literal["json", "sse"]


@dataclass(frozen=True)
class TurnTerminal:
    outcome: Literal["replayed", "capped", "conversation_limited"]
    reply: str = ""
    agent: str = "trip"
    trip_id: str | None = None
    response: Any = None


@dataclass
class AdmittedTurn:
    started: float
    transport: Transport
    user_id: str
    request_id: str | None
    permit: Any
    history_trip_id: str | None
    history: list[BaseMessage]
    base_history: list[BaseMessage]


@dataclass(frozen=True)
class CompletedTurn:
    reply: str
    agent: str
    trip_id: str | None


@dataclass
class ChatTurnDependencies:
    acquire_replay: Callable[[str], Awaitable[Any]]
    release_replay: Callable[[Any], Awaitable[None]]
    check_replay: Callable[[], Awaitable[None]]
    completed_request: Callable[[str | None], dict[str, str] | None]
    repair_completed: Callable[[str | None, dict[str, str]], Awaitable[None]]
    acquire_chat: Callable[[], Awaitable[Any]]
    release_chat: Callable[[Any], Awaitable[None]]
    load_request: Callable[
        [str | None], tuple[str | None, list[BaseMessage], dict[str, str] | None]
    ]
    over_cap: Callable[[str], tuple[bool, dict[str, Any]]]
    cap_message: Callable[[dict[str, Any]], str]
    reserve: Callable[[list[BaseMessage]], Awaitable[None]]
    limit_response: Callable[[BaseException], Any]
    save_chat: Callable[..., str | None]
    auto_persist_needed: Callable[[set[str]], bool]
    auto_persist: Callable[[str], bool]
    schedule_learning: Callable[[str, str], None]
    record_operation: Callable[..., None]
    record_phase: Callable[..., None]
    event: Callable[..., None]


class ChatTurnCoordinator:
    """Own admission, recovery, persistence, and finalization for both transports."""

    def __init__(self, dependencies: ChatTurnDependencies) -> None:
        self._deps = dependencies

    async def admit(
        self,
        *,
        started: float,
        transport: Transport,
        user_id: str,
        request_id: str | None,
        message: str,
    ) -> AdmittedTurn | TurnTerminal:
        deps = self._deps
        replay_permit = await deps.acquire_replay(user_id)
        permit: Any = None
        try:
            await deps.check_replay()
            replay = await asyncio.to_thread(deps.completed_request, request_id)
            if replay is not None:
                await deps.repair_completed(request_id, replay)
                deps.record_operation(
                    started, user_id=user_id, transport=transport, outcome="replayed"
                )
                return self._replay_terminal(replay)
            permit = await deps.acquire_chat()
        finally:
            await deps.release_replay(replay_permit)

        try:
            history_trip_id, history, replay = await asyncio.to_thread(
                deps.load_request, request_id
            )
            if replay is not None:
                await deps.release_chat(permit)
                permit = None
                deps.record_operation(
                    started, user_id=user_id, transport=transport, outcome="replayed"
                )
                return self._replay_terminal(replay)
            over, usage = deps.over_cap(user_id)
            if over:
                await deps.release_chat(permit)
                permit = None
                reply = deps.cap_message(usage)
                deps.event(
                    "api_chat_capped" if transport == "json" else "api_chat_stream_capped",
                    cost_usd=usage.get("cost_usd"),
                )
                deps.record_operation(
                    started, user_id=user_id, transport=transport, outcome="capped"
                )
                return TurnTerminal(outcome="capped", reply=reply, agent="cap")
            try:
                await deps.reserve(history)
            except Exception as exc:
                await deps.release_chat(permit)
                permit = None
                deps.record_operation(
                    started,
                    user_id=user_id,
                    transport=transport,
                    outcome="conversation_limited",
                    error=type(exc).__name__,
                )
                return TurnTerminal(
                    outcome="conversation_limited",
                    response=deps.limit_response(exc),
                )

            deps.record_phase(started, transport=transport, phase="admission")
            base_history = list(history)
            history.append(HumanMessage(content=message))
            return AdmittedTurn(
                started=started,
                transport=transport,
                user_id=user_id,
                request_id=request_id,
                permit=permit,
                history_trip_id=history_trip_id,
                history=history,
                base_history=base_history,
            )
        except Exception:
            if permit is not None:
                await deps.release_chat(permit)
            raise

    async def close(self, turn: AdmittedTurn | TurnTerminal) -> None:
        if isinstance(turn, AdmittedTurn) and turn.permit is not None:
            await self._deps.release_chat(turn.permit)
            turn.permit = None

    async def persist_interrupted(
        self,
        turn: AdmittedTurn,
        *,
        message: str,
        partial_reply: str,
        error: BaseException,
        tool_names: set[str],
    ) -> bool:
        failed = False
        try:
            await asyncio.to_thread(
                self._deps.save_chat,
                turn.history_trip_id,
                turn.base_history,
                [
                    HumanMessage(content=message),
                    AIMessage(content=partial_reply or "(interrupted)"),
                ],
                turn.request_id,
                False,
            )
        except Exception as save_error:
            failed = True
            self._deps.event(
                (
                    "api_chat_stream_partial_save_error"
                    if turn.transport == "sse"
                    else "api_chat_partial_save_error"
                ),
                error=type(save_error).__name__,
                turn_error=type(error).__name__,
            )
        return not failed

    async def finalize(
        self,
        turn: AdmittedTurn,
        *,
        message: str,
        reply: str,
        agent: str,
        tool_names: set[str],
        additional_kwargs: dict[str, Any],
        proposal_only: bool,
    ) -> CompletedTurn:
        finalization_started = time.monotonic()
        try:
            if not proposal_only and self._deps.auto_persist_needed(tool_names):
                await asyncio.to_thread(self._deps.auto_persist, reply)
            trip_id = await asyncio.to_thread(
                self._deps.save_chat,
                turn.history_trip_id,
                turn.base_history,
                [
                    HumanMessage(content=message),
                    AIMessage(content=reply, additional_kwargs=additional_kwargs),
                ],
                turn.request_id,
                True,
                agent,
                max(int(time.monotonic() - turn.started), 0),
            )
            if not proposal_only:
                self._deps.schedule_learning(turn.user_id, message)
        except Exception:
            self._deps.record_phase(
                finalization_started,
                transport=turn.transport,
                phase="finalization",
                status="error",
            )
            raise
        self._deps.record_phase(
            finalization_started,
            transport=turn.transport,
            phase="finalization",
        )
        self._deps.record_operation(
            turn.started,
            user_id=turn.user_id,
            transport=turn.transport,
            outcome="completed",
            **({"tool_calls": len(tool_names)} if tool_names else {}),
        )
        return CompletedTurn(reply=reply, agent=agent, trip_id=trip_id)

    @staticmethod
    def _replay_terminal(replay: dict[str, str]) -> TurnTerminal:
        return TurnTerminal(
            outcome="replayed",
            reply=replay["reply"],
            agent=replay["agent"],
            trip_id=replay["trip_id"] or None,
        )
