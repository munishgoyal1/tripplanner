"""Turn-scoped ceilings for paid Google Places requests."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from tripplanner.config import get_settings

RequestKind = Literal["text_search", "review_details", "photo"]
PaidProviderPurpose = Literal["user_interaction", "corpus_generation"]


@dataclass
class PlacesBudget:
    purpose: PaidProviderPurpose
    limits: dict[RequestKind, int]
    used: dict[RequestKind, int] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def consume(self, kind: RequestKind) -> bool:
        with self.lock:
            used = self.used.get(kind, 0)
            if used >= self.limits[kind]:
                return False
            self.used[kind] = used + 1
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
    settings = get_settings()
    budget = PlacesBudget(
        purpose=purpose,
        limits={
            "text_search": settings.google_places_max_text_searches_per_trip,
            "review_details": settings.google_places_max_review_details_per_trip,
            "photo": settings.google_places_max_photos_per_trip,
        }
    )
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
    budget = _BUDGET.get()
    return budget is not None and budget.consume(kind)
