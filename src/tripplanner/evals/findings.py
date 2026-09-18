"""Findings, grouped by shape rather than by instance.

Four hundred lines of "Day 3 is far from Day 2" is the same report as one line
with a count of four hundred, except that nobody reads the first one. A finding
is therefore identified by the *shape* of what went wrong, with the specific
trip kept only as an exemplar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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
