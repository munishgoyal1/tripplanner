"""Shared run correlation; independent of scenario execution and evaluation."""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RunContext:
    run_id: str
    scenario_id: str
    action_id: str = ""
    environment: str = "local"

    def event_fields(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value}


_CONTEXT: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar(
    "tripplanner_harness_context", default=None
)


def current_context() -> RunContext | None:
    return _CONTEXT.get()


@contextmanager
def run_scope(
    scenario_id: str,
    *,
    run_id: str | None = None,
    action_id: str = "",
    environment: str = "local",
) -> Iterator[RunContext]:
    context = RunContext(
        run_id=run_id or str(uuid.uuid4()),
        scenario_id=scenario_id,
        action_id=action_id,
        environment=environment,
    )
    token = _CONTEXT.set(context)
    try:
        yield context
    finally:
        _CONTEXT.reset(token)
