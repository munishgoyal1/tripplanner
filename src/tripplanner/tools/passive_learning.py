"""Post-turn passive-learning sweep (safety net).

Continuous learning during chat normally relies on the agent *choosing* to call
the extraction tools (``update_user_profile``, ``add_family_member``,
``add_user_interest``, ...). When the model is busy planning — or a cheaper
model is in use — those calls get dropped and the durable signal is lost.

This module is the deterministic safety net: after each user turn it runs the
same conservative LLM extractor used by the "About me" settings blurb over the
latest user message. What it finds is queued as a pending *suggestion* rather
than saved, so nothing becomes durable until the user confirms it in chat.

Best-effort: every entry point swallows errors and never raises into the chat
turn.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from tripplanner.tools import about_me_extractor, profile_suggestions

log = logging.getLogger(__name__)

# Cheap pre-filter: only spend an LLM call when the message plausibly carries a
# durable personal signal. Skips control phrases ("book it", "yes", "ok"), bare
# logistics, and very short replies.
_SIGNAL_RE = re.compile(
    r"\b("
    r"i\s*am|i'm|i\s*love|i\s*like|i\s*hate|i\s*prefer|i\s*enjoy|i\s*avoid|"
    r"my\s+(wife|husband|partner|son|daughter|kid|kids|child|children|mother|"
    r"father|mom|dad|parents|family|friend|dog|cat|pet)|"
    r"we\s+(went|visited|loved|stayed|usually|always|prefer)|"
    r"allergic|allergy|vegetarian|vegan|halal|kosher|gluten|jain|"
    r"live\s+in|based\s+in|i\s+work|i'm\s+a|i\s+am\s+a|"
    r"never|always|usually|afraid\s+of|scared\s+of|wheelchair|mobility"
    r")\b",
    re.I,
)

_MIN_CHARS = 12

# Trip-scoped cues: when present, the statement is a ONE-OFF exception for the
# current trip, NOT a durable preference. Routing it to the active trip's
# constraints prevents "3-star is fine just this time" from being learned as a
# permanent "prefers 3-star hotels" preference.
_TRIP_SCOPE_RE = re.compile(
    r"\b("
    r"just\s+(for\s+)?this\s+(trip|time|one)|"
    r"this\s+trip\s+only|only\s+this\s+trip|"
    r"this\s+time|for\s+now|for\s+this\s+one|on\s+this\s+one|"
    r"make\s+an\s+exception|just\s+once|one[\s-]?off|"
    r"only\s+for\s+(this|now)"
    r")\b",
    re.I,
)


def has_trip_scope_cue(text: str) -> bool:
    """True when ``text`` frames a statement as a one-off, trip-only exception."""
    return bool(_TRIP_SCOPE_RE.search(text or ""))


def has_learnable_signal(text: str) -> bool:
    """True when ``text`` is worth running the (billed) extractor over."""
    text = (text or "").strip()
    if len(text) < _MIN_CHARS:
        return False
    return bool(_SIGNAL_RE.search(text))


def learn_from_message(text: str) -> list[str]:
    """Extract durable prefs from one user message and queue them for review.

    Returns the ids of the suggestions raised (empty on no-op or on any
    failure). Nothing is written to the durable profile here: the user confirms
    each suggestion through :mod:`tripplanner.tools.profile_suggestions`.
    Trip-scoped one-offs ("just for this trip") are still routed straight to the
    active trip's constraints and return ``["trip_constraint"]``. Never raises.
    """
    try:
        text = (text or "").strip()
        # One-off exceptions go to the trip, never to durable preferences.
        if has_trip_scope_cue(text):
            try:
                from tripplanner.tools import trip_planner

                if trip_planner.add_trip_constraint(text):
                    return ["trip_constraint"]
            except Exception as exc:  # pragma: no cover - best-effort
                log.warning("trip-scope constraint capture failed: %s", exc)
            return []
        if not has_learnable_signal(text):
            return []
        extracted: dict[str, Any] = about_me_extractor.extract_about_me(text) or {}
        learned = extracted.pop("_learned_notes_to_append", None)
        if not extracted and not learned:
            return []

        records = profile_suggestions.build_suggestions(extracted, learned, text)
        return [record["id"] for record in profile_suggestions.queue_suggestions(records)]
    except Exception as exc:  # never break the chat turn
        log.warning("passive learning sweep failed: %s", exc)
        return []
