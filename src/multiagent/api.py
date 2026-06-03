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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
