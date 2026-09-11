"""Authorization scope for paid Google Places requests.

This is an **authorization** boundary, not a budget. A paid Places call is only
permitted while execution is inside a named ``user_interaction`` or
``corpus_generation`` scope, which reusable view builders, audits, tests,
issue-fix validation and background warming cannot create. That gate is what
stopped the 2026-08-27 incident pattern (unbounded cold-cache enrichment across
concurrent sandbox lanes, each with an isolated cache) from recurring, and it
stays.

What this module no longer does is *cap* how many calls an authorized scope may
make. Per-scope counters (three text searches, one review-details, three photos)
were a proxy for money that throttled quality on legitimately complex trips --
a multi-city itinerary genuinely needs more lookups than a weekend break. Spend
is now bounded by the measured INR ceiling in ``cost_ledger.py``, and per-trip
call counts are recorded there so an unoptimized flow shows up as a dashboard
anomaly instead of as a silently truncated itinerary.

Counts are still tracked per scope, purely as telemetry.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

RequestKind = Literal["text_search", "review_details", "photo"]
PaidProviderPurpose = Literal["user_interaction", "corpus_generation"]


@dataclass
class PlacesBudget:
    purpose: PaidProviderPurpose
    used: dict[RequestKind, int] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def consume(self, kind: RequestKind) -> bool:
        """Record one authorized paid call. Always permits -- the scope's
        existence is the permission; the count is observational."""
        with self.lock:
            self.used[kind] = self.used.get(kind, 0) + 1
            return True


_BUDGET: contextvars.ContextVar[PlacesBudget | None] = contextvars.ContextVar(
    "google_places_budget", default=None
)


@contextmanager
def places_budget_scope(purpose: PaidProviderPurpose) -> Iterator[PlacesBudget]:
    active = _BUDGET.get()
    if active is not None:
        yield active
        return
    budget = PlacesBudget(purpose=purpose)
    token = _BUDGET.set(budget)
    try:
        yield budget
    finally:
        _BUDGET.reset(token)


def current_budget() -> PlacesBudget | None:
    return _BUDGET.get()


def paid_provider_authorized() -> bool:
    return _BUDGET.get() is not None


@contextmanager
def use_budget(budget: PlacesBudget | None) -> Iterator[None]:
    if budget is None:
        yield
        return
    token = _BUDGET.set(budget)
    try:
        yield
    finally:
        _BUDGET.reset(token)


def consume(kind: RequestKind) -> bool:
    """``True`` when a paid call of ``kind`` is authorized here, else ``False``."""
    budget = _BUDGET.get()
    return budget is not None and budget.consume(kind)
