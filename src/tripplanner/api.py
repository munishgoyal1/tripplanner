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
* ``GET  /documents``    — stored traveller document fields (never the file).
* ``POST /documents/extract`` — propose fields from a photo or pasted text.
* ``GET  /trip/documents/readiness`` — deterministic paperwork checks for the trip.
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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from starlette.background import BackgroundTask

from tripplanner import config as _config  # noqa: F401  -- import triggers load_dotenv()
from tripplanner import graph_policy
from tripplanner.api_contracts import (
    ChatRequest,
    ChatResponse,
)
from tripplanner.chat_interactions import extract_input_request
from tripplanner.chat_turn import (
    AdmittedTurn,
    ChatTurnCoordinator,
    ChatTurnDependencies,
    TurnTerminal,
)
from tripplanner.decisions.receipts import ReceiptLog
from tripplanner.flight_middleware import FlightRecorderMiddleware
from tripplanner.observability import app_event, model_rate_limit_fields, setup_logging
from tripplanner.request_limits import (
    acquire_chat,
    acquire_replay_access,
    check_replay_lookup,
    release_chat,
    release_replay_access,
)
from tripplanner.request_state import request_state_scope
from tripplanner.trip_repository import TripConflictError
from tripplanner.user_context import set_user_id
from tripplanner.web.account_http import router as account_router
from tripplanner.web.http_context import (
    mobile_auth_redirect as _mobile_auth_redirect,  # noqa: F401
)
from tripplanner.web.http_context import (
    set_request_user as _set_request_user,
)
from tripplanner.web.ops_http import router as ops_router
from tripplanner.web.runtime_routes import router as runtime_router
from tripplanner.web.trip_http import router as trip_router

setup_logging()

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    # Let places_cache's rate limiter bail out of any in-progress wait
    # immediately, instead of a worker thread holding up process exit for as
    # long as its remaining quota wait -- concurrent.futures.thread's atexit
    # hook joins every ThreadPoolExecutor worker with no timeout.
    from tripplanner.web import places_cache

    places_cache.begin_shutdown()


app = FastAPI(title="Personal Assistant API", version="0.1.0", lifespan=_lifespan)

app.add_middleware(FlightRecorderMiddleware)


@app.exception_handler(TripConflictError)
async def _trip_conflict_handler(
    _request: Request, exc: TripConflictError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "This trip changed while your update was being saved. Refresh and retry.",
            "error": "trip_conflict",
            "message": str(exc),
        },
    )

# LangGraph counts every node, so a flat 24 cut the turn off at exactly the step
# where the policy forces the still-owed first itinerary save, leaving a created
# trip with no days. Keep the graceful policy budget the binding limit and this
# a backstop: each phase costs an agent node plus a tool node, plus a final
# reply node and enough completion headroom for a hotel-provider fallback followed
# by the required post-research persistence pass.
_CHAT_GRAPH_RECURSION_LIMIT = 2 * (
    graph_policy.MAX_TOOL_PHASES_PER_TURN
    + graph_policy.MAX_INITIAL_ITINERARY_UPDATES
    + graph_policy.MAX_POST_RESEARCH_UPDATES
    + 2
) + 2

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


def _ran_tools(messages: list[Any], since: int) -> dict[str, list[str]]:
    """Tool names this turn ran, for the saved assistant message to carry.

    The graph's tool messages are dropped when a turn is persisted, so a policy
    that spans turns -- whether the trip kickoff was ever asked -- would other-
    wise re-decide from scratch every time and never clear.
    """
    names: list[str] = []
    for message in list(messages)[since:]:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name and name not in names:
                names.append(str(name))
    return {graph_policy.RAN_TOOLS_KEY: names} if names else {}


def _rate_limit_response(exc: BaseException) -> JSONResponse | None:
    """A provider throttle is the caller going too fast, not a server fault.

    Returned as 500 it looked like a crash, so callers that already back off on
    429 -- the corpus builder among them -- discarded the request instead.
    """
    from tripplanner.observability import model_rate_limit_fields

    fields = model_rate_limit_fields(exc, "")
    if not fields:
        return None
    retry_ms = fields.get("retry_after_ms")
    seconds = max(1, round((retry_ms or 60_000) / 1000))
    return JSONResponse(
        status_code=429,
        content={"detail": "The model is busy right now. Try again shortly."},
        headers={"Retry-After": str(seconds)},
    )


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
    started_at = time.monotonic()
    status_code = 500
    from tripplanner.usage_attribution import usage_scope

    interaction_id = request.headers.get("x-request-id", "")
    from tripplanner.places_budget import PaidProviderPurpose, places_budget_scope

    purpose: PaidProviderPurpose = (
        "corpus_generation"
        if request.headers.get("x-tripplanner-paid-provider-purpose") == "corpus_generation"
        else "user_interaction"
    )
    provider_scope = (
        nullcontext() if os.environ.get("PYTEST_CURRENT_TEST") else places_budget_scope(purpose)
    )
    try:
        with request_state_scope():
            with provider_scope:
                if request.scope.get("path") == "/chat/stream":
                    response = await call_next(request)
                else:
                    with usage_scope(
                        "user_action",
                        interaction_id=interaction_id,
                        route=f"{request.method} {request.scope.get('path', '')}",
                    ):
                        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        from tripplanner.observability import log_api_request
        from tripplanner.ops_metrics import record_request

        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "unmatched"
        elapsed_ms = (time.monotonic() - started_at) * 1000
        if not str(route_path).startswith("/ops/"):
            record_request(
                request.method,
                str(route_path),
                status_code,
                elapsed_ms,
            )
        log_api_request(request.method, str(route_path), status_code, elapsed_ms)

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


async def _reserve_cost(req: ChatRequest, request_id: str) -> None:
    """Hold this turn's pessimistic INR estimate against the spend ceiling.

    Keyed by the request id, which is also the interaction id, so the hold is
    reconciled to actual spend when the turn's usage batch flushes without
    anything being threaded through the turn coordinator.
    """
    from tripplanner import cost_ledger
    from tripplanner.tools.trip_planner import load_active_trip_dict

    active_trip = await asyncio.to_thread(load_active_trip_dict) or {}
    category = "trip_update" if str(active_trip.get("destination") or "").strip() else "new_trip"
    await asyncio.to_thread(
        cost_ledger.reserve, category, interaction_id=request_id or req.request_id or ""
    )


def _cost_ceiling_response(exc: BaseException) -> JSONResponse:
    from tripplanner.cost_ledger import CostCeilingError

    if isinstance(exc, CostCeilingError):
        detail = exc.as_detail()
        detail["message"] = (
            f"This environment has reached its {exc.window} planning budget "
            f"(INR {exc.spent_inr:.0f} of INR {exc.ceiling_inr:.0f}). "
            f"It resets at {exc.resets_at}. "
            "Saved trips and preferences are unchanged."
        )
        return JSONResponse(status_code=429, content=detail)
    return JSONResponse(
        status_code=503,
        content={
            "code": "cost_ceiling_unavailable",
            "message": "Spend controls are unavailable. Please retry shortly.",
        },
    )


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
    turn_seconds: int | None = None,
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
    origin_prompt = ""
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
        origin_prompt = chat_store.originating_request(base_history, new_dest)

    from tripplanner.flight_recorder import record

    record("chat.persist.attempt", trip_id=tid_after, previous_trip_id=tid_before,
           request_id=request_id, completed=completed, duration_seconds=turn_seconds,
           messages=completed_turn)
    saved_trip_id = chat_store.persist_turn(
        tid_before,
        tid_after,
        base_history,
        completed_turn,
        carryover,
        origin_prompt=origin_prompt,
        request_id=request_id,
        completed=completed,
        agent=agent,
        turn_seconds=turn_seconds,
    )

    record("chat.persisted", trip_id=saved_trip_id, request_id=request_id,
           completed=completed, duration_seconds=turn_seconds)
    return saved_trip_id


# Fire-and-forget passive-learning sweeps. Keep strong refs so the event loop
# doesn't garbage-collect a running task before it finishes.
_BG_TASKS: set[asyncio.Task] = set()


def _schedule_learning_sweep(
    user_id: str, message: str, context: list[dict] | None = None
) -> None:
    """Run the post-turn passive-learning sweep without blocking the response.

    The extractor makes a blocking LLM call, so it runs in a worker thread; the
    user identity is re-bound and its request snapshot is isolated from the
    response. Extraction failures remain queued for retry on a later turn.
    """
    def _worker() -> None:
        from tripplanner.request_state import request_state_scope
        from tripplanner.tools import passive_learning, profile_summary
        from tripplanner.usage_attribution import usage_scope

        set_user_id(user_id)
        with request_state_scope(), usage_scope("agent_background", route="passive_learning"):
            passive_learning.learn_from_message(message, context)
            # Refresh the system-authored profile summary. Gated internally by a
            # durable-facts digest, so this is a no-op (no LLM call) when nothing
            # durable changed — including trip-scoped one-offs.
            try:
                profile_summary.update_summary()
            except Exception as exc:
                app_event("profile_summary_deferred", error=type(exc).__name__)

    try:
        task = asyncio.create_task(asyncio.to_thread(_worker))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except RuntimeError:
        # No running loop (e.g. a sync test harness) — run inline best-effort.
        _worker()


def _record_chat_operation(
    started: float,
    *,
    user_id: str,
    transport: Literal["json", "sse"],
    outcome: Literal[
        "completed", "replayed", "cost_limited", "rate_limited", "error"
    ],
    error: str | None = None,
    exception: BaseException | None = None,
    tool_calls: int = 0,
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
    from tripplanner.ops_metrics import record_chat_turn

    record_chat_turn(
        user_id,
        outcome,
        (time.monotonic() - started) * 1000,
        tool_calls=tool_calls,
    )


def _record_chat_error(
    started: float,
    *,
    user_id: str,
    transport: Literal["json", "sse"],
    exc: BaseException,
) -> None:
    """Record an admission/setup failure before it propagates to the client."""
    _record_chat_operation(
        started,
        user_id=user_id,
        transport=transport,
        outcome="error",
        error=type(exc).__name__,
    )


def _record_chat_phase(
    started: float,
    *,
    transport: Literal["json", "sse"],
    phase: Literal["admission", "finalization"],
    status: Literal["ok", "error"] = "ok",
) -> None:
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    app_event(
        "chat_phase",
        transport=transport,
        operation=phase,
        status=status,
        ms=duration_ms,
    )
    from tripplanner.ops_metrics import record_operation

    record_operation("chat_phase", f"{transport}.{phase}", status, duration_ms)


def _chat_turn_coordinator(
    req: ChatRequest,
    request: Request,
    user_id: str,
    transport: Literal["json", "sse"],
    request_id: str = "",
) -> ChatTurnCoordinator:
    return ChatTurnCoordinator(
        ChatTurnDependencies(
            acquire_replay=lambda _user_id: acquire_replay_access(user_id),
            release_replay=release_replay_access,
            check_replay=lambda: check_replay_lookup(request, user_id),
            completed_request=_completed_chat_request,
            repair_completed=_repair_completed_chat,
            acquire_chat=lambda: acquire_chat(request, user_id),
            release_chat=release_chat,
            load_request=_load_chat_request,
            reserve=lambda _history: _reserve_cost(req, request_id),
            limit_response=_cost_ceiling_response,
            save_chat=_save_chat,
            auto_persist_needed=_should_auto_persist_itinerary,
            auto_persist=_auto_persist_itinerary,
            schedule_learning=_schedule_learning_sweep,
            record_operation=_record_chat_operation,
            record_phase=_record_chat_phase,
            event=app_event,
        )
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    from tripplanner.graph import app_graph
    from tripplanner.places_budget import places_budget_scope

    started = time.monotonic()
    header_request_id = request.headers.get("x-request-id", "")
    if header_request_id and req.request_id and header_request_id != req.request_id:
        raise HTTPException(status_code=422, detail="Request IDs in header and body must match.")
    request_id = req.request_id or header_request_id
    user_id = _set_request_user(request, req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    coordinator = _chat_turn_coordinator(req, request, user_id, "json", request_id)
    try:
        turn = await coordinator.admit(
            started=started,
            transport="json",
            user_id=user_id,
            request_id=request_id,
            message=req.message,
        )
        if isinstance(turn, TurnTerminal):
            if turn.response is not None:
                return turn.response
            return ChatResponse(
                reply=turn.reply,
                agent=turn.agent,
                trip_id=turn.trip_id,
            )
        assert isinstance(turn, AdmittedTurn)
        budget_exhausted = False
        try:
            from tripplanner.usage_attribution import annotate_current_batch, usage_scope

            with usage_scope(
                "user_trip",
                interaction_id=request_id,
                trip_id=turn.history_trip_id or "",
                route="POST /chat",
                interaction_kind="trip_update" if turn.history_trip_id else "new_trip",
            ) as usage_attribution:
                try:
                    with places_budget_scope("user_interaction"):
                        result = await asyncio.to_thread(
                            app_graph.invoke,
                            {
                                "messages": turn.history,
                                "current_agent": "",
                                "proposal_only": req.proposal_only,
                            },
                            config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT},
                        )
                finally:
                    if not turn.history_trip_id:
                        from tripplanner.tools.trip_planner import active_trip_id

                        annotate_current_batch(
                            interaction_id=usage_attribution.interaction_id,
                            trip_id=await asyncio.to_thread(active_trip_id) or "",
                        )
        except GraphRecursionError:
            # Native and scripted clients use this path; without the same
            # handling the SSE path has, an exhausted turn raised a 500 and the
            # freshly created trip was left with no itinerary and no answer.
            budget_exhausted = True
            result = {"messages": list(turn.history), "current_agent": "trip"}
        except Exception as exc:
            await coordinator.persist_interrupted(
                turn,
                message=req.message,
                partial_reply="",
                error=exc,
                tool_names=set(),
            )
            throttled = _rate_limit_response(exc)
            if throttled is not None:
                _record_chat_operation(
                    started, user_id=user_id, transport="json", outcome="rate_limited"
                )
                return throttled
            raise

        if budget_exhausted:
            reply, gap_count = await asyncio.to_thread(_best_effort_plan_reply)
            app_event("api_chat_budget_exhausted", completion_gap_count=gap_count)
        else:
            reply = ""
            for msg in reversed(result["messages"]):
                if hasattr(msg, "content") and msg.content and msg.type == "ai":
                    reply = msg.content
                    break
            from tripplanner.hallucination_critic import critique

            issues = critique(reply, result.get("messages", []))
            if issues:
                app_event("hallucination_critic", issues=len(issues), claims=issues)

        turn_tools = set(_ran_tools(result.get("messages") or [], len(turn.history)).get(
            graph_policy.RAN_TOOLS_KEY, []
        ))
        agent = result.get("current_agent", "unknown")
        completion = await coordinator.finalize(
            turn,
            message=req.message,
            reply=reply,
            agent=agent,
            tool_names=turn_tools,
            additional_kwargs=_ran_tools(result.get("messages") or [], len(turn.history)),
            proposal_only=req.proposal_only,
        )
        app_event("api_chat_response", reply_length=len(reply))
        return ChatResponse(
            reply=completion.reply, agent=completion.agent, trip_id=completion.trip_id
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
        if "turn" in locals():
            await coordinator.close(turn)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _elapsed_clock(started: float) -> str:
    """Where in the turn this happened, so a replay can be read like a log."""
    seconds = max(int(time.monotonic() - started), 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


# Proxies must not buffer or cache an event stream, or the SPA sees the whole
# turn arrive at once instead of token by token.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _sse_replay_stream(replay: dict[str, Any]) -> AsyncIterator[str]:
    """Re-emit an already-completed turn as a single-token event stream."""
    yield _sse("token", {"text": replay["reply"]})
    yield _sse(
        "done",
        {
            "reply": replay["reply"],
            "agent": replay["agent"],
            "trip_id": replay["trip_id"] or None,
        },
    )


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
_BULLET = re.compile(r"(?m)^\s*[-*]\s+([^\n]{3,100})")


def _auto_persist_itinerary(reply: str) -> bool:
    """If the agent's reply describes a multi-day itinerary but never called
    update_trip_plan, parse a minimal structure and persist it directly so the
    Itinerary panel is never left blank.

    Deliberately lenient — only requires 2+ day headers.  The agent's richer
    structured call (when it behaves) will overwrite this with better data.
    """
    matches = list(_DAY_HDR.finditer(reply))
    if len(matches) < 2:
        return False

    from tripplanner.tools import trip_planner

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
        if not stop_names:
            stop_names = _BULLET.findall(chunk)
        stops = [
            {"name": n.strip().strip("*_ "), "kind": "attraction"}
            for n in dict.fromkeys(stop_names)  # dedup, preserve order
            if n.strip().strip("*_ ")
        ][:6]
        days.append({
            "day": day_num,
            "date": "",
            "title": title,
            "summary": chunk[:250].replace("\n", " "),
            "stops": stops,
        })

    try:
        result = trip_planner.update_trip_plan.invoke(
            {"updates_json": json.dumps({"day_wise_itinerary": days})}
        )
        active = trip_planner.load_active_trip_dict() or {}
        persisted = bool(active.get("day_wise_itinerary"))
        app_event(
            "itinerary_auto_persist",
            persisted=persisted,
            result_error=str(result).lstrip().startswith("Error:"),
            recovered_days=len(days),
        )
        return persisted
    except Exception as exc:
        app_event("itinerary_auto_persist_failed", error=type(exc).__name__)
        return False


def _should_auto_persist_itinerary(tool_names_called: set[str]) -> bool:
    if not {"create_trip_plan", "update_trip_plan"}.intersection(tool_names_called):
        return False
    from tripplanner.tools import trip_planner

    try:
        active = trip_planner.load_active_trip_dict() or {}
    except Exception:
        return False
    return not active.get("day_wise_itinerary")


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply, so the SPA gets live typing and
    tool-progress over a plain HTTP stream.
    """
    from tripplanner.graph import app_graph
    from tripplanner.places_budget import places_budget_scope

    started = time.monotonic()
    header_request_id = request.headers.get("x-request-id", "")
    if header_request_id and req.request_id and header_request_id != req.request_id:
        raise HTTPException(status_code=422, detail="Request IDs in header and body must match.")
    request_id = req.request_id or header_request_id
    user_id = _set_request_user(request, req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))

    coordinator = _chat_turn_coordinator(req, request, user_id, "sse", request_id)
    try:
        turn = await coordinator.admit(
            started=started,
            transport="sse",
            user_id=user_id,
            request_id=request_id,
            message=req.message,
        )
        if isinstance(turn, TurnTerminal):
            if turn.response is not None:
                return turn.response
            terminal = {
                "reply": turn.reply,
                "agent": turn.agent,
                "trip_id": turn.trip_id or "",
            }
            return StreamingResponse(
                _sse_replay_stream(terminal),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
        assert isinstance(turn, AdmittedTurn)
    except Exception as exc:
        _record_chat_error(started, user_id=user_id, transport="sse", exc=exc)
        raise

    async def gen():
        from tripplanner.usage_attribution import annotate_current_batch, usage_scope

        reply_parts: list[str] = []
        tool_starts: dict[str, float] = {}
        # Capture tool message outputs so we can fact-check the agent's final
        # reply against them (hallucination critic).
        tool_outputs: list[ToolMessage] = []
        tool_names_called: set[str] = set()  # track which tools fired this turn
        receipts = ReceiptLog()
        yield _sse("progress", {"stage": "thinking"})
        try:
            async def budgeted_events():
                with usage_scope(
                    "user_trip",
                    interaction_id=request_id,
                    trip_id=turn.history_trip_id or "",
                    route="POST /chat/stream",
                    interaction_kind=(
                        "trip_update" if turn.history_trip_id else "new_trip"
                    ),
                ) as usage_attribution:
                    try:
                        with places_budget_scope("user_interaction"):
                            async for event in app_graph.astream_events(
                                {
                                    "messages": turn.history,
                                    "current_agent": "",
                                    "proposal_only": req.proposal_only,
                                },
                                config={"recursion_limit": _CHAT_GRAPH_RECURSION_LIMIT},
                                version="v2",
                            ):
                                yield event
                    finally:
                        if not turn.history_trip_id:
                            from tripplanner.tools.trip_planner import active_trip_id

                            annotate_current_batch(
                                interaction_id=usage_attribution.interaction_id,
                                trip_id=await asyncio.to_thread(active_trip_id) or "",
                            )

            async for ev in budgeted_events():
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
                    elif name == "request_trip_input":
                        # Without this the card simply never appears and nothing says why.
                        app_event(
                            "api_chat_input_request_rejected",
                            detail=str(getattr(output, "content", output))[:200],
                        )
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
                    tool_text = (
                        output if isinstance(output, str) else getattr(output, "content", "")
                    )
                    receipt = receipts.add(name, tool_text)
                    if receipt is not None:
                        yield _sse(
                            "receipt",
                            {
                                "seq": receipts.count,
                                "at": _elapsed_clock(started),
                                **receipt.as_dict(),
                            },
                        )
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
            partial_save_failed = not await coordinator.persist_interrupted(
                turn,
                message=req.message,
                partial_reply=partial,
                error=exc,
                tool_names=tool_names_called,
            )
            _record_chat_operation(
                started,
                user_id=user_id,
                transport="sse",
                outcome="error",
                exception=exc,
                tool_calls=len(tool_names_called),
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
        try:
            completion = await coordinator.finalize(
                turn,
                message=req.message,
                reply=reply,
                agent="trip",
                tool_names=tool_names_called,
                additional_kwargs=(
                    {graph_policy.RAN_TOOLS_KEY: sorted(tool_names_called)}
                    if tool_names_called
                    else {}
                ),
                proposal_only=req.proposal_only,
            )
        except Exception as exc:
            app_event("api_chat_stream_save_error", error=type(exc).__name__)
            _record_chat_operation(
                started,
                user_id=user_id,
                transport="sse",
                outcome="error",
                error=type(exc).__name__,
                tool_calls=len(tool_names_called),
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
        app_event("api_chat_stream_done", reply_length=len(reply))
        yield _sse(
            "done",
            {
                "reply": completion.reply,
                "agent": completion.agent,
                "trip_id": completion.trip_id,
            },
        )

    async def attributed_gen():
        from tripplanner.usage_attribution import usage_scope

        with usage_scope(
            "user_trip",
            interaction_id=request_id,
            trip_id=turn.history_trip_id or "",
            route="POST /chat/stream",
            interaction_kind="trip_update" if turn.history_trip_id else "new_trip",
        ):
            async for event in gen():
                yield event

    return StreamingResponse(
        attributed_gen(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
        background=BackgroundTask(coordinator.close, turn),
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


app.include_router(runtime_router)
app.include_router(trip_router)
app.include_router(account_router)
app.include_router(ops_router)


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
