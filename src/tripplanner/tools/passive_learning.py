"""Automatic, retryable learning of explicitly stated conversational preferences."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from copy import deepcopy
from threading import Lock

from tripplanner.tools import about_me_extractor, profile_suggestions
from tripplanner.tools.user_preferences import mutate_preferences
from tripplanner.user_context import get_user_id

log = logging.getLogger(__name__)

# Kept for callers classifying trip-local exceptions; mixed messages still extract.
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
    """Skip only control messages; personal facts need no particular keywords."""
    text = (text or "").strip().casefold()
    return bool(text) and text not in {
        "ok", "okay", "yes", "no", "book it", "do it", "sounds good", "continue", "thanks",
    }


_LOCKS: dict[str, Lock] = {}
_LOCKS_GUARD = Lock()
_QUEUE_KEY = "_learning_pending"
_DONE_KEY = "_learning_processed"


def _user_lock() -> Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(get_user_id(), Lock())


def learn_from_message(text: str, context: list[dict] | None = None) -> list[str]:
    """Persist work before extraction; retry unfinished messages on the next sweep.

    Recent context resolves short answers, but only newly stated durable facts
    are saved. All extraction runs outside the chat's response path.
    """
    text = (text or "").strip()[:8000]
    context = (context or [])[-6:]
    skip = not has_learnable_signal(text) and not context
    identity = hashlib.sha256(json.dumps([text, context], sort_keys=True).encode()).hexdigest()
    changed: list[str] = []
    try:
        with _user_lock():
            def enqueue(prefs):
                pending = prefs.get(_QUEUE_KEY) or []
                if skip or identity in (prefs.get(_DONE_KEY) or []):
                    return None
                if any(job["id"] == identity for job in pending):
                    return None
                # Never silently evict failed work to make room for newer turns.
                sequence = int(prefs.get("_learning_sequence") or 0) + 1
                prefs["_learning_sequence"] = sequence
                pending.append({
                    "id": identity, "text": text, "context": context, "sequence": sequence,
                    "baseline": {
                        key: deepcopy(prefs.get(key)) for key in (
                            "profile", "trip_style", "budget_level", "interests", "dislikes",
                            "food_preferences", "transport_preferences", "hotel_preferences",
                            "family_members", "learned_notes",
                        )
                    },
                })
                prefs[_QUEUE_KEY] = pending
                return prefs

            prefs = mutate_preferences(enqueue)
            # A bounded drain protects the chat service after an outage. New turns
            # continue draining the durable backlog, oldest first.
            for job in (prefs.get(_QUEUE_KEY) or [])[:4]:
                baseline = job.get("baseline") or deepcopy(prefs)
                prompt = (
                    "RECENT CONTEXT (reference only):\n"
                    + json.dumps(job.get("context") or [], ensure_ascii=False)
                    + "\nNEW MESSAGE:\n" + job["text"]
                )
                try:
                    extracted = about_me_extractor.extract_about_me(
                        prompt, conversation=True, raise_on_error=True
                    )
                except Exception as exc:
                    log.warning("passive learning deferred: %s", type(exc).__name__)
                    def defer(current):
                        pending = current.get(_QUEUE_KEY) or []
                        failed = [item for item in pending if item["id"] == job["id"]]
                        if not failed:
                            return None
                        current[_QUEUE_KEY] = [
                            item for item in pending if item["id"] != job["id"]
                        ] + failed
                        return current

                    mutate_preferences(defer)
                    continue

                def apply(current):
                    changed.clear()
                    if job["id"] in (current.get(_DONE_KEY) or []):
                        return None
                    if not any(
                        item["id"] == job["id"] for item in (current.get(_QUEUE_KEY) or [])
                    ):
                        return None
                    changed.extend(profile_suggestions.save_extracted(
                        current, extracted, job["text"], baseline,
                        sequence=job.get("sequence", 0),
                    ))
                    current[_QUEUE_KEY] = [
                        item for item in (current.get(_QUEUE_KEY) or []) if item["id"] != job["id"]
                    ]
                    current[_DONE_KEY] = [*(current.get(_DONE_KEY) or []), job["id"]][-128:]
                    return current

                prefs = mutate_preferences(apply)
    except Exception as exc:
        log.warning("passive learning sweep failed: %s", type(exc).__name__)
    return changed
