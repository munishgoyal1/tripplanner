"""FastAPI server for the personal assistant."""

from __future__ import annotations

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from multiagent.observability import app_event, setup_logging

setup_logging()

app = FastAPI(title="Personal Assistant API", version="0.1.0")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    agent: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    from multiagent.graph import app_graph

    app_event("api_chat_request", length=len(req.message), words=len(req.message.split()))
    result = app_graph.invoke({
        "messages": [HumanMessage(content=req.message)],
        "current_agent": "",
    })

    reply = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and msg.type == "ai":
            reply = msg.content
            break

    app_event("api_chat_response", reply_length=len(reply))
    return ChatResponse(reply=reply, agent=result.get("current_agent", "unknown"))


@app.get("/trip/view")
async def trip_view_endpoint(user_id: str = "local", focus_kind: str = "", focus_name: str = "") -> dict:
    """Frontend-agnostic trip-panel view-model.

    Returns the same JSON the Chainlit panel renders, so an alternative
    React/HTML frontend can consume it directly. ``user_id`` selects whose
    active trip to read; ``focus_kind``/``focus_name`` optionally zoom one item.
    """
    from multiagent.tools import trip_planner
    from multiagent.user_context import set_user_id
    from multiagent.web import trip_view

    set_user_id(user_id)
    trip = trip_planner.load_active_trip_dict()
    focus = {"kind": focus_kind, "name": focus_name} if focus_name else None
    return trip_view.build_view(trip, focus)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
