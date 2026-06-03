"""FastAPI server for the personal assistant.

This is the **frontend-agnostic backend**. The Chainlit app (``web/app.py``)
and the React SPA (``frontend/``) are both just clients of these endpoints —
no UI framework is imported here. The trip-panel data contract lives in the
pure-Python ``web/trip_view.py`` and is served verbatim by ``GET /trip/view``.

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

import json
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from multiagent.observability import app_event, setup_logging

setup_logging()

app = FastAPI(title="Personal Assistant API", version="0.1.0")

# CORS — the SPA runs on a different origin in dev (Vite :5173). Override the
# allowed origins in production via WEB_ALLOWED_ORIGINS (comma-separated).
_origins = os.getenv("WEB_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory per-user chat history. Replace with Redis/Cosmos for multi-replica
# hosting; fine for single-process dev and the personal-use footprint.
_HISTORY: dict[str, list[BaseMessage]] = {}
_MAX_HISTORY = 40


def _history(user_id: str) -> list[BaseMessage]:
    return _HISTORY.setdefault(user_id, [])


def _trim(user_id: str) -> None:
    msgs = _HISTORY.get(user_id)
    if msgs and len(msgs) > _MAX_HISTORY:
        _HISTORY[user_id] = msgs[-_MAX_HISTORY:]


class ChatRequest(BaseModel):
    message: str
    user_id: str = "local"


class ChatResponse(BaseModel):
    reply: str
    agent: str


class SelectRequest(BaseModel):
    kind: str
    name: str
    user_id: str = "local"


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    from multiagent.graph import app_graph
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))

    history = _history(req.user_id)
    history.append(HumanMessage(content=req.message))
    result = app_graph.invoke({"messages": history, "current_agent": ""})

    reply = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and msg.type == "ai":
            reply = msg.content
            break
    history.append(AIMessage(content=reply))
    _trim(req.user_id)

    app_event("api_chat_response", reply_length=len(reply))
    return ChatResponse(reply=reply, agent=result.get("current_agent", "unknown"))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream the agent turn as Server-Sent Events.

    Emits ``token`` (assistant text deltas), ``tool`` (tool start/end), then a
    final ``done`` with the full reply — mirroring the Chainlit experience so
    the SPA gets live typing and tool-progress without coupling to Chainlit.
    """
    from multiagent.graph import app_graph
    from multiagent.user_context import set_user_id

    set_user_id(req.user_id)
    app_event("api_chat_stream_request", length=len(req.message))
    history = _history(req.user_id)
    history.append(HumanMessage(content=req.message))

    async def gen():
        reply_parts: list[str] = []
        try:
            async for ev in app_graph.astream_events(
                {"messages": history, "current_agent": ""}, version="v2"
            ):
                kind = ev.get("event")
                name = ev.get("name", "")
                data = ev.get("data", {}) or {}
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        reply_parts.append(text)
                        yield _sse("token", {"text": text})
                elif kind == "on_tool_start":
                    yield _sse("tool", {"name": name, "phase": "start"})
                elif kind == "on_tool_end":
                    yield _sse("tool", {"name": name, "phase": "end"})
        except Exception as exc:  # surface a clean error to the client
            app_event("api_chat_stream_error", error=type(exc).__name__)
            yield _sse("error", {"message": "The assistant hit an error. Please retry."})
            return

        reply = "".join(reply_parts)
        history.append(AIMessage(content=reply))
        _trim(req.user_id)
        app_event("api_chat_stream_done", reply_length=len(reply))
        yield _sse("done", {"reply": reply, "agent": "trip"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/trip/view")
async def trip_view_endpoint(
    user_id: str = "local", focus_kind: str = "", focus_name: str = ""
) -> dict:
    """Frontend-agnostic trip-panel view-model (same shape the Chainlit panel
    renders). ``focus_kind``/``focus_name`` optionally zoom one item."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    focus = {"kind": focus_kind, "name": focus_name} if focus_name else None
    return trip_view.build_view(trip, focus)


@app.post("/trip/select")
async def trip_select(req: SelectRequest) -> dict:
    """Add a hotel/attraction to the active trip (the SPA's 'Add to trip')."""
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(req.user_id)
    ok = trip_planner.add_selection(req.kind, {"name": req.name})
    trip = trip_planner.load_active_trip_dict()
    return {"ok": ok, "view": trip_view.build_view(trip, None)}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

