"""Chainlit chat UI for the trip planner.

Runs as: ``chainlit run src/multiagent/web/app.py``

- Each browser session gets a stable Chainlit ``cl.user_session`` ID, which
  becomes the user ID for storage. No login required.
- Conversation history accumulates inside ``cl.user_session``.
- The existing LangGraph agent runs unchanged \u2014 only the persistence layer
  is swapped to Cosmos when ``COSMOS_ENDPOINT`` is set.
"""

from __future__ import annotations

import asyncio
import logging

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

from multiagent.graph import app_graph
from multiagent.user_context import set_user_id

log = logging.getLogger(__name__)

WELCOME = (
    "\u2708\ufe0f **Trip Planner**\n\n"
    "Tell me where you'd like to go and I'll plan it end-to-end \u2014 flights, "
    "hotels, activities and a day-wise itinerary.\n\n"
    "_Try: \"Plan a 5-day family trip to Goa in January for 2 adults and 1 child\"_"
)


def _last_ai_message(messages: list) -> AIMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg
    return None


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialize per-session state and greet the user."""
    session_id = cl.user_session.get("id") or "anonymous"
    cl.user_session.set("user_id", str(session_id))
    cl.user_session.set("messages", [])
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(msg: cl.Message) -> None:
    """Handle one user turn: run the graph, stream the assistant reply."""
    user_id = cl.user_session.get("user_id") or "anonymous"
    set_user_id(user_id)

    messages: list = cl.user_session.get("messages") or []
    messages.append(HumanMessage(content=msg.content))

    thinking = cl.Message(content="")
    await thinking.send()

    try:
        # LangGraph's sync invoke runs inside a worker thread to avoid
        # blocking Chainlit's event loop.
        result = await asyncio.to_thread(
            app_graph.invoke,
            {"messages": messages, "current_agent": ""},
        )
    except Exception as exc:  # surface failure to the user without crashing the chat
        log.exception("graph invocation failed")
        thinking.content = (
            f"\u26a0\ufe0f Something went wrong: `{exc.__class__.__name__}: {exc}`"
        )
        await thinking.update()
        return

    new_messages = list(result.get("messages", messages))
    cl.user_session.set("messages", new_messages)

    last_ai = _last_ai_message(new_messages)
    thinking.content = last_ai.content if last_ai else "_(no response)_"
    await thinking.update()
