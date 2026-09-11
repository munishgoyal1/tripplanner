"""Single place for every runtime limit this application enforces.

There is exactly **one** cost control: a daily/weekly/monthly ceiling denominated
in **INR**, covering Azure OpenAI and Google Cloud together, enforced by
``cost_ledger.py`` against measured per-call spend. Everything else in this file
is either anti-abuse admission (bounding request *rate*, not spend) or a
liveness guard living in code rather than config.

What this file deliberately does NOT contain, and why:

- Per-trip / per-turn tool-call budgets. The agent may make whatever calls a
  quality itinerary needs; ``cost_ledger.py`` measures what that actually costs
  and the INR ceiling stops the environment when the money runs out. Runaway
  flows surface as anomalies in the operations dashboard rather than as silent
  truncation mid-itinerary. Liveness guards that merely stop infinite loops
  (``graph_policy._MAX_TOOL_PHASES_PER_TURN`` and friends) are code constants,
  not operator-tunable config.
- Durable conversation counters (new-trip/turn ceilings per day/week/lifetime).
  Counting trips was a proxy for counting money that mispriced trips by ~4x
  either way. The ledger counts money directly; an unpriceable call is charged
  the rolling P95 rather than zero, which is what protects against the cost
  estimator itself breaking.

UNIT DISCIPLINE: every ceiling here is INR and every accessor says so in its
name. USD appears only in provider pricing catalogs and crosses into INR exactly
once, in ``cost_model.usd_to_inr``. Confusing the two would multiply a ceiling by
~88 and open the budget far beyond what the owner set.

PARSE DISCIPLINE: one convention, unlike the two contradictory ones this file
previously carried. A missing, empty, or malformed value falls back to the
documented default below -- never to zero, and never to "disabled". A cost
ceiling that fails open on a deployment typo is not a cost ceiling. Only
``0`` written *deliberately* disables a limit, and only where noted.
"""

from __future__ import annotations

import os

# --- Parse helpers -----------------------------------------------------------


def _int_setting(name: str, default: int) -> int:
    """Positive integer from env, falling back to ``default`` on anything odd.

    Empty string, whitespace, non-numeric text, and values below 1 all yield
    ``default``. ``os.environ`` is re-read on every call (never cached at import)
    so a deployed process picks up a value and tests can monkeypatch mid-test --
    the bug that previously froze five budgets at import time.
    """
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 1 else default


def _inr_setting(name: str, default: float) -> float:
    """Positive INR amount from env, falling back to ``default`` on anything odd.

    ``<= 0`` is rejected rather than treated as "unlimited": an operator who
    wants no ceiling must say so through ``COST_CEILING_ENFORCED=0``, which is
    auditable, instead of by blanking a number.
    """
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _flag_setting(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


# --- The uber control: INR spend ceilings ------------------------------------
# Enforced by cost_ledger.py across Azure OpenAI + Google Cloud combined,
# environment-wide (not per user). Breach -> HTTP 429 carrying resets_at.
#
# These three windows are deliberately NOT multiples of each other: daily is a
# burst allowance, monthly is the real constraint. At the ~INR 42 average trip
# this model predicts, INR 10,000/month is roughly 13 full testing days, and a
# run of INR 1,000 days will exhaust the month well before day 30.


def cost_ceiling_inr_daily() -> float:
    return _inr_setting("COST_CEILING_INR_DAILY", 1000.0)


def cost_ceiling_inr_weekly() -> float:
    return _inr_setting("COST_CEILING_INR_WEEKLY", 5000.0)


def cost_ceiling_inr_monthly() -> float:
    return _inr_setting("COST_CEILING_INR_MONTHLY", 10000.0)


def cost_ceiling_inr(window: str) -> float:
    """INR ceiling for ``daily`` | ``weekly`` | ``monthly``."""
    if window == "daily":
        return cost_ceiling_inr_daily()
    if window == "weekly":
        return cost_ceiling_inr_weekly()
    if window == "monthly":
        return cost_ceiling_inr_monthly()
    raise ValueError(f"unknown cost ceiling window: {window!r}")


COST_CEILING_WINDOWS: tuple[str, ...] = ("daily", "weekly", "monthly")


def cost_ceiling_enforced() -> bool:
    """``0`` runs the ledger in observe-only mode: it records and reports spend,
    and logs what it *would* have refused, without returning 429."""
    return _flag_setting("COST_CEILING_ENFORCED", True)


def cost_ceiling_deny_on_ledger_error() -> bool:
    """Admission decision when the ledger itself cannot be read or written.

    ``deny`` (default) is correct wherever real money is at stake: an unreadable
    ledger means unknown spend. Local development sets this to ``0`` because the
    sandbox has no route to Cosmos and a storage outage must not brick the
    owner's own testing environment.
    """
    return _flag_setting("COST_CEILING_DENY_ON_LEDGER_ERROR", True)


# --- Anti-abuse admission ----------------------------------------------------
# Bounds how fast requests arrive, NOT how much they cost -- the INR ceiling
# above owns spend. Sized so genuine owner testing and a genuine prod user never
# reach them; they exist for scripted abuse and viral spikes. In-process and
# per-server-instance, so they reset on restart. Breach -> HTTP 429.


def chat_user_requests_per_minute() -> int:
    return _int_setting("CHAT_USER_REQUESTS_PER_MINUTE", 30)


def chat_ip_requests_per_minute() -> int:
    return _int_setting("CHAT_IP_REQUESTS_PER_MINUTE", 90)


def chat_max_concurrent_per_user() -> int:
    return _int_setting("CHAT_MAX_CONCURRENT_PER_USER", 5)


def chat_max_concurrent_global() -> int:
    return _int_setting("CHAT_MAX_CONCURRENT_GLOBAL", 12)


def chat_replay_lookups_per_minute() -> int:
    """Retry-status polls are cheap reads; derived from the chat rate so there is
    one fewer number to keep in sync."""
    return _int_setting("CHAT_REPLAY_LOOKUPS_PER_MINUTE", chat_user_requests_per_minute() * 6)


def chat_replay_lookups_per_ip_per_minute() -> int:
    return _int_setting(
        "CHAT_REPLAY_LOOKUPS_PER_IP_PER_MINUTE", chat_ip_requests_per_minute() * 6
    )


# --- Presentation ------------------------------------------------------------
# Not cost controls: how large a photo gallery one page render builds. Kept
# configurable because they are visual-density choices. Photo media is the
# dominant *paid* Google SKU once text search sits inside its free monthly
# pool, so these do influence spend -- but the ceiling above is what bounds it;
# these bound what a gallery looks like.


def google_places_max_photos_per_place() -> int:
    return _int_setting("GOOGLE_PLACES_MAX_PHOTOS_PER_PLACE", 1)


def google_places_max_photos_per_request() -> int:
    """Photos one view render may sign.

    Named for what it actually scopes. The predecessor was called
    ``..._PER_TRIP`` while resetting on every HTTP request, so a trip viewed
    five times signed five times the documented number. Google's signed photo
    URLs expire in about an hour and are not part of the durable place cache,
    so a re-render genuinely re-signs; ``GOOGLE_PLACES_PHOTO_URL_CACHE_TTL_SEC``
    is what keeps repeat views within that window free.
    """
    return _int_setting("GOOGLE_PLACES_MAX_PHOTOS_PER_REQUEST", 40)
