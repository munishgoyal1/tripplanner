"""Content-free attribution propagated across provider and model calls."""

from __future__ import annotations

import contextvars
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Initiator = Literal[
    "user_trip",
    "user_action",
    "audit",
    "agent_background",
    "automation",
    "unattributed",
]
InteractionKind = Literal["new_trip", "trip_update", "other"]


@dataclass(frozen=True)
class UsageAttribution:
    initiator: Initiator = "unattributed"
    interaction_id: str = ""
    trip_id: str = ""
    route: str = ""
    environment: str = ""
    interaction_kind: InteractionKind = "other"

    def fields(self) -> dict[str, str]:
        values = asdict(self)
        values["environment"] = values["environment"] or os.getenv(
            "TRIPPLANNER_ENVIRONMENT", "local"
        )
        return {key: str(value) for key, value in values.items() if value}


_CONTEXT: contextvars.ContextVar[UsageAttribution | None] = contextvars.ContextVar(
    "tripplanner_usage_attribution", default=None
)


@dataclass
class UsageBatch:
    records: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, record: dict[str, Any]) -> None:
        with self.lock:
            self.records.append(record)

    def annotate_trip(self, interaction_id: str, trip_id: str) -> None:
        if not interaction_id or not trip_id:
            return
        with self.lock:
            for record in self.records:
                if record.get("interaction_id") == interaction_id:
                    record["trip_id"] = trip_id


_BATCH: contextvars.ContextVar[UsageBatch | None] = contextvars.ContextVar(
    "tripplanner_usage_batch", default=None
)


def current_attribution() -> UsageAttribution:
    from tripplanner.validation.harness.context import current_context

    harness = current_context()
    if harness is not None:
        return UsageAttribution(
            initiator="audit",
            interaction_id=harness.run_id,
            route=harness.action_id,
            environment=harness.environment,
        )
    return _CONTEXT.get() or UsageAttribution()


def current_batch() -> UsageBatch | None:
    return _BATCH.get()


def annotate_current_batch(*, interaction_id: str, trip_id: str) -> None:
    batch = current_batch()
    if batch is not None:
        batch.annotate_trip(interaction_id, trip_id)


@contextmanager
def usage_scope(
    initiator: Initiator,
    *,
    interaction_id: str = "",
    trip_id: str = "",
    route: str = "",
    environment: str = "",
    interaction_kind: InteractionKind = "other",
) -> Iterator[UsageAttribution]:
    attribution = UsageAttribution(
        initiator=initiator,
        interaction_id=interaction_id or uuid.uuid4().hex,
        trip_id=trip_id,
        route=route,
        environment=environment,
        interaction_kind=interaction_kind,
    )
    batch = current_batch()
    owns_batch = batch is None
    if batch is None:
        batch = UsageBatch()
    batch_token = _BATCH.set(batch) if owns_batch else None
    token = _CONTEXT.set(attribution)
    try:
        yield attribution
    finally:
        _CONTEXT.reset(token)
        if owns_batch:
            _BATCH.reset(batch_token)
            from tripplanner.provider_usage import persist_batch

            persist_batch(batch.records)
