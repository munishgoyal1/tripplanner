"""System-authored running summary of the user.

This is the second of three learning layers:

1. ``about_me``   — USER-authored free text. Source of truth, only the user edits it.
2. ``profile_summary`` (this module) — SYSTEM (LLM)-authored synthesis across ALL
   durable signals. Evolves after interactions; the user may correct or reset it.
3. trip constraints — one-off exceptions stored ON the active trip; they die with
   the trip and never touch durable preferences.

``update_summary()`` is called from the post-turn background sweep. It is gated by a
cheap digest of the durable signals so the LLM is only invoked when something durable
actually changed — trip-scoped one-offs and routine chatter cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from tripplanner.tools import user_preferences

log = logging.getLogger(__name__)
_ANY_UPDATED_AT = object()

# Durable fields that feed the summary. about_me is treated as highest authority.
_DIGEST_KEYS = (
    "about_me",
    "profile",
    "trip_style",
    "budget_level",
    "family",
    "family_members",
    "interests",
    "dislikes",
    "food_preferences",
    "hotel_preferences",
    "transport_preferences",
    "accessibility_needs",
    "learned_notes",
    "past_trips",
    "past_trip_mentions",
)

_SYSTEM_PROMPT = """You write a concise, factual running summary of a traveller for an
AI trip-planning assistant. The summary is shown back to the user for transparency,
so it must be accurate, neutral, and never invent facts.

You are given the user's saved data as JSON. Synthesize a single short paragraph
(<= 120 words, no bullet lists, no headings) capturing the durable, planning-relevant
truths: who they are and who they travel with, home base, budget/comfort level, the
trip styles and interests they consistently show, hard constraints (dietary,
accessibility), strong dislikes, notable past-trip patterns, and the destinations
they have been planning or have shown interest in (from ``planned_trips``).

Rules:
- Treat the user's own "about_me" text as the HIGHEST authority. If structured fields
  conflict with about_me, prefer about_me.
- Only state what the data supports. Do NOT guess ages, names, or preferences that
  aren't present. Omit empty/unknown fields silently.
- Write in third person ("Travels with...", "Prefers..."). Warm but compact.
- Do NOT include one-off, trip-specific exceptions — only durable traits.
- If there is essentially nothing to summarize, return an empty string.

Output: plain text only (no markdown, no JSON, no quotes)."""


def _planned_trips() -> list[dict[str, Any]]:
    """Compact list of the user's saved/planned trips (destination + dates +
    status). These are a durable signal even when the user never stated explicit
    preferences — planning trips to places is itself meaningful.
    """
    try:
        from tripplanner.tools import trip_planner

        trips = trip_planner.list_saved_trips()
    except Exception:  # pragma: no cover - storage failure
        return []
    out: list[dict[str, Any]] = []
    for t in trips[:12]:
        dest = (t.get("destination") or "").strip()
        if not dest:
            continue
        out.append(
            {
                "destination": dest,
                "departure_date": t.get("departure_date") or "",
                "return_date": t.get("return_date") or "",
                "status": t.get("status") or "draft",
            }
        )
    return out


def _durable_digest(prefs: dict[str, Any]) -> str:
    """Stable hash of the durable signals the summary is built from."""
    snapshot = {k: prefs.get(k) for k in _DIGEST_KEYS}
    snapshot["__planned__"] = _planned_trips()
    blob = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _has_signal(prefs: dict[str, Any]) -> bool:
    """True when there is at least some durable substance worth summarizing."""
    if (prefs.get("about_me") or "").strip():
        return True
    profile = prefs.get("profile") or {}
    if any((profile.get(k) or "") for k in ("display_name", "home_city", "home_country")):
        return True
    for key in ("interests", "dislikes", "family_members", "learned_notes", "past_trips"):
        if prefs.get(key):
            return True
    if _planned_trips():
        return True
    return False


def regenerate(prefs: dict[str, Any]) -> str:
    """Call the LLM to synthesize the summary from ``prefs``.

    Returns the summary text, or ``""`` on any error (missing config, network
    failure) or when there's nothing durable to summarize.
    """
    if not _has_signal(prefs):
        return ""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import AzureChatOpenAI

        from tripplanner.config import get_settings
    except Exception as exc:  # pragma: no cover - import errors are environmental
        log.warning("profile_summary: imports failed (%s); skipping", exc)
        return ""

    payload = {k: prefs.get(k) for k in _DIGEST_KEYS if prefs.get(k)}
    planned = _planned_trips()
    if planned:
        payload["planned_trips"] = planned
    try:
        s = get_settings()
        llm = AzureChatOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            azure_deployment=s.azure_openai_deployment,
            api_version=s.azure_openai_api_version,
            temperature=0.0,
        )
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
    except Exception as exc:
        log.warning("profile_summary: LLM call failed (%s); skipping", exc)
        return ""

    content = getattr(response, "content", "")
    if not isinstance(content, str):
        content = str(content)
    return content.strip()


def update_summary(force: bool = False) -> str:
    """Refresh the stored ``profile_summary`` if durable facts changed.

    Loads prefs, compares the durable digest against the one the last summary was
    built from, and only invokes the LLM when they differ (or ``force=True``).
    Persists ``profile_summary`` + ``profile_summary_updated_at`` +
    ``profile_summary_digest`` on success. Best-effort: never raises. Returns the
    current summary (possibly unchanged).
    """
    try:
        prefs = user_preferences.load_preferences()
    except Exception:  # pragma: no cover - storage failure
        return ""

    digest = _durable_digest(prefs)
    current = prefs.get("profile_summary") or ""
    summary_state = (
        current,
        prefs.get("profile_summary_updated_at"),
        prefs.get("profile_summary_digest") or "",
    )
    if not force and digest == (prefs.get("profile_summary_digest") or ""):
        return current

    summary = regenerate(prefs)
    if not summary:
        # Still record the digest so we don't retry the LLM every turn when there
        # is genuinely nothing to summarize.
        try:
            def store_empty_digest(latest: dict[str, Any]) -> dict[str, Any] | None:
                if _durable_digest(latest) != digest:
                    return None
                latest["profile_summary_digest"] = digest
                return latest

            stored = user_preferences.mutate_preferences(store_empty_digest)
        except Exception:  # pragma: no cover
            return current
        return stored.get("profile_summary") or current

    try:
        updated_at = datetime.now().isoformat()
        stored_summary = False

        def store_summary(latest: dict[str, Any]) -> dict[str, Any] | None:
            nonlocal stored_summary
            stored_summary = False
            latest_summary_state = (
                latest.get("profile_summary") or "",
                latest.get("profile_summary_updated_at"),
                latest.get("profile_summary_digest") or "",
            )
            if _durable_digest(latest) != digest or latest_summary_state != summary_state:
                return None
            latest["profile_summary"] = summary
            latest["profile_summary_updated_at"] = updated_at
            latest["profile_summary_digest"] = digest
            stored_summary = True
            return latest

        stored = user_preferences.mutate_preferences(store_summary)
    except Exception:  # pragma: no cover - storage failure
        return current
    return summary if stored_summary else (stored.get("profile_summary") or current)


def apply_summary(prefs: dict[str, Any], text: str) -> None:
    text = (text or "").strip()
    prefs["profile_summary"] = text
    prefs["profile_summary_updated_at"] = datetime.now().isoformat() if text else None
    prefs["profile_summary_digest"] = _durable_digest(prefs)


def set_summary(
    text: str,
    *,
    expected_updated_at: str | None | object = _ANY_UPDATED_AT,
) -> dict[str, Any]:
    """Persist a user-corrected (or reset) summary verbatim.

    Stamps the current durable digest so an immediate background sweep won't
    overwrite the user's edit. Returns the updated fields.
    """
    applied = False

    def apply(prefs: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal applied
        if (
            expected_updated_at is not _ANY_UPDATED_AT
            and prefs.get("profile_summary_updated_at") != expected_updated_at
        ):
            return None
        applied = True
        apply_summary(prefs, text)
        return prefs

    prefs = user_preferences.mutate_preferences(apply)
    return {
        "applied": applied,
        "profile_summary": prefs["profile_summary"],
        "profile_summary_updated_at": prefs["profile_summary_updated_at"],
    }
