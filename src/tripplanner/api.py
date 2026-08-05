"""FastAPI server for the personal assistant.

This is the **frontend-agnostic backend** that also serves the built React SPA
(``frontend/dist``) at the root origin. The SPA is just a client of these
endpoints — no UI framework is imported here. The trip-panel data contract
lives in the pure-Python ``web/trip_view.py`` and is served verbatim by
``GET /trip/view``.

Endpoints
---------
* ``POST /chat``         — one-shot reply (no streaming), handy for scripts.
* ``POST /chat/stream``  — Server-Sent Events: tokens + tool steps in real time.
* ``GET  /trip/view``    — the trip-panel view-model JSON.
* ``POST /trip/select``  — add a hotel/attraction to the active trip.
* ``GET  /health``       — liveness probe.

Per-user conversation history is kept in a small in-memory store keyed by the
``user_id`` the client sends (the SPA generates a stable ``web-<uuid>`` and
stores it in ``localStorage``). Trip state itself is already persisted per user
by ``trip_planner`` (local JSON or Cosmos), so this store only holds the
in-flight chat turns for context.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from tripplanner import config as _config  # noqa: F401  -- import triggers load_dotenv()
from tripplanner.chat_interactions import extract_input_request
from tripplanner.observability import app_event, model_rate_limit_fields, setup_logging
from tripplanner.request_identity import (
    is_anonymous_id,
    is_hosted,
    require_guest_capability,
    require_signed_user,
    resolve_user_id,
)
from tripplanner.request_limits import (
    acquire_chat,
    acquire_replay_access,
    acquire_workspace_exclusive,
    check_replay_lookup,
    release_chat,
    release_replay_access,
    release_workspace_exclusive,
)
from tripplanner.user_context import set_user_id
from tripplanner.web import oauth

setup_logging()

app = FastAPI(title="Personal Assistant API", version="0.1.0")

_CHAT_GRAPH_RECURSION_LIMIT = 24

# CORS — the SPA runs on a different origin in dev (Vite :5173). Override the
# allowed origins in production via WEB_ALLOWED_ORIGINS (comma-separated).
# Cookie-based OAuth needs credentials, which browsers forbid alongside the
# "*" wildcard — so only enable credentials when explicit origins are set.
# (In dev the SPA talks to the API through the Vite proxy, i.e. same-origin,
# so credentials flow without CORS anyway.)
_origins = [o.strip() for o in os.getenv("WEB_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
_allow_credentials = _origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _set_request_user(request: Request, claimed_user_id: str = "local") -> str:
    user_id = resolve_user_id(request, claimed_user_id)
    set_user_id(user_id)
    return user_id


def _best_effort_plan_reply() -> tuple[str, int]:
    from tripplanner.tools.trip_planner import (
        load_active_trip_dict,
        planning_completion_gaps,
    )

    try:
        trip = load_active_trip_dict() or {}
        gaps = planning_completion_gaps(trip)
    except Exception:
        trip = {}
        gaps = []
    destination = str(trip.get("destination") or "your trip").strip()
    itinerary = trip.get("day_wise_itinerary")
    if not isinstance(itinerary, list) or not itinerary:
        return (
            "Planning reached its safety limit before a usable itinerary was saved. "
            "Please retry with a shorter trip scope.",
            len(gaps),
        )
    reply = f"I saved the best available {destination} itinerary."
    if gaps:
        reply += " It is usable, but these details still need refinement: " + " ".join(gaps)
    return reply, len(gaps)


@app.middleware("http")
async def _strip_api_prefix(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Let the SPA call ``/api/...`` in production the same way it does in dev.

    The API routes live at the root (``/chat``, ``/trip/view``, ...). In dev the
    Vite proxy rewrites ``/api`` away; in production (single origin) we do the
    same rewrite here so one build works in both places.
    """
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)

# Per-user chat history is persisted per active trip via ``web.chat_store`` so
# the conversation + itinerary summary survive a browser refresh and follow
# saved-trip switches. These helpers wrap the load/save dance for both chat
# endpoints (sync and streaming).
def _load_chat() -> tuple[str | None, list[BaseMessage]]:
    """Return (active_trip_id, message history) for the current user."""
    from tripplanner.tools.trip_planner import active_trip_id
    from tripplanner.web import chat_store

    tid = active_trip_id()
    return tid, chat_store.load(tid)


def _load_chat_request(
    request_id: str | None,
) -> tuple[str | None, list[BaseMessage], dict[str, str] | None]:
    """Load retry-aware history and any already completed operation result."""
    from tripplanner.tools.trip_planner import active_trip_id
    from tripplanner.web import chat_store

    tid = active_trip_id()
    chat_store.reconcile_general(tid)
    replay = chat_store.completed_operation(tid, request_id)
    return tid, chat_store.load_for_request(tid, request_id), replay


def _completed_chat_request(request_id: str | None) -> dict[str, str] | None:
    from tripplanner.web import chat_store

    return chat_store.completed_request(request_id)


async def _repair_completed_chat(
    request_id: str | None, replay: dict[str, str]
) -> None:
    if not request_id:
        return
    from tripplanner.web import chat_store

    try:
        await asyncio.to_thread(chat_store.ensure_completed_turn, request_id, replay)
    except Exception as exc:
        app_event("api_chat_replay_repair_error", error=type(exc).__name__)


def _save_chat(
    tid_before: str | None,
    base_history: list[BaseMessage],
    completed_turn: list[BaseMessage],
    request_id: str | None = None,
    completed: bool = True,
    agent: str = "trip",
) -> str | None:
    """Persist the turn under the trip that's active *after* the turn.

    Handles three transitions (see ``chat_store.persist_turn``): no change,
    first-trip creation (migrate the pre-trip conversation), and a mid-chat
    destination switch (Mexico → Kashmir) where the new trip starts a fresh
    chat seeded with a distilled carryover note. Returns the active trip id.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools.trip_planner import active_trip_id
    from tripplanner.web import chat_carryover, chat_store

    tid_after = active_trip_id()

    carryover = ""
    is_switch = (
        tid_before is not None
        and tid_after is not None
        and tid_after != tid_before
    )
    if is_switch and not chat_store.transcript(tid_after):
        # Brand-new destination chat: distil portable context from the prior
        # conversation so the fresh chat isn't cold. Best-effort (LLM).
        prev_dest = trip_planner.saved_trip_destination(tid_before or "")
        active = trip_planner.load_active_trip_dict() or {}
        new_dest = str(active.get("destination") or "")
        carryover = chat_carryover.distill(base_history, prev_dest, new_dest)

    return chat_store.persist_turn(
        tid_before,
        tid_after,
        base_history,
        completed_turn,
        carryover,
        request_id=request_id,
        completed=completed,
        agent=agent,
    )


# Fire-and-forget passive-learning sweeps. Keep strong refs so the event loop
# doesn't garbage-collect a running task before it finishes.
_BG_TASKS: set[asyncio.Task] = set()


def _schedule_learning_sweep(user_id: str, message: str) -> None:
    """Run the post-turn passive-learning sweep without blocking the response.

    The extractor makes a blocking LLM call, so it runs in a worker thread; the
    user's ``user_id`` is re-bound inside the thread (ContextVars don't cross
    threads). Best-effort — all failures are swallowed.
    """
    def _worker() -> None:
        from tripplanner.tools import passive_learning, profile_summary
        from tripplanner.user_context import set_user_id

        set_user_id(user_id)
        passive_learning.learn_from_message(message)
        # Refresh the system-authored profile summary. Gated internally by a
        # durable-facts digest, so this is a no-op (no LLM call) when nothing
        # durable changed — including trip-scoped one-offs.
        profile_summary.update_summary()

    try:
        task = asyncio.create_task(asyncio.to_thread(_worker))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except RuntimeError:
        # No running loop (e.g. a sync test harness) — run inline best-effort.
        _worker()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    user_id: str = "local"
    proposal_only: bool = False
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    agent: str
    trip_id: str | None = None


class SelectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"
    start_day: int | None = None
    end_day: int | None = None
    day: int | None = None
    source_day: int | None = None
    source_stop: int | None = None
    replace_stay: bool = True


class DeselectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"
    day: int | None = None
    stop: int | None = None
    all_occurrences: bool = True


class TripIdRequest(BaseModel):
    trip_id: str
    user_id: str = "local"


class UserRequest(BaseModel):
    user_id: str = "local"


class StopBookedRequest(BaseModel):
    day: int
    name: str
    booked: bool
    user_id: str = "local"


class PreferencesRequest(BaseModel):
    user_id: str = "local"
    # Editable subset of the structured preferences. All optional — only
    # provided keys are merged (additive, never wiping unspecified fields).
    display_name: str | None = None
    home_city: str | None = None
    home_country: str | None = None
    trip_style: str | None = None
    budget_level: str | None = None
    flight_class: str | None = None
    prefer_direct_flights: bool | None = None
    hotel_star_rating_min: int | None = None
    dietary: list[str] | None = None
    interests: list[str] | None = None
    dislikes: list[str] | None = None
    planning_mode: Literal["direct", "interactive"] | None = None
    # Free-text "About me" blurb. When provided and changed, the backend runs
    # the LLM extractor and additively overlays the structured fields it finds.
    about_me: str | None = None
    # System-authored profile summary. When provided, it's stored verbatim
    # (user correction / reset via empty string); not the same as about_me.
    profile_summary: str | None = None
    profile_summary_updated_at: str | None = None


class PrivacyActionRequest(BaseModel):
    user_id: str = "local"
    action: Literal["delete_trip_history", "clear_all_data", "delete_account"]
    # For destructive actions we require explicit typed confirmation text.
    confirm_text: str = ""


class GuestMigrateRequest(BaseModel):
    user_id: str  # the authenticated identity to migrate INTO
    guest_id: str  # the guest web-<uuid> identity to migrate FROM


class ExportEmailRequest(BaseModel):
    user_id: str = "local"
    email: str
    include_photos: bool = True
    include_map_circuit: bool = True
    template: Literal["minimal", "detailed", "family"] = "detailed"
    request_id: str = Field(min_length=1, max_length=128)


def _record_chat_operation(
    started: float,
    *,
    user_id: str,
    transport: Literal["json", "sse"],
    outcome: Literal["completed", "replayed", "capped", "error"],
    error: str | None = None,
    exception: BaseException | None = None,
) -> None:
    error_name = error or (type(exception).__name__ if exception else None)
    model_fields = (
        model_rate_limit_fields(exception, _config.get_settings().azure_openai_deployment)
        if exception
        else {}
    )
    app_event(
        "chat_operation",
        user_id=user_id,
        transport=transport,
        outcome=outcome,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        **({"error": error_name} if error_name else {}),
        **model_fields,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    from tripplanner.graph import app_graph
    from tripplanner.usage import cap_message, is_over_cap

    started = time.monotonic()
    user_id = _set_request_user(request, req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    try:
        replay_permit = await acquire_replay_access(user_id)
    except Exception as exc:
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="json",
            outcome="error",
            error=type(exc).__name__,
        )
        raise
    try:
        await check_replay_lookup(request, user_id)
        replay = await asyncio.to_thread(_completed_chat_request, req.request_id)
        if replay is not None:
            await _repair_completed_chat(req.request_id, replay)
            _record_chat_operation(
                started, user_id=user_id, transport="json", outcome="replayed"
            )
            return ChatResponse(
                reply=replay["reply"],
                agent=replay["agent"],
                trip_id=replay["trip_id"] or None,
            )
        permit = await acquire_chat(request, user_id)
    except Exception as exc:
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="json",
            outcome="error",
            error=type(exc).__name__,
        )
        raise
    finally:
        await release_replay_access(replay_permit)
    try:
        history_tid, history, replay = await asyncio.to_thread(
            _load_chat_request, req.request_id
        )
        if replay is not None:
            _record_chat_operation(
                started, user_id=user_id, transport="json", outcome="replayed"
            )
            return ChatResponse(
                reply=replay["reply"],
                agent=replay["agent"],
                trip_id=replay["trip_id"] or None,
            )
        over, usage = is_over_cap(user_id)
        if over:
            msg = cap_message(usage)
            app_event("api_chat_capped", cost_usd=usage.get("cost_usd"))
            _record_chat_operation(
                started, user_id=user_id, transport="json", outcome="capped"
            )
            return ChatResponse(reply=msg, agent="cap")

        base_history = list(history)
        history.append(HumanMessage(content=req.message))
        try:
            result = await asyncio.to_thread(
                app_graph.invoke,
                {
                    "messages": history,
                    "current_agent": "",
                    "proposal_only": req.proposal_only,
                },
            )
        except Exception:
            try:
                await asyncio.to_thread(
                    _save_chat,
                    history_tid,
                    base_history,
                    [
                        HumanMessage(content=req.message),
                        AIMessage(content="(interrupted)"),
                    ],
                    req.request_id,
                    False,
                )
            except Exception:
                pass
            raise

        reply = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                reply = msg.content
                break
        from tripplanner.hallucination_critic import critique

        issues = critique(reply, result.get("messages", []))
        if issues:
            app_event("hallucination_critic", issues=len(issues), claims=issues)
        completed_turn = [HumanMessage(content=req.message), AIMessage(content=reply)]
        agent = result.get("current_agent", "unknown")
        tid_after = await asyncio.to_thread(
            _save_chat,
            history_tid,
            base_history,
            completed_turn,
            req.request_id,
            True,
            agent,
        )
        if not req.proposal_only:
            _schedule_learning_sweep(user_id, req.message)

        app_event("api_chat_response", reply_length=len(reply))
        _record_chat_operation(
            started, user_id=user_id, transport="json", outcome="completed"
        )
        return ChatResponse(
            reply=reply, agent=agent, trip_id=tid_after
        )
    except Exception as exc:
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="json",
            outcome="error",
            exception=exc,
        )
        raise
    finally:
        await release_chat(permit)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _summarize_tool_input(raw: Any, max_len: int = 160) -> str:
    """Render a one-line preview of a tool's input for the SSE 'tool' event.

    Keeps the panel chatty ("running search_hotels(city='Paris', nights=5)...")
    without flooding the wire with the full payload.
    """
    if raw is None:
        return ""
    payload = raw.get("input") if isinstance(raw, dict) and "input" in raw else raw
    if isinstance(payload, dict):
        parts = []
        for k, v in payload.items():
            if isinstance(v, (list, tuple, dict)):
                vs = json.dumps(v, ensure_ascii=False, default=str)
            else:
                vs = str(v)
            if len(vs) > 40:
                vs = vs[:37] + "..."
            parts.append(f"{k}={vs}")
        text = ", ".join(parts)
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            text = str(payload)
    if len(text) > max_len:
        text = text[: max_len - 1] + "\u2026"
    return text


# ---------------------------------------------------------------------------
# Itinerary safety net — direct parse + persist when agent skips the tool call
# ---------------------------------------------------------------------------
_DAY_HDR = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|\*{1,2})?[Dd]ay\s+(\d+)"
    r"(?:\s*[-\u2013\u2014:·]\s*([^\n\*]{0,80}))?",
)
_BOLD = re.compile(r"\*\*([^\*\n]{3,60})\*\*")


def _auto_persist_itinerary(reply: str) -> None:
    """If the agent's reply describes a multi-day itinerary but never called
    update_trip_plan, parse a minimal structure and persist it directly so the
    Itinerary panel is never left blank.

    Deliberately lenient — only requires 2+ day headers.  The agent's richer
    structured call (when it behaves) will overwrite this with better data.
    """
    matches = list(_DAY_HDR.finditer(reply))
    if len(matches) < 2:
        return  # not a day-wise reply

    from tripplanner.tools.trip_planner import update_trip_plan as _utp

    days: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        day_num = int(m.group(1))
        raw_title = (m.group(2) or "").strip().strip("*_ ")
        title = raw_title[:80] if raw_title else f"Day {day_num}"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(reply)
        chunk = reply[start:end].strip()
        # Collect bolded place names as stops (agent usually bolds them)
        stop_names = _BOLD.findall(chunk)
        stops = [
            {"name": n.strip(), "kind": "attraction"}
            for n in dict.fromkeys(stop_names)  # dedup, preserve order
            if n.strip()
        ][:6]
        days.append({
            "day": day_num,
            "date": "",
            "title": title,
            "summary": chunk[:250].replace("\n", " "),
            "stops": stops,
        })

    try:
        _utp.invoke({"updates_json": json.dumps({"day_wise_itinerary": days})})
    except Exception:
        pass  # best-effort; never crash the response path


def _should_auto_persist_itinerary(tool_names_called: set[str]) -> bool:
    return (
        "create_trip_plan" in tool_names_called
        and "update_trip_plan" not in tool_names_called
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply, so the SPA gets live typing and
    tool-progress over a plain HTTP stream.
    """
    from tripplanner.graph import app_graph
    from tripplanner.usage import cap_message, is_over_cap

    started = time.monotonic()
    user_id = _set_request_user(request, req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))

    try:
        replay_permit = await acquire_replay_access(user_id)
    except Exception as exc:
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="sse",
            outcome="error",
            error=type(exc).__name__,
        )
        raise
    try:
        await check_replay_lookup(request, user_id)
        replay = await asyncio.to_thread(_completed_chat_request, req.request_id)
        if replay is not None:
            await _repair_completed_chat(req.request_id, replay)

            async def _replay():
                yield _sse("token", {"text": replay["reply"]})
                _record_chat_operation(
                    started, user_id=user_id, transport="sse", outcome="replayed"
                )
                yield _sse(
                    "done",
                    {
                        "reply": replay["reply"],
                        "agent": replay["agent"],
                        "trip_id": replay["trip_id"] or None,
                    },
                )

            return StreamingResponse(
                _replay(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        permit = await acquire_chat(request, user_id)
    except Exception as exc:
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="sse",
            outcome="error",
            error=type(exc).__name__,
        )
        raise
    finally:
        await release_replay_access(replay_permit)
    try:
        history_tid, history, replay = await asyncio.to_thread(
            _load_chat_request, req.request_id
        )
        if replay is not None:
            async def _replay_after_admission():
                yield _sse("token", {"text": replay["reply"]})
                _record_chat_operation(
                    started, user_id=user_id, transport="sse", outcome="replayed"
                )
                yield _sse(
                    "done",
                    {
                        "reply": replay["reply"],
                        "agent": replay["agent"],
                        "trip_id": replay["trip_id"] or None,
                    },
                )

            return StreamingResponse(
                _replay_after_admission(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                background=BackgroundTask(release_chat, permit),
            )
        base_history = list(history)
        history.append(HumanMessage(content=req.message))
    except Exception as exc:
        await release_chat(permit)
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="sse",
            outcome="error",
            error=type(exc).__name__,
        )
        raise

    try:
        over, usage = is_over_cap(user_id)
    except Exception as exc:
        await release_chat(permit)
        _record_chat_operation(
            started,
            user_id=user_id,
            transport="sse",
            outcome="error",
            error=type(exc).__name__,
        )
        raise
    if over:
        msg = cap_message(usage)
        app_event("api_chat_stream_capped", cost_usd=usage.get("cost_usd"))

        async def _capped():
            yield _sse("token", {"text": msg})
            _record_chat_operation(
                started, user_id=user_id, transport="sse", outcome="capped"
            )
            yield _sse("done", {"reply": msg, "agent": "cap"})

        return StreamingResponse(
            _capped(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(release_chat, permit),
        )

    async def gen():
        reply_parts: list[str] = []
        tool_starts: dict[str, float] = {}
        # Capture tool message outputs so we can fact-check the agent's final
        # reply against them (hallucination critic).
        tool_outputs: list[ToolMessage] = []
        tool_names_called: set[str] = set()  # track which tools fired this turn
        yield _sse("progress", {"stage": "thinking"})
        try:
            async for ev in app_graph.astream_events(
                {
                    "messages": history,
                    "current_agent": "",
                    "proposal_only": req.proposal_only,
                },
                config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT},
                version="v2",
            ):
                kind = ev.get("event")
                name = ev.get("name", "")
                run_id = ev.get("run_id", "")
                data = ev.get("data", {}) or {}
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        reply_parts.append(text)
                        yield _sse("token", {"text": text})
                elif kind == "on_tool_start":
                    tool_starts[run_id] = time.monotonic()
                    tool_names_called.add(name)
                    args_preview = _summarize_tool_input(data.get("input"))
                    yield _sse("tool", {
                        "name": name,
                        "phase": "start",
                        "args": args_preview,
                    })
                elif kind == "on_tool_end":
                    tool_started = tool_starts.pop(run_id, None)
                    duration_ms = (
                        int((time.monotonic() - tool_started) * 1000)
                        if tool_started
                        else None
                    )
                    payload: dict[str, Any] = {"name": name, "phase": "end"}
                    if duration_ms is not None:
                        payload["duration_ms"] = duration_ms
                    output = data.get("output")
                    input_request = extract_input_request(output)
                    if input_request is not None:
                        yield _sse("input_request", input_request)
                    if output is not None:
                        # ToolNode wraps the result in a ToolMessage; the raw
                        # @tool may also surface a plain string.
                        if isinstance(output, str):
                            tool_outputs.append(ToolMessage(content=output, tool_call_id=name))
                        else:
                            content = getattr(output, "content", None)
                            if content is not None:
                                tool_outputs.append(
                                    ToolMessage(content=content, tool_call_id=name)
                                )
                    yield _sse("tool", payload)
                    yield _sse("progress", {"stage": "reviewing"})
        except GraphRecursionError:
            reply, gap_count = await asyncio.to_thread(_best_effort_plan_reply)
            app_event(
                "api_chat_stream_budget_exhausted",
                completion_gap_count=gap_count,
            )
            reply_parts.append(reply)
            yield _sse("token", {"text": reply})
        except Exception as exc:  # surface a clean error to the client
            app_event("api_chat_stream_error", error=type(exc).__name__)
            # Persist whatever we have so a tool side-effect during the turn
            # (e.g. a freshly created trip) doesn't leave the conversation
            # orphaned — otherwise the active trip exists with an empty chat
            # that vanishes on refresh.
            partial = "".join(reply_parts)
            completed_turn = [
                HumanMessage(content=req.message),
                AIMessage(content=partial or "(interrupted)"),
            ]
            partial_save_failed = False
            try:
                _save_chat(
                    history_tid,
                    base_history,
                    completed_turn,
                    req.request_id,
                    False,
                )
            except Exception as save_exc:
                partial_save_failed = True
                app_event(
                    "api_chat_stream_partial_save_error",
                    error=type(save_exc).__name__,
                    turn_error=type(exc).__name__,
                )
            _record_chat_operation(
                started,
                user_id=user_id,
                transport="sse",
                outcome="error",
                exception=exc,
            )
            message = "The assistant hit an error. Please retry."
            if partial_save_failed:
                message = (
                    "The assistant hit an error, and the interrupted conversation could not "
                    "be saved. Trip changes may still have been applied. Please retry."
                )
            yield _sse("error", {"message": message})
            return

        reply = "".join(reply_parts)
        yield _sse("progress", {"stage": "saving"})
        # Hallucination critic: log unverified prices/times/URLs as telemetry
        # only (internal QA signal — not surfaced to the user).
        from tripplanner.hallucination_critic import critique

        issues = critique(reply, tool_outputs)
        if issues:
            app_event("hallucination_critic", issues=len(issues), claims=issues)
        completed_turn = [HumanMessage(content=req.message), AIMessage(content=reply)]
        # Safety net: if the agent described a day-wise itinerary but never
        # called update_trip_plan, parse the reply and persist it directly so
        # the Itinerary panel is never left blank.
        if not req.proposal_only and _should_auto_persist_itinerary(tool_names_called):
            await asyncio.to_thread(_auto_persist_itinerary, reply)
        try:
            tid_after = await asyncio.to_thread(
                _save_chat,
                history_tid,
                base_history,
                completed_turn,
                req.request_id,
            )
        except Exception as exc:
            app_event("api_chat_stream_save_error", error=type(exc).__name__)
            _record_chat_operation(
                started,
                user_id=user_id,
                transport="sse",
                outcome="error",
                error=type(exc).__name__,
            )
            yield _sse(
                "error",
                {
                    "message": (
                        "The reply completed but its transcript could not be saved. "
                        "Please retry."
                    )
                },
            )
            return
        if not req.proposal_only:
            _schedule_learning_sweep(user_id, req.message)
        app_event("api_chat_stream_done", reply_length=len(reply))
        _record_chat_operation(
            started, user_id=user_id, transport="sse", outcome="completed"
        )
        yield _sse("done", {"reply": reply, "agent": "trip", "trip_id": tid_after})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(release_chat, permit),
    )


@app.get("/chat/history")
async def chat_history(request: Request, user_id: str = "local", trip_id: str = "") -> dict:
    """The persisted transcript for the user's *currently active* trip.

    Lets the SPA restore the conversation + itinerary summary after a refresh,
    and load the right conversation when the user switches saved trips.
    """
    from tripplanner.tools.trip_planner import active_trip_id
    from tripplanner.web import chat_store

    _set_request_user(request, user_id)
    tid = trip_id.strip() or await asyncio.to_thread(active_trip_id) or ""
    rows = await asyncio.to_thread(chat_store.transcript, tid)
    return {"trip_id": tid, "messages": rows}


@app.get("/trip/view")
async def trip_view_endpoint(
    request: Request,
    background: BackgroundTasks,
    user_id: str = "local",
    focus_kind: str = "",
    focus_name: str = "",
    focus_day: int | None = None,
    focus_stop: int | None = None,
) -> dict:
    """Frontend-agnostic trip-panel view-model with optional occurrence focus."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    focus = (
        {
            "kind": focus_kind,
            "name": focus_name,
            **({"day": focus_day} if focus_day is not None else {}),
            **({"stop": focus_stop} if focus_stop is not None else {}),
        }
        if focus_name
        else None
    )
    view = await asyncio.to_thread(trip_operations.build_view, focus)
    # Warm the destination-guide dataset after responding so the first city/kind
    # switch is instant while the user is still reading the itinerary.
    if focus is None:
        background.add_task(trip_operations.warm_guide)
    return view


@app.get("/trip/places")
async def trip_places_endpoint(
    request: Request,
    user_id: str = "local",
    city: str = "",
    kind: str = "",
    query: str = "",
    cursor: str = "",
    limit: int = 6,
    focus_kind: str = "",
    focus_name: str = "",
) -> dict:
    """Cursor-paged destination-guide place discovery (Lab 13).

    Filters the balanced place pool by ``city``/``kind``/``query`` and returns one
    lightweight page plus counts and available filter values. With ``focus_name``
    set, returns same-city, same-kind alternatives to the focused place.
    """
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(
        trip_operations.paged_places,
        city=city or None,
        kind=kind or None,
        query=query or None,
        cursor=cursor or None,
        limit=limit,
        focus_kind=focus_kind or None,
        focus_name=focus_name or None,
    )


@app.get("/maps/config")
async def maps_config_endpoint() -> dict:
    """Expose whether the interactive map is enabled + its browser key.

    The key is a referrer-restricted browser key (see ``config.py``); returning
    it here is the standard pattern for the Maps JavaScript API. Empty key →
    ``enabled: false`` and the SPA hides the map panel.
    """
    from tripplanner.config import get_settings

    key = get_settings().google_maps_browser_key or ""
    return {"enabled": bool(key), "key": key}


@app.get("/analytics/config")
async def analytics_config_endpoint() -> dict:
    """Expose the public GA4 id only for the production environment."""
    import os
    import re

    from tripplanner.config import get_settings

    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    measurement_id = get_settings().google_analytics_measurement_id.strip().upper()
    enabled = environment in {"prod", "production"} and bool(
        re.fullmatch(r"G-[A-Z0-9]+", measurement_id)
    )
    return {"enabled": enabled, "measurement_id": measurement_id if enabled else ""}


@app.get("/trip/map")
async def trip_map_endpoint(request: Request, user_id: str = "local") -> dict:
    """Interactive-map view-model: geocoded, day-tagged pins + route bands."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_map)


@app.get("/destination/overview")
async def destination_overview_endpoint(
    request: Request,
    destination: str = "",
    user_id: str = "local",
    news: bool = True,
) -> dict:
    """Destination-level overview (photos, key attractions, reviews, news).

    When ``destination`` is omitted, falls back to the active trip's
    destination so the SPA can show "about the place" before any selections.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.web import trip_view

    _set_request_user(request, user_id)
    if not destination:
        trip = trip_planner.load_active_trip_dict()
        destination = str((trip or {}).get("destination") or "")
    return await asyncio.to_thread(
        trip_view.build_destination_overview, destination, include_news=news
    )



@app.post("/trip/select")
async def trip_select(req: SelectRequest, request: Request) -> dict:
    """Add a hotel/attraction to the active trip (the SPA's 'Add to trip')."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.select,
            req.kind,
            req.name,
            start_day=req.start_day,
            end_day=req.end_day,
            day=req.day,
            source_day=req.source_day,
            source_stop=req.source_stop,
            replace_stay=req.replace_stay,
        )
    finally:
        await release_workspace_exclusive(workspace)


@app.post("/trip/deselect")
async def trip_deselect(req: DeselectRequest, request: Request) -> dict:
    """Remove a hotel/attraction from the active trip (the SPA's 'Remove')."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.deselect,
            req.kind,
            req.name,
            day=req.day,
            stop=req.stop,
            all_occurrences=req.all_occurrences,
        )
    finally:
        await release_workspace_exclusive(workspace)


@app.get("/trip/itinerary")
async def trip_itinerary_endpoint(request: Request, user_id: str = "local") -> dict:
    """Structured day-by-day itinerary view-model (the Itinerary tab)."""
    from tripplanner.web import trip_operations

    _set_request_user(request, user_id)
    return await asyncio.to_thread(trip_operations.build_itinerary)


@app.post("/trip/stop/booked")
async def trip_stop_booked(req: StopBookedRequest, request: Request) -> dict:
    """Toggle one itinerary stop's booked flag (the Itinerary checkbox)."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(
            trip_operations.set_stop_booked, req.day, req.name, req.booked
        )
    finally:
        await release_workspace_exclusive(workspace)


@app.get("/trips")
async def trips_list(request: Request, user_id: str = "local") -> dict:
    """All saved trips for the user (the SPA's 'My trips' switcher)."""
    from tripplanner.tools import trip_planner

    _set_request_user(request, user_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"trips": trips}


@app.post("/trips/switch")
async def trips_switch(req: TripIdRequest, request: Request) -> dict:
    """Make a saved trip active (auto-saving whatever was active) and return
    the refreshed trip-panel view."""
    from tripplanner.web import trip_operations

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        return await asyncio.to_thread(trip_operations.switch_trip, req.trip_id)
    finally:
        await release_workspace_exclusive(workspace)


@app.post("/trips/delete")
async def trips_delete(req: TripIdRequest, request: Request) -> dict:
    """Delete a single saved trip AND its chat history; returns the refreshed
    saved-trips list."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import chat_store

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        await asyncio.to_thread(trip_planner.delete_saved_trip, req.trip_id)
        await asyncio.to_thread(chat_store.clear, req.trip_id)
        trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        return {"ok": True, "trips": trips}
    finally:
        await release_workspace_exclusive(workspace)


@app.post("/trip/new")
async def trip_new(req: UserRequest, request: Request) -> dict:
    """Start a fresh planning chat: clear the active trip + the general chat
    bucket so the next conversation begins clean. Saved trips are untouched."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import chat_store

    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        await asyncio.to_thread(trip_planner.start_new_trip)
        await asyncio.to_thread(chat_store.clear, None)
        return {"ok": True}
    finally:
        await release_workspace_exclusive(workspace)



@app.get("/trip/export.ics")
async def trip_export_ics(request: Request, user_id: str = "local") -> Response:
    """Download the active trip as an iCalendar (.ics) file."""
    from tripplanner.tools import trip_planner
    from tripplanner.web.ics_export import build_ics

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    body = build_ics(plan)
    dest = ((plan or {}).get("destination") or "trip").lower()
    safe = "".join(c if c.isalnum() else "-" for c in dest).strip("-") or "trip"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{safe}.ics"'},
    )


@app.get("/trip/export/print")
async def trip_export_print(
    request: Request,
    user_id: str = "local",
    include_photos: str = "1",
    include_map_circuit: str = "1",
    template: str = "detailed",
    auto_print: str = "0",
) -> Response:
    """Return a print-ready HTML itinerary suitable for Save-as-PDF."""
    from tripplanner.tools import trip_planner
    from tripplanner.web.itinerary_export import build_export_html, parse_export_bool

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    html = build_export_html(
        plan,
        include_photos=parse_export_bool(include_photos, default=True),
        include_map_circuit=parse_export_bool(include_map_circuit, default=True),
        template=template,
        auto_print=parse_export_bool(auto_print, default=False),
    )
    return Response(content=html, media_type="text/html; charset=utf-8")


@app.get("/trip/export.pdf")
async def trip_export_pdf(
    request: Request,
    user_id: str = "local",
    template: str = "detailed",
    include_photos: str = "1",
    include_map_circuit: str = "1",
) -> Response:
    """Return a downloadable itinerary PDF generated server-side."""
    from tripplanner.tools import trip_planner

    _set_request_user(request, user_id)
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return JSONResponse({"error": "no active trip"}, status_code=404)

    try:
        from tripplanner.web.itinerary_export import parse_export_bool
        from tripplanner.web.itinerary_pdf import build_itinerary_pdf_bytes

        pdf_bytes = build_itinerary_pdf_bytes(
            plan,
            template=template,
            include_photos=parse_export_bool(include_photos, default=True),
            include_map_circuit=parse_export_bool(include_map_circuit, default=True),
        )
    except ImportError:
        return JSONResponse(
            {
                "error": "pdf_renderer_not_installed",
                "message": "Install reportlab to enable direct PDF download.",
            },
            status_code=503,
        )

    dest = str(plan.get("destination") or "trip").strip().lower()
    safe = "".join(c if c.isalnum() else "-" for c in dest).strip("-") or "trip"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-itinerary.pdf"'},
    )


@app.post("/trip/export/email")
async def trip_export_email(req: ExportEmailRequest, request: Request) -> dict:
    """Send the itinerary export once for a client-generated request ID.

    If SMTP is not configured, returns a `mailto:` fallback so the frontend can
    open the user's mail client with a prefilled subject/body.
    """
    import smtplib
    from email.message import EmailMessage
    from urllib.parse import quote

    from tripplanner.tools import trip_planner
    from tripplanner.web import external_operations
    from tripplanner.web.itinerary_export import build_export_html
    from tripplanner.web.share import mint_for_active_trip

    _set_request_user(request, req.user_id)
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return {"ok": False, "error": "no_active_trip", "message": "No active trip to export."}

    # Share / continue-planning link.
    token = mint_for_active_trip()
    share_url = f"{str(request.base_url).rstrip('/')}/trip/shared/{token}" if token else ""

    html = build_export_html(
        plan,
        include_photos=bool(req.include_photos),
        include_map_circuit=bool(req.include_map_circuit),
        template=req.template,
        auto_print=False,
        share_url=share_url,
    )
    destination = str(plan.get("destination") or "Trip")
    subject = f"{destination} itinerary export"
    fingerprint = external_operations.payload_fingerprint(
        {
            "trip_id": trip_planner.active_trip_id(),
            "email": req.email.strip().casefold(),
            "include_photos": req.include_photos,
            "include_map_circuit": req.include_map_circuit,
            "template": req.template,
        }
    )
    try:
        existing = external_operations.get(req.request_id, fingerprint)
    except external_operations.IdempotencyConflictError as exc:
        return JSONResponse(
            {"ok": False, "error": "idempotency_conflict", "message": str(exc)},
            status_code=409,
        )
    if existing and existing.get("status") == "completed":
        return {**dict(existing.get("result") or {}), "replayed": True}

    plain = (
        f"Your trip itinerary for {destination} is attached as HTML.\n"
        "Open it in a browser and Print → Save as PDF for a carry-along copy.\n"
        + (
            f"\nContinue planning or share this trip:\n{share_url}\n"
            if share_url
            else ""
        )
    )

    # Azure-first path: ACS Email (stays inside Azure cost/account boundary).
    acs_conn = os.getenv("AZURE_COMMUNICATION_CONNECTION_STRING", "").strip()
    acs_sender = os.getenv("AZURE_COMMUNICATION_EMAIL_SENDER", "").strip()
    if acs_conn and acs_sender:
        try:
            operation, _ = external_operations.claim_pending(
                req.request_id, fingerprint, provider="acs"
            )
            if operation.get("provider") != "acs":
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "email_delivery_uncertain",
                        "message": "The earlier delivery attempt is still unresolved.",
                    },
                    status_code=503,
                )
            from azure.communication.email import EmailClient

            client = EmailClient.from_connection_string(acs_conn)
            message = {
                "senderAddress": acs_sender,
                "recipients": {"to": [{"address": req.email}]},
                "content": {
                    "subject": subject,
                    "plainText": plain,
                    "html": html,
                },
            }
            poller = client.begin_send(
                message,
                operation_id=external_operations.provider_operation_id(req.request_id),
            )
            poller.result()
            result = {"ok": True, "message": f"Itinerary sent to {req.email}."}
            external_operations.record_completed(
                req.request_id,
                fingerprint,
                provider="acs",
                result=result,
            )
            app_event("api_trip_export_email_sent", destination=destination, provider="acs")
            return result
        except Exception as exc:
            app_event("api_trip_export_email_error", error=type(exc).__name__, provider="acs")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "email_delivery_uncertain",
                    "message": "Email delivery could not be confirmed. Retry this send safely.",
                },
                status_code=503,
            )

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "").strip()
    smtp_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"}

    if not smtp_host or not smtp_from:
        body = quote(
            plain + ("\n(Email sending is not configured on this server.)"),
            safe="",
        )
        return {
            "ok": False,
            "error": "email_not_configured",
            "mailto": (
                f"mailto:{quote(req.email, safe='')}?"
                f"subject={quote(subject, safe='')}&body={body}"
            ),
            "message": "SMTP is not configured; opened mail client fallback.",
        }

    try:
        operation, claimed = external_operations.claim_pending(
            req.request_id, fingerprint, provider="smtp"
        )
    except external_operations.IdempotencyConflictError as exc:
        return JSONResponse(
            {"ok": False, "error": "idempotency_conflict", "message": str(exc)},
            status_code=409,
        )
    if not claimed:
        if operation.get("status") == "completed":
            return {**dict(operation.get("result") or {}), "replayed": True}
        return JSONResponse(
            {
                "ok": False,
                "error": "email_delivery_uncertain",
                "message": "The earlier delivery attempt is still unresolved.",
            },
            status_code=503,
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = req.email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    msg.add_attachment(
        html.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename="trip-itinerary.html",
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            if smtp_tls:
                smtp.starttls()
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
    except Exception as exc:
        app_event("api_trip_export_email_error", error=type(exc).__name__)
        return JSONResponse(
            {
                "ok": False,
                "error": "email_delivery_uncertain",
                "message": "Email delivery could not be confirmed.",
            },
            status_code=503,
        )

    result = {"ok": True, "message": f"Itinerary sent to {req.email}."}
    external_operations.record_completed(
        req.request_id,
        fingerprint,
        provider="smtp",
        result=result,
    )
    app_event("api_trip_export_email_sent", destination=destination)
    return result


@app.post("/trip/share")
async def trip_share(req: SelectRequest, request: Request) -> dict:
    """Mint an opaque read-only share token for the active trip.

    Re-using ``SelectRequest`` only for its ``user_id`` field — ``kind``/``name``
    are ignored. Returns ``{token, url}`` or ``{error}`` if no active plan.
    """
    from tripplanner.web.share import mint_for_active_trip

    _set_request_user(request, req.user_id)
    token = mint_for_active_trip()
    if not token:
        return {"error": "no active trip to share"}
    base = str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/trip/shared/{token}"}


@app.get("/trip/shared/{token}")
async def trip_shared_view(token: str, request: Request) -> Response:
    """Public read-only HTML snapshot of a shared trip plan."""
    from tripplanner.web.share import render_public_html

    base = str(request.base_url).rstrip("/")
    html = render_public_html(token, current_origin=base)
    if html is None:
        return JSONResponse(
            {"error": "invalid or expired share link"}, status_code=404
        )
    return Response(content=html, media_type="text/html; charset=utf-8")


@app.get("/trip/shared/{token}.json")
async def trip_shared_json(token: str) -> dict:
    """Public JSON payload for a shared snapshot."""
    from tripplanner.web.share import resolve

    snapshot = resolve(token)
    if snapshot is None:
        return JSONResponse({"error": "invalid or expired share link"}, status_code=404)
    return snapshot


@app.post("/trip/shared/{token}/import")
async def trip_shared_import(token: str, req: UserRequest, request: Request) -> dict:
    """Import a shared snapshot into the caller's own editable trip space."""
    from tripplanner.tools import trip_planner
    from tripplanner.web import share, trip_view

    snapshot = share.resolve(token)
    if snapshot is None:
        return JSONResponse({"error": "invalid or expired share link"}, status_code=404)
    user_id = _set_request_user(request, req.user_id)
    workspace = await acquire_workspace_exclusive(user_id)
    try:
        imported = await asyncio.to_thread(
            trip_planner.import_shared_trip_snapshot, snapshot.get("plan") or {}
        )
        view = await asyncio.to_thread(trip_view.build_view, imported, None)
        return {"ok": True, "view": view}
    finally:
        await release_workspace_exclusive(workspace)


@app.get("/preferences")
async def get_preferences(request: Request, user_id: str = "local") -> dict:
    """Return the editable subset of the user's saved preferences (for the
    SPA settings panel)."""
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, user_id)
    prefs = prefs_store.load_preferences()
    profile = prefs.get("profile") or {}
    transport = prefs.get("transport_preferences") or {}
    hotel = prefs.get("hotel_preferences") or {}
    food = prefs.get("food_preferences") or {}
    return {
        "display_name": profile.get("display_name") or "",
        "home_city": profile.get("home_city") or "",
        "home_country": profile.get("home_country") or "",
        "trip_style": prefs.get("trip_style") or "",
        "budget_level": prefs.get("budget_level") or "",
        "flight_class": transport.get("flight_class") or "",
        "prefer_direct_flights": bool(transport.get("prefer_direct_flights", True)),
        "hotel_star_rating_min": int(hotel.get("star_rating_min") or 3),
        "dietary": list(food.get("dietary") or []),
        "interests": list(prefs.get("interests") or []),
        "dislikes": list(prefs.get("dislikes") or []),
        "about_me": prefs.get("about_me") or "",
        "profile_summary": prefs.get("profile_summary") or "",
        "profile_summary_updated_at": prefs.get("profile_summary_updated_at"),
        "planning_mode": prefs.get("planning_mode") or "direct",
    }


@app.post("/preferences")
async def save_preferences_endpoint(req: PreferencesRequest, request: Request) -> dict:
    """Merge the provided preference fields and persist them (additive — only
    keys present in the request are written)."""
    from tripplanner.tools import preferences_merge
    from tripplanner.tools import profile_summary as profile_summary_mod
    from tripplanner.tools import user_preferences as prefs_store

    _set_request_user(request, req.user_id)
    current = prefs_store.load_preferences()
    about_text: str | None = None
    about_extracted: dict = {}
    about_learned: list[dict] = []
    extracted_keys: list[str] = []
    summary_conflict = False
    summary_has_compare_token = "profile_summary_updated_at" in req.model_fields_set
    explicit_paths = {
        "display_name": "profile.display_name",
        "home_city": "profile.home_city",
        "home_country": "profile.home_country",
        "trip_style": "trip_style",
        "budget_level": "budget_level",
        "flight_class": "transport_preferences.flight_class",
        "prefer_direct_flights": "transport_preferences.prefer_direct_flights",
        "hotel_star_rating_min": "hotel_preferences.star_rating_min",
        "dietary": "food_preferences.dietary",
        "interests": "interests",
        "dislikes": "dislikes",
        "planning_mode": "planning_mode",
        "about_me": "about_me",
        "profile_summary": "profile_summary",
    }
    submitted_paths = {
        path
        for field, path in explicit_paths.items()
        if field in req.model_fields_set
    }
    if req.about_me is not None:
        about_text = req.about_me.strip()[: preferences_merge.ABOUT_ME_MAX_CHARS]
        old_about = str(current.get("about_me") or "").strip()
        if about_text and about_text != old_about:
            extracted = preferences_merge.about_me_extractor.extract_about_me(about_text)
            about_learned = list(extracted.pop("_learned_notes_to_append", None) or [])
            about_extracted = extracted
            extracted_keys = preferences_merge.flatten_keys(extracted)
            if about_learned:
                extracted_keys.append("learned_notes")

    def apply(prefs: dict) -> dict | None:
        nonlocal summary_conflict
        summary_conflict = False
        if (
            req.profile_summary is not None
            and summary_has_compare_token
            and prefs.get("profile_summary_updated_at") != req.profile_summary_updated_at
        ):
            summary_conflict = True
            return None

        profile = dict(prefs.get("profile") or {})
        transport = dict(prefs.get("transport_preferences") or {})
        hotel = dict(prefs.get("hotel_preferences") or {})
        food = dict(prefs.get("food_preferences") or {})

        if req.display_name is not None:
            profile["display_name"] = req.display_name.strip() or None
        if req.home_city is not None:
            profile["home_city"] = req.home_city.strip() or None
        if req.home_country is not None:
            profile["home_country"] = req.home_country.strip() or None
        if req.trip_style is not None:
            prefs["trip_style"] = req.trip_style or None
        if req.budget_level is not None:
            prefs["budget_level"] = req.budget_level or None
        if req.flight_class is not None:
            transport["flight_class"] = req.flight_class or None
        if req.prefer_direct_flights is not None:
            transport["prefer_direct_flights"] = req.prefer_direct_flights
        if req.hotel_star_rating_min is not None:
            hotel["star_rating_min"] = max(1, min(5, int(req.hotel_star_rating_min)))
        if req.dietary is not None:
            food["dietary"] = [value.strip() for value in req.dietary if value.strip()]
        if req.interests is not None:
            prefs["interests"] = [value.strip() for value in req.interests if value.strip()]
        if req.dislikes is not None:
            prefs["dislikes"] = [value.strip() for value in req.dislikes if value.strip()]
        if req.planning_mode is not None:
            prefs["planning_mode"] = req.planning_mode

        prefs["profile"] = profile
        prefs["transport_preferences"] = transport
        prefs["hotel_preferences"] = hotel
        prefs["food_preferences"] = food

        if about_text is not None:
            prefs["about_me"] = about_text
            prefs = preferences_merge.additive_overlay_extracted(prefs, about_extracted)
            if about_learned:
                notes = list(prefs.get("learned_notes") or [])
                seen = {
                    (entry.get("note") or "").strip().lower()
                    for entry in notes
                    if isinstance(entry, dict)
                }
                for entry in about_learned:
                    note = str(entry.get("note") or "").strip()
                    if note and note.lower() not in seen:
                        seen.add(note.lower())
                        notes.append(entry)
                prefs["learned_notes"] = notes
        if req.profile_summary is not None:
            profile_summary_mod.apply_summary(prefs, req.profile_summary)
        prefs_store.mark_explicit_fields(prefs, submitted_paths)
        return prefs

    updated = prefs_store.mutate_preferences(apply)
    if summary_conflict:
        return JSONResponse(
            {
                "error": "profile summary changed while settings were open",
                "profile_summary": updated.get("profile_summary") or "",
                "profile_summary_updated_at": updated.get("profile_summary_updated_at"),
            },
            status_code=409,
        )

    app_event("api_preferences_saved")
    return {"ok": True, "about_me_extracted": extracted_keys}


@app.post("/profile/summary/regenerate")
async def regenerate_profile_summary(req: SelectRequest, request: Request) -> dict:
    """Force a fresh LLM-authored profile summary for the user.

    Re-uses ``SelectRequest`` only for ``user_id`` (``kind``/``name`` ignored).
    Returns the new ``profile_summary`` (may be empty if there's nothing durable
    to summarize or the model is unavailable).
    """
    from tripplanner.tools import profile_summary as profile_summary_mod

    _set_request_user(request, req.user_id)
    profile_summary_mod.update_summary(force=True)
    prefs = profile_summary_mod.user_preferences.load_preferences()
    app_event("api_profile_summary_regenerated")
    return {
        "ok": True,
        "profile_summary": prefs.get("profile_summary") or "",
        "profile_summary_updated_at": prefs.get("profile_summary_updated_at"),
    }

@app.post("/account/privacy")
async def account_privacy_action(req: PrivacyActionRequest, request: Request) -> dict:
    """Run user-requested privacy actions (GDPR-style controls).

    Supported actions:
    - ``delete_trip_history``: remove all saved/active trips and chat history.
    - ``clear_all_data``: delete trips/chats + reset preferences + clear usage/cache.
    - ``delete_account``: same as clear-all; identity provider account remains external.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.usage import clear_usage
    from tripplanner.web import chat_store
    import tripplanner.tools_cache as tools_cache

    user_id = _set_request_user(request, req.user_id)

    if req.action in {"clear_all_data", "delete_account"}:
        if req.confirm_text.strip().upper() != "DELETE":
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Type DELETE to confirm this action.",
            }

    workspace = await acquire_workspace_exclusive(user_id)
    try:
        deleted_trips = await asyncio.to_thread(trip_planner.clear_all_trip_history)
        deleted_chats = await asyncio.to_thread(chat_store.clear_all)

        deleted_usage = 0
        deleted_cache = 0
        reset_prefs = False

        if req.action in {"clear_all_data", "delete_account"}:
            await asyncio.to_thread(prefs_store.reset_preferences)
            reset_prefs = True
            deleted_usage = await asyncio.to_thread(clear_usage, user_id)
            deleted_cache = await asyncio.to_thread(tools_cache.clear_cache_for_user, user_id)
    finally:
        await release_workspace_exclusive(workspace)

    app_event(
        "api_privacy_action",
        action=req.action,
        deleted_trips=deleted_trips,
        deleted_chats=deleted_chats,
        deleted_usage=deleted_usage,
        deleted_cache=deleted_cache,
    )

    return {
        "ok": True,
        "action": req.action,
        "deleted_trips": deleted_trips,
        "deleted_chats": deleted_chats,
        "deleted_usage": deleted_usage,
        "deleted_cache": deleted_cache,
        "preferences_reset": reset_prefs,
        "message": (
            "Trip history deleted."
            if req.action == "delete_trip_history"
            else "All app data cleared for this account."
        ),
    }


@app.post("/account/migrate-guest")
async def account_migrate_guest(req: GuestMigrateRequest, request: Request) -> dict:
    """Copy trips and preferences from a guest (web-*) identity into an
    authenticated account.

    Called once after Google OAuth sign-in when the browser had existing guest
    data. Safe to call multiple times — already-migrated trips are skipped.
    Returns {ok, copied_trips, skipped_trips, copied_prefs}.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store

    guest_id = (req.guest_id or "").strip()
    auth_id = require_signed_user(request) if is_hosted() else resolve_user_id(request, req.user_id)
    if not is_anonymous_id(guest_id) or not auth_id:
        return {"ok": False, "error": "invalid_ids"}
    if is_hosted():
        require_guest_capability(request, guest_id)

    workspace = await acquire_workspace_exclusive(guest_id, auth_id)
    try:
        set_user_id(guest_id)
        guest_trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        guest_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
        guest_trip_ids = [str(item["trip_id"]) for item in guest_trips if item.get("trip_id")]
        guest_active_id = str((guest_active or {}).get("trip_id") or "")
        if guest_active_id:
            guest_trip_ids.append(guest_active_id)
        guest_chat_state = await asyncio.to_thread(chat_store.export_state, guest_trip_ids)

        set_user_id(auth_id)
        auth_trips = await asyncio.to_thread(trip_planner.list_saved_trips)
        auth_trip_ids = {t["trip_id"] for t in auth_trips}

        copied_trips = 0
        skipped_trips = 0
        for summary in guest_trips:
            tid = summary.get("trip_id")
            if not tid or tid in auth_trip_ids:
                skipped_trips += 1
                continue
            set_user_id(guest_id)
            full_plan = await asyncio.to_thread(trip_planner._load_history_trip, tid)
            if not full_plan:
                skipped_trips += 1
                continue
            set_user_id(auth_id)
            await asyncio.to_thread(trip_planner._mirror_to_history, full_plan)
            copied_trips += 1

        copied_prefs = False
        set_user_id(guest_id)
        guest_prefs = prefs_store.load_preferences()
        if prefs_store.has_non_default_preferences(guest_prefs):
            set_user_id(auth_id)

            def adopt_guest_prefs(auth_prefs: dict) -> dict | None:
                nonlocal copied_prefs
                copied_prefs = False
                merged = prefs_store.adopt_missing_preferences(auth_prefs, guest_prefs)
                copied_prefs = merged != auth_prefs
                return merged if copied_prefs else None

            prefs_store.mutate_preferences(adopt_guest_prefs)

        set_user_id(auth_id)
        auth_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
        if guest_active and not auth_active:
            await asyncio.to_thread(trip_planner._save_active_trip, guest_active)
        copied_chat = await asyncio.to_thread(chat_store.adopt_state, guest_chat_state)
    finally:
        set_user_id(auth_id)
        await release_workspace_exclusive(workspace)

    app_event(
        "api_guest_migrate",
        copied_trips=copied_trips,
        skipped_trips=skipped_trips,
        copied_prefs=copied_prefs,
        copied_chat=copied_chat,
    )
    return {
        "ok": True,
        "copied_trips": copied_trips,
        "skipped_trips": skipped_trips,
        "copied_prefs": copied_prefs,
        "copied_chat": copied_chat,
    }


@app.get("/account/guest-data-summary")
async def account_guest_data_summary(request: Request, user_id: str) -> dict:
    """How much data does a guest (web-*) account have?

    Called by the frontend after OAuth login to decide whether to offer
    the guest-import banner.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.user_context import set_user_id

    guest_id = (user_id or "").strip()
    if not is_anonymous_id(guest_id):
        return {"has_data": False, "trip_count": 0}
    if is_hosted():
        require_signed_user(request)
        require_guest_capability(request, guest_id)
    set_user_id(guest_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
    count = len(trips) + (1 if active and not trips else 0)
    preferences = await asyncio.to_thread(prefs_store.load_preferences)
    has_preferences = prefs_store.has_non_default_preferences(preferences)
    return {
        "has_data": count > 0 or has_preferences,
        "trip_count": count,
        "has_preferences": has_preferences,
    }


# ---------------------------------------------------------------------------
# Google OAuth — standalone HMAC-signed session cookie. Degrades gracefully:
# when OAUTH_GOOGLE_CLIENT_ID etc. are unset, /auth/me reports
# {authenticated: false} and the SPA falls back to name/anon.
# ---------------------------------------------------------------------------
def _secure_cookie(request: Request) -> bool:
    return oauth.redirect_uri(str(request.base_url)).startswith("https://")


@app.get("/auth/config")
async def auth_config(request: Request) -> dict:
    """Tells the SPA whether to show the 'Sign in with Google' button, and
    surfaces the exact redirect URI the backend will hand to Google — copy
    this verbatim into the Google Cloud Console 'Authorized redirect URIs'
    list to avoid redirect_uri_mismatch."""
    return {
        "google": oauth.is_enabled(),
        "guest_sessions": oauth.signing_enabled(),
        "redirect_uri": oauth.redirect_uri(str(request.base_url)),
    }


@app.post("/auth/guest/session")
async def auth_guest_session(req: UserRequest, request: Request) -> Response:
    """Issue a signed capability for a browser/native anonymous identity."""
    current = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if current and current.get("session_kind") != "guest":
        return JSONResponse({"authenticated": True, "user_id": current["user_id"], "token": ""})
    guest_id = (req.user_id or "").strip()
    if not is_anonymous_id(guest_id):
        return JSONResponse({"authenticated": False}, status_code=400)
    if not oauth.signing_enabled():
        if is_hosted():
            return JSONResponse({"authenticated": False}, status_code=503)
        return JSONResponse({"authenticated": False, "user_id": guest_id, "token": ""})

    token = oauth.make_guest_token(guest_id)
    response = JSONResponse({"authenticated": False, "user_id": guest_id, "token": token})
    response.set_cookie(
        oauth.SESSION_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return response


@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    """Return the signed-in identity (from the session cookie) or anonymous."""
    session = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if not session or session.get("session_kind") == "guest":
        return {"authenticated": False}
    return {
        "authenticated": True,
        **{key: value for key, value in session.items() if key != "session_kind"},
    }


@app.get("/auth/mobile/session")
async def auth_mobile_session(token: str = "") -> Response:
    """Validate a signed OAuth session returned to the native app."""
    session = oauth.read_session(token)
    if not session or session.get("session_kind") == "guest":
        return JSONResponse({"authenticated": False}, status_code=401)
    return JSONResponse(
        {
            "authenticated": True,
            **{key: value for key, value in session.items() if key != "session_kind"},
        }
    )


def _mobile_auth_redirect(target: str, token: str) -> str | None:
    parsed = urlsplit(target)
    if parsed.scheme not in {"tripplanner", "exp"}:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["session"] = token
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


@app.get("/auth/login/google")
async def auth_login_google(request: Request, redirect: str = "/") -> RedirectResponse:
    """Kick off the authorization-code flow → redirect the browser to Google."""
    if not oauth.is_enabled():
        return RedirectResponse(redirect or "/", status_code=302)
    callback = oauth.redirect_uri(str(request.base_url))
    url, state_token = oauth.build_authorize_url(callback, redirect or "/")
    res = RedirectResponse(url, status_code=302)
    res.set_cookie(
        "mg_oauth_state",
        state_token,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return res


@app.get("/auth/callback/google")
async def auth_callback_google(
    request: Request, code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Google redirects here with ?code. Exchange it, set the session cookie,
    then bounce back to the SPA path the user started from."""
    post_login = oauth.verify_state(request.cookies.get("mg_oauth_state"), state)
    if error or not code or post_login is None:
        app_event("api_oauth_callback_rejected", reason=error or "bad_state")
        res = RedirectResponse("/?auth=failed", status_code=302)
        res.delete_cookie("mg_oauth_state", path="/")
        return res

    callback = oauth.redirect_uri(str(request.base_url))
    try:
        profile = await oauth.exchange_code(code, callback)
    except Exception as exc:
        app_event("api_oauth_exchange_error", error=type(exc).__name__)
        res = RedirectResponse("/?auth=failed", status_code=302)
        res.delete_cookie("mg_oauth_state", path="/")
        return res

    identifier = profile["identifier"]
    # Seed the display name on first login.
    try:
        from tripplanner.tools import user_preferences as prefs_store
        from tripplanner.user_context import set_user_id

        set_user_id(identifier)
        if profile.get("name"):
            display_name = profile["name"].split()[0]

            def seed_display_name(prefs: dict) -> dict | None:
                profile_blob = dict(prefs.get("profile") or {})
                if profile_blob.get("display_name"):
                    return None
                profile_blob["display_name"] = display_name
                prefs["profile"] = profile_blob
                return prefs

            prefs_store.mutate_preferences(seed_display_name)
    except Exception:
        pass  # profile seeding is best-effort; never block login

    app_event("api_oauth_login", provider="google")
    token = oauth.make_session_token(
        identifier, profile.get("name", ""), profile.get("email", ""), profile.get("picture", "")
    )
    res = RedirectResponse(_mobile_auth_redirect(post_login, token) or post_login or "/", status_code=302)
    res.delete_cookie("mg_oauth_state", path="/")
    res.set_cookie(
        oauth.SESSION_COOKIE,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
    )
    return res


@app.post("/auth/logout")
async def auth_logout() -> JSONResponse:
    res = JSONResponse({"ok": True})
    res.delete_cookie(oauth.SESSION_COOKIE, path="/")
    return res


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics/tools")
async def metrics_tools() -> dict:
    """Return per-tool latency + error + cache-hit counters.

    In-process only — accumulated for the lifetime of the current container.
    Intended for live introspection during a session; long-horizon data lives
    in Log Analytics via the structured ``tool_call`` events.
    """
    from tripplanner.observability import tool_metrics_snapshot

    return {"tools": tool_metrics_snapshot()}


@app.get("/usage")
async def usage_for_user(request: Request, user_id: str = "local") -> dict:
    """Return this month's LLM token + cost usage for ``user_id`` and the cap."""
    from tripplanner.usage import get_cap_usd, get_usage, is_over_cap

    resolved_user_id = _set_request_user(request, user_id)
    over, doc = is_over_cap(resolved_user_id)
    return {
        "user_id": resolved_user_id,
        "month": doc.get("month"),
        "prompt_tokens": doc.get("prompt_tokens", 0),
        "completion_tokens": doc.get("completion_tokens", 0),
        "calls": doc.get("calls", 0),
        "cost_usd": round(float(doc.get("cost_usd", 0.0)), 4),
        "cap_usd": get_cap_usd(),
        "over_cap": over,
    }


# ---------------------------------------------------------------------------
# Static SPA — serve the built React frontend (frontend/dist) so a single
# container/origin hosts both the API and the UI. Registered LAST so it never
# shadows an API route; the catch-all returns index.html for client-side
# routing. Skipped entirely when the build is absent (pure-API dev runs).
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_SPA_DIST = (
    Path(os.environ["SPA_DIST_DIR"])
    if os.environ.get("SPA_DIST_DIR")
    else Path(__file__).resolve().parents[2] / "frontend" / "dist"
)

if (_SPA_DIST / "index.html").is_file():
    _assets = _SPA_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/", include_in_schema=False)
    async def _spa_index() -> FileResponse:
        return FileResponse(str(_SPA_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_catchall(full_path: str) -> FileResponse:
        target = _SPA_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_SPA_DIST / "index.html"))

