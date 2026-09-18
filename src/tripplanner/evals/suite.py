"""Available offline evaluator families and their input/coverage requirements."""

from __future__ import annotations

from typing import Any

from tripplanner.evals.contracts import CorpusRecord
from tripplanner.evals.findings import Finding

EVALUATORS = ("plan", "human", "render", "metamorphic")


def has_place_coverage(record: CorpusRecord) -> bool:
    from tripplanner.evals.deterministic.render import _lookup

    if not record.places:
        return False
    lookup = _lookup(record.places)
    for day in record.plan.get("day_wise_itinerary") or []:
        for stop in day.get("stops") or []:
            name = stop.get("name", "") if isinstance(stop, dict) else str(stop)
            city = (stop.get("city") if isinstance(stop, dict) else "") or day.get("city")
            facts = lookup(name, city or record.destination) or {}
            if facts.get("lat") is None or facts.get("lng") is None:
                return False
    return True


def rating_for(record: CorpusRecord, ratings: dict[str, Any]) -> dict[str, Any]:
    from tripplanner.evals.human import _entry_for

    return _entry_for(record, ratings)


def evaluate(
    evaluator: str,
    record: CorpusRecord,
    ratings: dict[str, Any],
) -> tuple[str, list[Finding], str]:
    from tripplanner.evals.deterministic.checks import check_record
    from tripplanner.evals.deterministic.mutations import check_metamorphic
    from tripplanner.evals.deterministic.render import check_render
    from tripplanner.evals.human import HARD_GATES, _outcome, gate_findings

    if evaluator == "human":
        entry = rating_for(record, ratings)
        findings = gate_findings(record, ratings)
        complete = all(_outcome(entry, gate.key) for gate in HARD_GATES)
        reason = "" if complete else "Human gate ratings are incomplete"
    elif evaluator in {"plan", "render", "metamorphic"}:
        functions = {"plan": check_record, "render": check_render, "metamorphic": check_metamorphic}
        findings = functions[evaluator](record)
        complete = has_place_coverage(record)
        reason = (
            "" if complete else "Stored place facts are missing or incomplete for itinerary stops"
        )
        if evaluator == "render" and any(item.rule == "R0" for item in findings):
            return "error", findings, "Rendering failed; result is not reusable"
    else:
        raise ValueError(f"Unknown evaluator {evaluator}")
    status = ("fail" if findings else "pass") if complete else "insufficient_evidence"
    return status, findings, reason
