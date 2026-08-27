"""Structured evidence captured while a harness scenario runs."""

from __future__ import annotations

import threading
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class HarnessEvent:
    kind: str
    fields: dict[str, Any]


@dataclass
class HarnessEvidence:
    run_id: str
    scenario_id: str
    environment: str
    events: list[HarnessEvent] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "environment": self.environment,
            "events": [asdict(event) for event in self.events],
        }


class EvidenceCollector(AbstractContextManager["EvidenceCollector"]):
    """Collect app events emitted by the current harness run."""

    def __init__(self, run_id: str, scenario_id: str, environment: str = "local") -> None:
        self.evidence = HarnessEvidence(run_id, scenario_id, environment)
        self._lock = threading.Lock()

    def record(self, kind: str, fields: dict[str, Any]) -> None:
        if fields.get("run_id") != self.evidence.run_id:
            return
        with self._lock:
            self.evidence.events.append(HarnessEvent(kind, dict(fields)))

    def __enter__(self) -> EvidenceCollector:
        from tripplanner.observability import add_event_observer

        add_event_observer(self.record)
        return self

    def __exit__(self, *_args: object) -> None:
        from tripplanner.observability import remove_event_observer

        remove_event_observer(self.record)
