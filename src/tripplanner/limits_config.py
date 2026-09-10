"""Single place for every request-throttling and usage-budget limit.

Two mechanically distinct systems live here, each its own section below:

1. Time-window throttling (``request_limits.py``, ``conversation_limits.py``,
   ``usage.py``) — sliding per-minute/concurrency admission plus durable
   daily/weekly/lifetime/monthly-cost ceilings. This is the anti-abuse,
   anti-viral-spike lever: it bounds how many requests the app serves *per
   time window*, independent of what any one request does. Breaching it
   returns HTTP 429 (or a soft in-chat refusal for the monthly cost cap).

2. Per-turn / per-trip tool-call & paid-API-call budgets (``config.py``
   ``Settings``, enforced in ``graph_policy.py``, ``transport_compare.py``,
   ``places_budget.py``) — bounded counters scoped to one conversation turn
   or one trip, e.g. "at most 3 Google Places text searches per trip".
   Breaching one doesn't reject the request; the agent stops calling tools
   and summarizes with whatever it already has.

All accessors re-read ``os.environ`` on every call (not cached at import),
matching the pre-existing behavior of both source modules this consolidates
— tests rely on ``monkeypatch.setenv`` taking effect mid-test.
"""

from __future__ import annotations

import os


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# --- Time-window throttling: sliding per-minute + concurrency admission ---
# (request_limits.py — in-process, per-server-instance, resets on restart)


def chat_user_requests_per_minute() -> int:
    return _positive_int("CHAT_USER_REQUESTS_PER_MINUTE", 10)


def chat_ip_requests_per_minute() -> int:
    return _positive_int("CHAT_IP_REQUESTS_PER_MINUTE", 30)


def chat_max_concurrent_per_user() -> int:
    return _positive_int("CHAT_MAX_CONCURRENT_PER_USER", 1)


def chat_max_concurrent_global() -> int:
    return _positive_int("CHAT_MAX_CONCURRENT_GLOBAL", 4)


def chat_replay_lookups_per_minute() -> int:
    return _positive_int("CHAT_REPLAY_LOOKUPS_PER_MINUTE", 60)


def chat_replay_lookups_per_ip_per_minute() -> int:
    return _positive_int("CHAT_REPLAY_LOOKUPS_PER_IP_PER_MINUTE", 180)


# --- Durable daily/weekly/lifetime conversation ceilings ---
# (conversation_limits.py — Cosmos- or local-file-backed, survives restarts)

_CONVERSATION_LIMIT_ENV_NAMES = {
    ("new_trip", "daily"): "CHAT_NEW_TRIP_LIMIT_DAILY",
    ("existing_trip_turn", "daily"): "CHAT_EXISTING_TRIP_TURN_LIMIT_DAILY",
    ("new_trip", "weekly"): "CHAT_NEW_TRIP_LIMIT_WEEKLY",
    ("existing_trip_turn", "weekly"): "CHAT_EXISTING_TRIP_TURN_LIMIT_WEEKLY",
    ("new_trip", "lifetime"): "CHAT_NEW_TRIP_LIMIT_LIFETIME",
    ("existing_trip_turn", "lifetime"): "CHAT_EXISTING_TRIP_TURN_LIMIT_LIFETIME",
}


def conversation_limit(category: str, window: str) -> int:
    """0 disables the ceiling for that (category, window) pair."""
    try:
        return max(0, int(os.getenv(_CONVERSATION_LIMIT_ENV_NAMES[(category, window)], "0")))
    except (TypeError, ValueError):
        return 0


# --- Monthly LLM cost cap ---
# (usage.py — per-user running $ total; <= 0 disables the cap)


def monthly_llm_cost_cap_usd() -> float:
    raw = os.getenv("MONTHLY_LLM_COST_CAP_USD", "20")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 20.0


# --- Per-turn / per-trip tool-call & paid-API-call budgets ---
# (config.py Settings — bounds how many tool-call rounds/searches a single
# chat turn or trip can spend, the other lever that caps paid-provider
# spend per turn/trip, besides the time-window throttling above)


def max_tool_phases_per_turn() -> int:
    return _positive_int("MAX_TOOL_PHASES_PER_TURN", 10)


def max_initial_itinerary_updates() -> int:
    return _positive_int("MAX_INITIAL_ITINERARY_UPDATES", 2)


def max_post_research_updates() -> int:
    return _positive_int("MAX_POST_RESEARCH_UPDATES", 1)


def max_transport_comparisons_per_turn() -> int:
    return _positive_int("MAX_TRANSPORT_COMPARISONS_PER_TURN", 3)


def max_transport_comparisons_per_trip() -> int:
    return _positive_int("MAX_TRANSPORT_COMPARISONS_PER_TRIP", 6)


def google_places_max_text_searches_per_trip() -> int:
    return _positive_int("GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_TRIP", 3)


def google_places_max_review_details_per_trip() -> int:
    return _positive_int("GOOGLE_PLACES_MAX_REVIEW_DETAILS_PER_TRIP", 1)


def google_places_max_photos_per_trip() -> int:
    return _positive_int("GOOGLE_PLACES_MAX_PHOTOS_PER_TRIP", 3)


def google_places_max_photos_per_place() -> int:
    return _positive_int("GOOGLE_PLACES_MAX_PHOTOS_PER_PLACE", 1)
