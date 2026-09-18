"""Serializable event evidence shared by collectors and evaluators."""

from __future__ import annotations

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
