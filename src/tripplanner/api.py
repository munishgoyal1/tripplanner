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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from tripplanner import config as _config  # noqa: F401  -- import triggers load_dotenv()
from tripplanner.observability import app_event, setup_logging
from tripplanner.web import oauth

setup_logging()

app = FastAPI(title="Personal Assistant API", version="0.1.0")

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


def _save_chat(tid_before: str | None, history: list[BaseMessage]) -> str | None:
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
    if is_switch and not chat_store.transcript(tid_after) and len(history) >= 2:
        # Brand-new destination chat: distil portable context from the prior
        # conversation so the fresh chat isn't cold. Best-effort (LLM).
        prev_dest = trip_planner.saved_trip_destination(tid_before or "")
        active = trip_planner.load_active_trip_dict() or {}
        new_dest = str(active.get("destination") or "")
        carryover = chat_carryover.distill(history[:-2], prev_dest, new_dest)

    return chat_store.persist_turn(tid_before, tid_after, history, carryover)


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
    message: str
    user_id: str = "local"


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
    replace_stay: bool = True


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
    # Free-text "About me" blurb. When provided and changed, the backend runs
    # the LLM extractor and additively overlays the structured fields it finds.
    about_me: str | None = None
    # System-authored profile summary. When provided, it's stored verbatim
    # (user correction / reset via empty string); not the same as about_me.
    profile_summary: str | None = None


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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    from tripplanner.graph import app_graph
    from tripplanner.usage import cap_message, is_over_cap
    from tripplanner.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    over, usage = is_over_cap(req.user_id)
    if over:
        msg = cap_message(usage)
        app_event("api_chat_capped", cost_usd=usage.get("cost_usd"))
        return ChatResponse(reply=msg, agent="cap")

    history_tid, history = await asyncio.to_thread(_load_chat)
    history.append(HumanMessage(content=req.message))
    result = await asyncio.to_thread(
        app_graph.invoke, {"messages": history, "current_agent": ""}
    )

    reply = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and msg.type == "ai":
            reply = msg.content
            break
    # Hallucination critic: log unverified prices/times/URLs as telemetry only
    # (internal QA signal — not surfaced to the user to avoid noisy footers).
    from tripplanner.hallucination_critic import critique

    issues = critique(reply, result.get("messages", []))
    if issues:
        app_event("hallucination_critic", issues=len(issues), claims=issues)
    history.append(AIMessage(content=reply))
    tid_after = await asyncio.to_thread(_save_chat, history_tid, history)
    _schedule_learning_sweep(req.user_id, req.message)

    app_event("api_chat_response", reply_length=len(reply))
    return ChatResponse(
        reply=reply, agent=result.get("current_agent", "unknown"), trip_id=tid_after
    )


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


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply, so the SPA gets live typing and
    tool-progress over a plain HTTP stream.
    """
    from tripplanner.graph import app_graph
    from tripplanner.usage import cap_message, is_over_cap
    from tripplanner.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))

    over, usage = is_over_cap(req.user_id)
    if over:
        msg = cap_message(usage)
        app_event("api_chat_stream_capped", cost_usd=usage.get("cost_usd"))

        async def _capped():
            yield _sse("token", {"text": msg})
            yield _sse("done", {"reply": msg, "agent": "cap"})

        return StreamingResponse(_capped(), media_type="text/event-stream")

    history_tid, history = await asyncio.to_thread(_load_chat)
    history.append(HumanMessage(content=req.message))

    async def gen():
        reply_parts: list[str] = []
        tool_starts: dict[str, float] = {}
        # Capture tool message outputs so we can fact-check the agent's final
        # reply against them (hallucination critic).
        tool_outputs: list[ToolMessage] = []
        tool_names_called: set[str] = set()  # track which tools fired this turn
        try:
            async for ev in app_graph.astream_events(
                {"messages": history, "current_agent": ""}, version="v2"
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
                    started = tool_starts.pop(run_id, None)
                    duration_ms = int((time.monotonic() - started) * 1000) if started else None
                    payload: dict[str, Any] = {"name": name, "phase": "end"}
                    if duration_ms is not None:
                        payload["duration_ms"] = duration_ms
                    output = data.get("output")
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
        except Exception as exc:  # surface a clean error to the client
            app_event("api_chat_stream_error", error=type(exc).__name__)
            # Persist whatever we have so a tool side-effect during the turn
            # (e.g. a freshly created trip) doesn't leave the conversation
            # orphaned — otherwise the active trip exists with an empty chat
            # that vanishes on refresh.
            partial = "".join(reply_parts)
            history.append(AIMessage(content=partial or "(interrupted)"))
            try:
                _save_chat(history_tid, history)
            except Exception:
                pass
            yield _sse("error", {"message": "The assistant hit an error. Please retry."})
            return

        reply = "".join(reply_parts)
        # Hallucination critic: log unverified prices/times/URLs as telemetry
        # only (internal QA signal — not surfaced to the user).
        from tripplanner.hallucination_critic import critique

        issues = critique(reply, tool_outputs)
        if issues:
            app_event("hallucination_critic", issues=len(issues), claims=issues)
        history.append(AIMessage(content=reply))
        # Safety net: if the agent described a day-wise itinerary but never
        # called update_trip_plan, parse the reply and persist it directly so
        # the Itinerary panel is never left blank.
        if "update_trip_plan" not in tool_names_called:
            await asyncio.to_thread(_auto_persist_itinerary, reply)
        tid_after = await asyncio.to_thread(_save_chat, history_tid, history)
        _schedule_learning_sweep(req.user_id, req.message)
        app_event("api_chat_stream_done", reply_length=len(reply))
        yield _sse("done", {"reply": reply, "agent": "trip", "trip_id": tid_after})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/chat/history")
async def chat_history(user_id: str = "local", trip_id: str = "") -> dict:
    """The persisted transcript for the user's *currently active* trip.

    Lets the SPA restore the conversation + itinerary summary after a refresh,
    and load the right conversation when the user switches saved trips.
    """
    from tripplanner.user_context import set_user_id
    from tripplanner.tools.trip_planner import active_trip_id
    from tripplanner.web import chat_store

    set_user_id(user_id)
    tid = trip_id.strip() or await asyncio.to_thread(active_trip_id) or ""
    rows = await asyncio.to_thread(chat_store.transcript, tid)
    return {"trip_id": tid, "messages": rows}


@app.get("/trip/view")
async def trip_view_endpoint(
    user_id: str = "local", focus_kind: str = "", focus_name: str = ""
) -> dict:
    """Frontend-agnostic trip-panel view-model. ``focus_kind``/``focus_name``
    optionally zoom one item."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(user_id)
    focus = {"kind": focus_kind, "name": focus_name} if focus_name else None
    return await asyncio.to_thread(trip_operations.build_view, focus)


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


@app.get("/trip/map")
async def trip_map_endpoint(user_id: str = "local") -> dict:
    """Interactive-map view-model: geocoded, day-tagged pins + route bands."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(user_id)
    return await asyncio.to_thread(trip_operations.build_map)


@app.get("/destination/overview")
async def destination_overview_endpoint(
    destination: str = "", user_id: str = "local", news: bool = True
) -> dict:
    """Destination-level overview (photos, key attractions, reviews, news).

    When ``destination`` is omitted, falls back to the active trip's
    destination so the SPA can show "about the place" before any selections.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_view

    set_user_id(user_id)
    if not destination:
        trip = trip_planner.load_active_trip_dict()
        destination = str((trip or {}).get("destination") or "")
    return await asyncio.to_thread(
        trip_view.build_destination_overview, destination, include_news=news
    )



@app.post("/trip/select")
async def trip_select(req: SelectRequest) -> dict:
    """Add a hotel/attraction to the active trip (the SPA's 'Add to trip')."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(req.user_id)
    return await asyncio.to_thread(
        trip_operations.select,
        req.kind,
        req.name,
        start_day=req.start_day,
        end_day=req.end_day,
        replace_stay=req.replace_stay,
    )


@app.post("/trip/deselect")
async def trip_deselect(req: SelectRequest) -> dict:
    """Remove a hotel/attraction from the active trip (the SPA's 'Remove')."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(req.user_id)
    return await asyncio.to_thread(trip_operations.deselect, req.kind, req.name)


@app.get("/trip/itinerary")
async def trip_itinerary_endpoint(user_id: str = "local") -> dict:
    """Structured day-by-day itinerary view-model (the Itinerary tab)."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(user_id)
    return await asyncio.to_thread(trip_operations.build_itinerary)


@app.post("/trip/stop/booked")
async def trip_stop_booked(req: StopBookedRequest) -> dict:
    """Toggle one itinerary stop's booked flag (the Itinerary checkbox)."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(req.user_id)
    return await asyncio.to_thread(
        trip_operations.set_stop_booked, req.day, req.name, req.booked
    )


@app.get("/trips")
async def trips_list(user_id: str = "local") -> dict:
    """All saved trips for the user (the SPA's 'My trips' switcher)."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id

    set_user_id(user_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"trips": trips}


@app.post("/trips/switch")
async def trips_switch(req: TripIdRequest) -> dict:
    """Make a saved trip active (auto-saving whatever was active) and return
    the refreshed trip-panel view."""
    from tripplanner.user_context import set_user_id
    from tripplanner.web import trip_operations

    set_user_id(req.user_id)
    return await asyncio.to_thread(trip_operations.switch_trip, req.trip_id)


@app.post("/trips/delete")
async def trips_delete(req: TripIdRequest) -> dict:
    """Delete a single saved trip AND its chat history; returns the refreshed
    saved-trips list."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store

    set_user_id(req.user_id)
    await asyncio.to_thread(trip_planner.delete_saved_trip, req.trip_id)
    # Also erase that trip's persisted conversation so no orphaned data lingers.
    await asyncio.to_thread(chat_store.clear, req.trip_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    return {"ok": True, "trips": trips}


@app.post("/trip/new")
async def trip_new(req: UserRequest) -> dict:
    """Start a fresh planning chat: clear the active trip + the general chat
    bucket so the next conversation begins clean. Saved trips are untouched."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store

    set_user_id(req.user_id)
    await asyncio.to_thread(trip_planner.start_new_trip)
    await asyncio.to_thread(chat_store.clear, None)
    return {"ok": True}



@app.get("/trip/export.ics")
async def trip_export_ics(user_id: str = "local") -> Response:
    """Download the active trip as an iCalendar (.ics) file."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web.ics_export import build_ics

    set_user_id(user_id)
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
    user_id: str = "local",
    include_photos: str = "1",
    include_map_circuit: str = "1",
    template: str = "detailed",
    auto_print: str = "0",
) -> Response:
    """Return a print-ready HTML itinerary suitable for Save-as-PDF."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web.itinerary_export import build_export_html, parse_export_bool

    set_user_id(user_id)
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
    user_id: str = "local",
    template: str = "detailed",
) -> Response:
    """Return a downloadable itinerary PDF generated server-side."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id

    set_user_id(user_id)
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return JSONResponse({"error": "no active trip"}, status_code=404)

    try:
        from tripplanner.web.itinerary_pdf import build_itinerary_pdf_bytes

        pdf_bytes = build_itinerary_pdf_bytes(plan, template=template)
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
    """Send the itinerary export to an email address (SMTP when configured).

    If SMTP is not configured, returns a `mailto:` fallback so the frontend can
    open the user's mail client with a prefilled subject/body.
    """
    from email.message import EmailMessage
    from urllib.parse import quote
    import smtplib

    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web.itinerary_export import build_export_html
    from tripplanner.web.share import mint_for_active_trip

    set_user_id(req.user_id)
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
            poller = client.begin_send(message)
            poller.result()
            app_event("api_trip_export_email_sent", destination=destination, provider="acs")
            return {"ok": True, "message": f"Itinerary sent to {req.email}."}
        except Exception as exc:
            app_event("api_trip_export_email_error", error=type(exc).__name__, provider="acs")

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
            "mailto": f"mailto:{quote(req.email, safe='')}?subject={quote(subject, safe='')}&body={body}",
            "message": "SMTP is not configured; opened mail client fallback.",
        }

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
        return {"ok": False, "error": "email_send_failed", "message": "Could not send email."}

    app_event("api_trip_export_email_sent", destination=destination)
    return {"ok": True, "message": f"Itinerary sent to {req.email}."}


@app.post("/trip/share")
async def trip_share(req: SelectRequest, request: Request) -> dict:
    """Mint an opaque read-only share token for the active trip.

    Re-using ``SelectRequest`` only for its ``user_id`` field — ``kind``/``name``
    are ignored. Returns ``{token, url}`` or ``{error}`` if no active plan.
    """
    from tripplanner.user_context import set_user_id
    from tripplanner.web.share import mint_for_active_trip

    set_user_id(req.user_id)
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
async def trip_shared_import(token: str, req: UserRequest) -> dict:
    """Import a shared snapshot into the caller's own editable trip space."""
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id
    from tripplanner.web import share, trip_view

    snapshot = share.resolve(token)
    if snapshot is None:
        return JSONResponse({"error": "invalid or expired share link"}, status_code=404)
    set_user_id(req.user_id)
    imported = trip_planner.import_shared_trip_snapshot(snapshot.get("plan") or {})
    return {"ok": True, "view": trip_view.build_view(imported, None)}


@app.get("/preferences")
async def get_preferences(user_id: str = "local") -> dict:
    """Return the editable subset of the user's saved preferences (for the
    SPA settings panel)."""
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.user_context import set_user_id

    set_user_id(user_id)
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
    }


@app.post("/preferences")
async def save_preferences_endpoint(req: PreferencesRequest) -> dict:
    """Merge the provided preference fields and persist them (additive — only
    keys present in the request are written)."""
    from tripplanner.tools import preferences_merge
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.user_context import set_user_id

    set_user_id(req.user_id)
    prefs = prefs_store.load_preferences()
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
        food["dietary"] = [d.strip() for d in req.dietary if d.strip()]
    if req.interests is not None:
        prefs["interests"] = [d.strip() for d in req.interests if d.strip()]
    if req.dislikes is not None:
        prefs["dislikes"] = [d.strip() for d in req.dislikes if d.strip()]

    prefs["profile"] = profile
    prefs["transport_preferences"] = transport
    prefs["hotel_preferences"] = hotel
    prefs["food_preferences"] = food

    # Free-text About-me: extract structured fields and overlay additively
    # (shared logic in preferences_merge).
    extracted_keys: list[str] = []
    if req.about_me is not None:
        prefs, extracted_keys = preferences_merge.apply_about_me(prefs, req.about_me)

    prefs_store.save_preferences(prefs)

    # User-corrected / reset profile summary is stored verbatim (and stamps the
    # current digest so the background sweep won't immediately overwrite it).
    if req.profile_summary is not None:
        from tripplanner.tools import profile_summary as profile_summary_mod

        profile_summary_mod.set_summary(req.profile_summary)

    app_event("api_preferences_saved")
    return {"ok": True, "about_me_extracted": extracted_keys}


@app.post("/profile/summary/regenerate")
async def regenerate_profile_summary(req: SelectRequest) -> dict:
    """Force a fresh LLM-authored profile summary for the user.

    Re-uses ``SelectRequest`` only for ``user_id`` (``kind``/``name`` ignored).
    Returns the new ``profile_summary`` (may be empty if there's nothing durable
    to summarize or the model is unavailable).
    """
    from tripplanner.tools import profile_summary as profile_summary_mod
    from tripplanner.user_context import set_user_id

    set_user_id(req.user_id)
    summary = profile_summary_mod.update_summary(force=True)
    app_event("api_profile_summary_regenerated")
    return {"ok": True, "profile_summary": summary}

@app.post("/account/privacy")
async def account_privacy_action(req: PrivacyActionRequest) -> dict:
    """Run user-requested privacy actions (GDPR-style controls).

    Supported actions:
    - ``delete_trip_history``: remove all saved/active trips and chat history.
    - ``clear_all_data``: delete trips/chats + reset preferences + clear usage/cache.
    - ``delete_account``: same as clear-all; identity provider account remains external.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.usage import clear_usage
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store
    import tripplanner.tools_cache as tools_cache

    set_user_id(req.user_id)

    if req.action in {"clear_all_data", "delete_account"}:
        if req.confirm_text.strip().upper() != "DELETE":
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Type DELETE to confirm this action.",
            }

    deleted_trips = await asyncio.to_thread(trip_planner.clear_all_trip_history)
    deleted_chats = await asyncio.to_thread(chat_store.clear_all)

    deleted_usage = 0
    deleted_cache = 0
    reset_prefs = False

    if req.action in {"clear_all_data", "delete_account"}:
        await asyncio.to_thread(prefs_store.reset_preferences)
        reset_prefs = True
        deleted_usage = await asyncio.to_thread(clear_usage, req.user_id)
        deleted_cache = await asyncio.to_thread(tools_cache.clear_cache_for_user, req.user_id)

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
async def account_migrate_guest(req: GuestMigrateRequest) -> dict:
    """Copy trips and preferences from a guest (web-*) identity into an
    authenticated account.

    Called once after Google OAuth sign-in when the browser had existing guest
    data. Safe to call multiple times — already-migrated trips are skipped.
    Returns {ok, copied_trips, skipped_trips, copied_prefs}.
    """
    from tripplanner.tools import trip_planner, user_preferences as prefs_store
    from tripplanner.user_context import set_user_id
    from tripplanner.web import chat_store

    guest_id = (req.guest_id or "").strip()
    auth_id = (req.user_id or "").strip()
    if not guest_id.startswith("web-") or not auth_id:
        return {"ok": False, "error": "invalid_ids"}

    # ── 1. Copy saved trips from guest into authenticated user ──────────────
    set_user_id(guest_id)
    guest_trips = await asyncio.to_thread(trip_planner.list_saved_trips)

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
        # Load the full plan from the guest store.
        set_user_id(guest_id)
        full_plan = await asyncio.to_thread(trip_planner._load_history_trip, tid)
        if not full_plan:
            skipped_trips += 1
            continue
        # Write it into the authenticated user's store.
        set_user_id(auth_id)
        await asyncio.to_thread(trip_planner._mirror_to_history, full_plan)
        copied_trips += 1

    # ── 2. Copy preferences if the authenticated user has none yet ──────────
    set_user_id(auth_id)
    auth_prefs = prefs_store.load_preferences()
    copied_prefs = False
    if not auth_prefs.get("about_me") and not auth_prefs.get("interests"):
        set_user_id(guest_id)
        guest_prefs = prefs_store.load_preferences()
        if guest_prefs.get("about_me") or guest_prefs.get("interests"):
            set_user_id(auth_id)
            prefs_store.save_preferences(guest_prefs)
            copied_prefs = True

    # ── 3. Copy the active trip (if guest has one and auth user has none) ───
    set_user_id(guest_id)
    guest_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
    set_user_id(auth_id)
    auth_active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
    copied_chat = False
    if guest_active and not auth_active:
        await asyncio.to_thread(trip_planner._save_active_trip, guest_active)

    # ── 4. Copy the active trip's chat so the conversation isn't lost ───────
    guest_active_id = (guest_active or {}).get("trip_id")
    auth_active_id = (auth_active or {}).get("trip_id")
    # Copy only if we just imported the active trip (auth had none before).
    if guest_active_id and not auth_active:
        set_user_id(guest_id)
        guest_msgs = await asyncio.to_thread(chat_store.load, guest_active_id)
        if not guest_msgs:
            # Fall back to the general bucket (pre-trip conversation).
            guest_msgs = await asyncio.to_thread(chat_store.load, None)
        if guest_msgs:
            set_user_id(auth_id)
            await asyncio.to_thread(chat_store.save, guest_active_id, guest_msgs)
            copied_chat = True

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
async def account_guest_data_summary(user_id: str) -> dict:
    """How much data does a guest (web-*) account have?

    Called by the frontend after OAuth login to decide whether to offer
    the guest-import banner.
    """
    from tripplanner.tools import trip_planner
    from tripplanner.user_context import set_user_id

    guest_id = (user_id or "").strip()
    if not guest_id.startswith("web-"):
        return {"has_data": False, "trip_count": 0}
    set_user_id(guest_id)
    trips = await asyncio.to_thread(trip_planner.list_saved_trips)
    active = await asyncio.to_thread(trip_planner.load_active_trip_dict)
    count = len(trips) + (1 if active and not trips else 0)
    return {"has_data": count > 0, "trip_count": count}


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
        "redirect_uri": oauth.redirect_uri(str(request.base_url)),
    }


@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    """Return the signed-in identity (from the session cookie) or anonymous."""
    session = oauth.read_session(request.cookies.get(oauth.SESSION_COOKIE))
    if not session:
        return {"authenticated": False}
    return {"authenticated": True, **session}


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
        prefs = prefs_store.load_preferences()
        profile_blob = dict(prefs.get("profile") or {})
        if not profile_blob.get("display_name") and profile.get("name"):
            profile_blob["display_name"] = profile["name"].split()[0]
            prefs["profile"] = profile_blob
            prefs_store.save_preferences(prefs)
    except Exception:
        pass  # profile seeding is best-effort; never block login

    app_event("api_oauth_login", provider="google")
    token = oauth.make_session_token(
        identifier, profile.get("name", ""), profile.get("email", ""), profile.get("picture", "")
    )
    res = RedirectResponse(post_login or "/", status_code=302)
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
async def usage_for_user(user_id: str = "local") -> dict:
    """Return this month's LLM token + cost usage for ``user_id`` and the cap."""
    from tripplanner.usage import get_cap_usd, get_usage, is_over_cap

    over, doc = is_over_cap(user_id)
    return {
        "user_id": user_id,
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

