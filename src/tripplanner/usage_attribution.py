"""Content-free attribution propagated across provider and model calls."""

from __future__ import annotations

import contextvars
import os
import threading
import time
import uuid
from collections import Counter
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
        "service",
        "sku_class",
        "stage",
        "status",
        "store",
        "tool",
        "trip_id",
        "units",
        "purpose",
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


def _is_failure(fields: dict[str, Any]) -> bool:
    status = str(fields.get("status") or fields.get("outcome") or "").lower()
    return bool(fields.get("error")) or status in {"error", "failed", "failure"}


def _aggregate_event(kind: str, fields: dict[str, Any]) -> bool:
    if _is_failure(fields):
        return False
    if kind == "cache_access":
        return fields.get("result") != "provider_unavailable"
    if kind == "provider_call":
        return not bool(fields.get("attempted", True))
    return kind in {"storage_operation", "outbound_call", "llm_usage"}


@dataclass
class UsageBatch:
    records: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    attribution: UsageAttribution | None = None
    flow_places: dict[str, str] = field(default_factory=dict)
    total_event_count: int = 0
    aggregate_event_counts: Counter[str] = field(default_factory=Counter)
    cache_results: Counter[str] = field(default_factory=Counter)
    cache_record_indexes: dict[tuple[str, ...], int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, record: dict[str, Any]) -> None:
        with self.lock:
            if record.get("event_type") == "cache_hit":
                key = tuple(
                    str(record.get(field) or "")
                    for field in ("provider", "operation", "sku_class", "dataset")
                )
                existing_index = self.cache_record_indexes.get(key)
                if existing_index is not None:
                    existing = self.records[existing_index]
                    existing["units"] = int(existing.get("units") or 1) + int(
                        record.get("units") or 1
                    )
                    existing["estimated_savings_usd"] = round(
                        float(existing.get("estimated_savings_usd") or 0)
                        + float(record.get("estimated_savings_usd") or 0),
                        8,
                    )
                    return
                self.cache_record_indexes[key] = len(self.records)
            self.records.append(record)

    def append_event(self, kind: str, fields: dict[str, Any]) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key in _TRACE_EVENT_FIELDS
            and (value is None or isinstance(value, (bool, float, int, str)))
        }
        with self.lock:
            self.total_event_count += 1
            if (
                str(fields.get("environment") or "").lower() == "local"
                and fields.get("place")
                and kind == "cache_access"
            ):
                label = str(fields["place"])
                if fields.get("city"):
                    label += f" ({fields['city']})"
                decision = str(fields.get("result") or fields.get("status") or kind)
                self.flow_places[label] = decision
            if _aggregate_event(kind, fields):
                self.aggregate_event_counts[kind] += 1
                if kind == "cache_access":
                    result = str(fields.get("result") or "unknown")
                    self.cache_results[result] += max(1, int(fields.get("units") or 1))
                return
            self.events.append(
                {
                    "sequence": self.total_event_count,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "kind": kind,
                    **safe_fields,
                }
            )

    def flow_summary(self) -> dict[str, Any]:
        with self.lock:
            events = list(self.events)
            records = list(self.records)
            places = list(self.flow_places.items())
            event_count = self.total_event_count
            aggregate_counts = self.aggregate_event_counts.copy()
            cache_results = self.cache_results.copy()
        hit_results = sum(
            count for result, count in cache_results.items() if result.endswith("hit")
        )
        miss_results = sum(
            count
            for result, count in cache_results.items()
            if result == "miss" or result.endswith("_miss") or result == "refresh"
        )
        return {
            "event_count": event_count,
            "llm_calls": sum(1 for event in events if event.get("kind") == "llm_call"),
            "tool_calls": sum(1 for event in events if event.get("kind") == "tool_call"),
            "provider_calls": sum(
                int(record.get("units") or 1)
                for record in records
                if record.get("attempted", True)
            ),
            "cache_hits": hit_results,
            "cache_misses": miss_results,
            "storage_operations": sum(
                1 for event in events if event.get("kind") == "storage_operation"
            )
            + aggregate_counts["storage_operation"],
            "aggregated_event_count": sum(aggregate_counts.values()),
            "outbound_calls": aggregate_counts["outbound_call"],
            "llm_usage_events": aggregate_counts["llm_usage"],
            "cache_served_provider_calls": aggregate_counts["provider_call"],
            "places": [f"{label}={decision}" for label, decision in places[:5]],
            "place_count": len(places),
        }

    def append_aggregate_summary(self, summary: dict[str, Any]) -> None:
        if not summary.get("aggregated_event_count"):
            return
        attribution = (self.attribution or UsageAttribution()).fields()
        with self.lock:
            self.events.append(
                {
                    "sequence": self.total_event_count + 1,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "kind": "telemetry_summary",
                    **attribution,
                    **{
                        key: summary[key]
                        for key in (
                            "aggregated_event_count",
                            "cache_hits",
                            "cache_misses",
                            "storage_operations",
                            "outbound_calls",
                            "llm_usage_events",
                            "cache_served_provider_calls",
                        )
                    },
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
    started_at = time.monotonic()
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
    from tripplanner.flight_recorder import TRACE, record

    trace_token = TRACE.set(TRACE.get() or attribution.interaction_id)
    record("interaction.start", **attribution.fields())
    try:
        yield attribution
    finally:
        record("interaction.end", **(batch.attribution or attribution).fields())
        if owns_batch:
            try:
                from tripplanner.observability import log_flow_summary

                summary = batch.flow_summary()
                log_flow_summary(
                    (batch.attribution or attribution).fields(),
                    summary,
                    (time.monotonic() - started_at) * 1000,
                )
                batch.append_aggregate_summary(summary)
            except Exception:
                pass
        _CONTEXT.reset(token)
        TRACE.reset(trace_token)
        if owns_batch:
            _BATCH.reset(batch_token)
            from tripplanner.interaction_telemetry import persist_interaction
            from tripplanner.provider_usage import persist_batch

            persist_batch(batch.records, batch.events)
            final_attribution = batch.attribution or attribution
            persist_interaction(final_attribution.fields(), batch.events, batch.records)

            # Reconcile this interaction's INR reservation against what it
            # actually cost, and fold the same records into the trip's cost
            # document. Runs after persist_batch so the ledger and the raw
            # provider_usage rows can never disagree about what was recorded.
            # The reservation is keyed by interaction_id, so nothing has to be
            # threaded from the admission point down to here.
            from tripplanner import cost_ledger

            cost_ledger.settle(final_attribution.fields(), batch.records)
