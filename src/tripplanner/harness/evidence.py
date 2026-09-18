"""Subscribe to runtime events for one correlated harness run."""

from __future__ import annotations

import threading
from contextlib import AbstractContextManager
from typing import Any

from tripplanner.observability.evidence import HarnessEvent as HarnessEvent
from tripplanner.observability.evidence import HarnessEvidence as HarnessEvidence


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
