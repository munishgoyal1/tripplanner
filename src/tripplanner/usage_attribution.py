"""Content-free attribution propagated across provider and model calls."""

from __future__ import annotations

import contextvars
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Literal

Initiator = Literal[
    "user_trip",
    "user_action",
    "audit",
    "agent_background",
    "automation",
    "unattributed",
]


@dataclass(frozen=True)
class UsageAttribution:
    initiator: Initiator = "unattributed"
    interaction_id: str = ""
    trip_id: str = ""
    route: str = ""
    environment: str = ""

    def fields(self) -> dict[str, str]:
        values = asdict(self)
        values["environment"] = values["environment"] or os.getenv(
            "TRIPPLANNER_ENVIRONMENT", "local"
        )
        return {key: str(value) for key, value in values.items() if value}


_CONTEXT: contextvars.ContextVar[UsageAttribution | None] = contextvars.ContextVar(
    "tripplanner_usage_attribution", default=None
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


@contextmanager
def usage_scope(
    initiator: Initiator,
    *,
    interaction_id: str = "",
    trip_id: str = "",
    route: str = "",
    environment: str = "",
) -> Iterator[UsageAttribution]:
    attribution = UsageAttribution(
        initiator=initiator,
        interaction_id=interaction_id or uuid.uuid4().hex,
        trip_id=trip_id,
        route=route,
        environment=environment,
    )
    token = _CONTEXT.set(attribution)
    try:
        yield attribution
    finally:
        _CONTEXT.reset(token)
