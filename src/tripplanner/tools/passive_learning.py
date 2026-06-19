"""Post-turn passive-learning sweep (safety net).

Continuous learning during chat normally relies on the agent *choosing* to call
the extraction tools (``update_user_profile``, ``add_family_member``,
``add_user_interest``, ...). When the model is busy planning — or a cheaper
model is in use — those calls get dropped and the durable signal is lost.

This module is the deterministic safety net: after each user turn it runs the
same conservative LLM extractor used by the "About me" settings blurb over the
latest user message and overlays whatever it finds ADDITIVELY. It never removes
anything and dedupes against what's already saved (including anything the agent
captured this same turn), so double-capture is harmless.

Best-effort: every entry point swallows errors and never raises into the chat
turn.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from tripplanner.tools import about_me_extractor
from tripplanner.tools.preferences_merge import additive_overlay_extracted
from tripplanner.tools.user_preferences import load_preferences, save_preferences

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


def has_learnable_signal(text: str) -> bool:
    """True when ``text`` is worth running the (billed) extractor over."""
    text = (text or "").strip()
    if len(text) < _MIN_CHARS:
        return False
    return bool(_SIGNAL_RE.search(text))


def learn_from_message(text: str) -> list[str]:
    """Extract durable prefs from one user message and overlay additively.

    Returns the list of top-level preference keys touched (empty on no-op or on
    any failure). Never raises.
    """
    try:
        text = (text or "").strip()
        if not has_learnable_signal(text):
            return []
        extracted: dict[str, Any] = about_me_extractor.extract_about_me(text) or {}
        learned = extracted.pop("_learned_notes_to_append", None)
        if not extracted and not learned:
            return []

        prefs = load_preferences()
        touched: list[str] = []
        if extracted:
            prefs = additive_overlay_extracted(prefs, extracted)
            touched = list(extracted.keys())
        if learned:
            existing = list(prefs.get("learned_notes") or [])
            seen = {
                (n.get("note") or "").strip().lower()
                for n in existing
                if isinstance(n, dict)
            }
            for entry in learned:
                if not isinstance(entry, dict):
                    continue
                note = (entry.get("note") or "").strip()
                if not note or note.lower() in seen:
                    continue
                seen.add(note.lower())
                existing.append(entry)
            prefs["learned_notes"] = existing
            touched.append("learned_notes")

        if touched:
            save_preferences(prefs)
        return touched
    except Exception as exc:  # never break the chat turn
        log.warning("passive learning sweep failed: %s", exc)
        return []
