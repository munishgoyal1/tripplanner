"""Distil relevant context when the user switches to a new destination mid-chat.

When someone is planning Mexico and suddenly says "plan me a trip to Kashmir",
the agent creates a fresh trip (and a fresh chat bucket). We don't copy the old
verbatim transcript into the new chat — instead we seed the new conversation with
a short, friendly carryover note that distils only the RELEVANT, trip-agnostic
details the traveller already shared (companions, budget, pace, interests, hard
constraints). Global preferences keep flowing through the agent's normal context;
this just rescues the things stated in the previous chat.

One small LLM call, best-effort: any failure (missing config, network) returns
``""`` and the new chat simply starts without a carryover note.
"""

from __future__ import annotations

import logging

from langchain_core.messages import BaseMessage

log = logging.getLogger(__name__)

_MAX_PREV_TURNS = 24  # cap the prior transcript we feed the distiller

_SYSTEM_PROMPT = """You help an AI trip-planning assistant hand off context when a
traveller abruptly switches from planning one destination to a brand-new one.

You are given the recent conversation about their PREVIOUS destination and the
name of the NEW destination they just asked to plan. Write a SHORT, warm note (in
the assistant's first-person voice) that:
- opens with a one-line transition acknowledging the switch to the new place,
- then carries over ONLY the details that stay relevant across destinations:
  who they're travelling with, group size/ages, rough budget, trip pace, hotel
  comfort level, dietary/accessibility needs, and clear interests or dislikes.

Rules:
- <= 90 words, plain prose, no bullet lists, no headings.
- Do NOT carry over anything destination-specific (old dates, old cities, old
  hotels/flights). Those don't apply to the new trip.
- NEVER invent facts. If the previous chat shared nothing portable, just write a
  single friendly line welcoming them to plan the new destination.
- End by inviting them to confirm dates/details for the new trip.
"""


def _format_prev(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for m in messages[-_MAX_PREV_TURNS:]:
        mtype = getattr(m, "type", "")
        role = "Traveller" if mtype == "human" else "Assistant" if mtype == "ai" else None
        if role is None:
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        text = text.strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def distill(
    prev_messages: list[BaseMessage],
    prev_destination: str,
    new_destination: str,
) -> str:
    """Return a short carryover note for the new trip's chat, or ``""``.

    Best-effort: returns ``""`` on missing config, an empty prior conversation,
    or any LLM error.
    """
    transcript = _format_prev(prev_messages)
    if not transcript.strip():
        return ""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import AzureChatOpenAI

        from tripplanner.config import get_settings
    except Exception as exc:  # pragma: no cover - import errors are environmental
        log.warning("chat_carryover: imports failed (%s); skipping", exc)
        return ""

    payload = (
        f"PREVIOUS destination: {prev_destination or 'unknown'}\n"
        f"NEW destination: {new_destination or 'unknown'}\n\n"
        f"Recent conversation:\n{transcript}"
    )
    try:
        s = get_settings()
        if not (s.azure_openai_endpoint and s.azure_openai_api_key):
            return ""
        llm = AzureChatOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            azure_deployment=s.azure_openai_deployment,
            api_version=s.azure_openai_api_version,
            temperature=0.3,
        )
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=payload),
            ]
        )
    except Exception as exc:
        log.warning("chat_carryover: LLM call failed (%s); skipping", exc)
        return ""

    content = getattr(response, "content", "")
    if not isinstance(content, str):
        content = str(content)
    return content.strip()
