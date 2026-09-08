"""Findings, grouped by shape rather than by instance.

Four hundred lines of "Day 3 is far from Day 2" is the same report as one line
with a count of four hundred, except that nobody reads the first one. A finding
is therefore identified by the *shape* of what went wrong, with the specific
trip kept only as an exemplar.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BASELINE_VERSION = 1


@dataclass(frozen=True)
class Finding:
    rule: str
    symptom: str
    message: str
    record_id: str
    provenance: str
    day: int | None = None

    @property
    def key(self) -> str:
        return f"{self.rule}|{self.symptom}"


@dataclass
class Group:
    rule: str
    symptom: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.rule}|{self.symptom}"

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def exemplar(self) -> Finding:
        return self.findings[0]

    @property
    def provenances(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for finding in self.findings:
            tally[finding.provenance] = tally.get(finding.provenance, 0) + 1
        return tally


def symptom_of(message: str, names: list[str] | None = None) -> str:
    """The shape of a message, with the specific trip taken out of it."""
    text = str(message or "")
    for name in sorted({n for n in (names or []) if n and len(n) > 2}, key=len, reverse=True):
        text = text.replace(name, "<place>")
    text = re.sub(r"\d+", "N", text)
    return re.sub(r"\s+", " ", text).strip()


def group(findings: list[Finding]) -> list[Group]:
    grouped: dict[str, Group] = {}
    for finding in findings:
        bucket = grouped.get(finding.key)
        if bucket is None:
            bucket = Group(rule=finding.rule, symptom=finding.symptom)
            grouped[finding.key] = bucket
        bucket.findings.append(finding)
    return sorted(grouped.values(), key=lambda item: (-item.count, item.key))


# --------------------------------------------------------------------------- #
# baseline                                                                      #
# --------------------------------------------------------------------------- #


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": BASELINE_VERSION, "accepted": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": BASELINE_VERSION, "accepted": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("accepted"), dict):
        return {"version": BASELINE_VERSION, "accepted": {}}
    return payload


def new_groups(groups: list[Group], baseline: dict[str, Any]) -> list[Group]:
    accepted = baseline.get("accepted") or {}
    return [item for item in groups if item.key not in accepted]


def stale_keys(groups: list[Group], baseline: dict[str, Any]) -> list[str]:
    """Accepted findings that no longer occur, so the baseline can shrink."""
    live = {item.key for item in groups}
    return sorted(key for key in (baseline.get("accepted") or {}) if key not in live)


def accept(groups: list[Group], baseline: dict[str, Any]) -> dict[str, Any]:
    """Record every current finding as known, preserving earlier acceptances."""
    accepted = dict(baseline.get("accepted") or {})
    today = datetime.now(UTC).date().isoformat()
    for item in groups:
        existing = accepted.get(item.key) or {}
        accepted[item.key] = {
            "rule": item.rule,
            "symptom": item.symptom,
            "accepted_on": existing.get("accepted_on") or today,
            "count_when_accepted": existing.get("count_when_accepted") or item.count,
            "example": existing.get("example") or item.exemplar.message,
        }
    return {"version": BASELINE_VERSION, "accepted": accepted}


def save_baseline(path: Path, baseline: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        "version": BASELINE_VERSION,
        "accepted": dict(sorted((baseline.get("accepted") or {}).items())),
    }
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
