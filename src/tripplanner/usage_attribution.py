"""Content-free attribution propagated across provider and model calls."""

from __future__ import annotations

import contextvars
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
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

_TRACE_EVENT_FIELDS = frozenset(
    {
        "attempted",
        "billable",
        "cache",
        "cache_hit",
        "cache_scope",
        "cached_tokens",
        "completion_tokens",
        "container",
        "dataset",
        "endpoint",
        "environment",
        "error",
        "estimated_cost_usd",
        "event_kind",
        "http_status",
        "initiator",
        "interaction_id",
        "interaction_kind",
        "message_count",
        "model",
        "ms",
        "operation",
        "outcome",
        "prompt_chars",
        "prompt_tokens",
        "provider",
        "result",
        "route",
        "sku_class",
        "stage",
        "status",
        "store",
        "tool",
        "trip_id",
        "units",
    }
)


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
    events: list[dict[str, Any]] = field(default_factory=list)
    attribution: UsageAttribution | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, record: dict[str, Any]) -> None:
        with self.lock:
            self.records.append(record)

    def append_event(self, kind: str, fields: dict[str, Any]) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key in _TRACE_EVENT_FIELDS
            and (value is None or isinstance(value, (bool, float, int, str)))
        }
        with self.lock:
            self.events.append(
                {
                    "sequence": len(self.events) + 1,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "kind": kind,
                    **safe_fields,
                }
            )

    def promote_attribution(self, attribution: UsageAttribution) -> None:
        fields = attribution.fields()
        with self.lock:
            self.attribution = attribution
            for item in [*self.records, *self.events]:
                for key in ("initiator", "interaction_id", "interaction_kind", "trip_id"):
                    if fields.get(key):
                        item[key] = fields[key]

    def annotate_trip(self, interaction_id: str, trip_id: str) -> None:
        if not interaction_id or not trip_id:
            return
        with self.lock:
            if self.attribution is not None:
                self.attribution = replace(
                    self.attribution,
                    interaction_id=interaction_id,
                    trip_id=trip_id,
                )
            for record in self.records:
                if record.get("interaction_id") == interaction_id:
                    record["trip_id"] = trip_id
            for event in self.events:
                if event.get("interaction_id") == interaction_id:
                    event["trip_id"] = trip_id


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


def append_current_event(kind: str, fields: dict[str, Any]) -> None:
    batch = current_batch()
    if batch is None:
        return
    batch.append_event(kind, {**current_attribution().fields(), **fields})


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
    if batch.attribution is None:
        batch.attribution = attribution
    elif attribution.initiator == "user_trip":
        batch.promote_attribution(attribution)
    batch_token = _BATCH.set(batch) if owns_batch else None
    token = _CONTEXT.set(attribution)
    try:
        yield attribution
    finally:
        _CONTEXT.reset(token)
        if owns_batch:
            _BATCH.reset(batch_token)
            from tripplanner.interaction_telemetry import persist_interaction
            from tripplanner.provider_usage import persist_batch

            persist_batch(batch.records, batch.events)
            final_attribution = batch.attribution or attribution
            persist_interaction(final_attribution.fields(), batch.events, batch.records)
