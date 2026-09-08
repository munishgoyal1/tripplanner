"""Human assessments for fidelity gates and experiential trip quality."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tripplanner.validation.corpus import CorpusRecord
from tripplanner.validation.findings import Finding

RATINGS_FILE = "quality-ratings.json"
RATINGS_VERSION = 1

PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"
HARD_GATE_OUTCOMES = frozenset({PASS, FAIL, NOT_APPLICABLE})


@dataclass(frozen=True)
class QualityDimension:
    key: str
    title: str
    prompt: str


HARD_GATES: tuple[QualityDimension, ...] = (
    QualityDimension(
        "scenario_preference_fidelity",
        "Scenario and preference fidelity",
        "Does the plan honor the scenario's explicit party, pace, interests, food, mobility, "
        "lodging, transport, and other constraints?",
    ),
    QualityDimension(
        "budget_evidence_completeness",
        "Requested budget evidence completeness",
        "When the scenario requests a budget or ceiling, does the comparable total fit it and "
        "does the plan contain enough priced evidence to support that total?",
    ),
)

TASTE_DIMENSIONS: tuple[QualityDimension, ...] = (
    QualityDimension(
        "destination_specificity",
        "Destination specificity and local character",
        "Could these choices and details belong only to this destination rather than a generic "
        "trip?",
    ),
    QualityDimension(
        "memorable_moments",
        "Memorable or signature moments",
        "Does the trip contain distinctive experiences likely to become trip-defining memories?",
    ),
    QualityDimension(
        "narrative_coherence",
        "Narrative and day coherence",
        "Do days have an intelligible theme and progression, and does the whole trip tell a story?",
    ),
    QualityDimension(
        "meal_quality",
        "Meal quality",
        "Are meals concrete, locally relevant, varied, and fitted to the day and traveller?",
    ),
    QualityDimension(
        "intentional_free_time",
        "Intentional free time",
        "Is rest or unstructured time deliberately placed and appropriate to the requested pace?",
    ),
    QualityDimension(
        "repetition",
        "Repetition",
        "Does the trip avoid accidental repetition while allowing a revisit with a clear purpose?",
    ),
)

_HARD_GATE_BY_KEY = {dimension.key: dimension for dimension in HARD_GATES}
_TASTE_BY_KEY = {dimension.key: dimension for dimension in TASTE_DIMENSIONS}


def ratings_path(corpus_root: Path) -> Path:
    return corpus_root / RATINGS_FILE


def load(corpus_root: Path) -> dict[str, Any]:
    """Load ratings conservatively; malformed input cannot silently enable gates."""
    path = ratings_path(corpus_root)
    if not path.exists():
        return empty_ratings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_ratings()
    if not isinstance(payload, dict) or payload.get("version") != RATINGS_VERSION:
        return empty_ratings()
    if not isinstance(payload.get("ratings"), dict):
        return empty_ratings()
    return payload


def empty_ratings() -> dict[str, Any]:
    return {
        "version": RATINGS_VERSION,
        "scale": {"min": 1, "max": 5},
        "reference_cohort_approved": False,
        "ratings": {},
    }


def _assessment(entry: Any, key: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    gates = entry.get("hard_gates")
    assessment = gates.get(key) if isinstance(gates, dict) else None
    return assessment if isinstance(assessment, dict) else {}


def _outcome(entry: Any, key: str) -> str:
    outcome = _assessment(entry, key).get("outcome")
    if outcome == NOT_APPLICABLE and key != "budget_evidence_completeness":
        return ""
    return str(outcome) if outcome in HARD_GATE_OUTCOMES else ""


def _entry_for(record: CorpusRecord, ratings: dict[str, Any]) -> dict[str, Any]:
    entries = ratings.get("ratings")
    if not isinstance(entries, dict):
        return {}
    keys = (record.id, record.logical_trip_id, *(link.id for link in record.links))
    return next(
        (entry for key in keys if isinstance((entry := entries.get(key)), dict)),
        {},
    )


def gate_findings(record: CorpusRecord, ratings: dict[str, Any]) -> list[Finding]:
    """Turn explicit owner-rated gate failures into normal audit findings."""
    entry = _entry_for(record, ratings)
    findings: list[Finding] = []
    for dimension in HARD_GATES:
        assessment = _assessment(entry, dimension.key)
        if _outcome(entry, dimension.key) != FAIL:
            continue
        evidence = str(assessment.get("evidence") or "").strip()
        message = f"{dimension.title} failed"
        if evidence:
            message = f"{message}: {evidence}"
        findings.append(
            Finding(
                rule=f"QG{list(_HARD_GATE_BY_KEY).index(dimension.key) + 1}",
                symptom=dimension.title,
                message=message,
                record_id=record.id,
                provenance=record.provenance,
            )
        )
    return findings


def _valid_taste_scores(entry: Any) -> dict[str, int]:
    if not isinstance(entry, dict):
        return {}
    taste = entry.get("taste")
    if not isinstance(taste, dict):
        return {}
    scores: dict[str, int] = {}
    for key in _TASTE_BY_KEY:
        assessment = taste.get(key)
        score = assessment.get("score") if isinstance(assessment, dict) else None
        if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
            scores[key] = score
    return scores


def report(records: list[CorpusRecord], ratings: dict[str, Any]) -> dict[str, Any]:
    """Summarize coverage without converting taste into an automated verdict."""
    rated_entries = {record.id: _entry_for(record, ratings) for record in records}
    rated_entries = {record_id: entry for record_id, entry in rated_entries.items() if entry}

    gates: list[dict[str, Any]] = []
    for index, dimension in enumerate(HARD_GATES, start=1):
        outcomes = {PASS: 0, FAIL: 0, NOT_APPLICABLE: 0, "unrated": 0}
        for record in records:
            outcome = _outcome(rated_entries.get(record.id), dimension.key)
            outcomes[outcome or "unrated"] += 1
        gates.append(
            {
                "code": f"QG{index}",
                "key": dimension.key,
                "title": dimension.title,
                "prompt": dimension.prompt,
                "severity": "gate",
                **outcomes,
            }
        )

    taste: list[dict[str, Any]] = []
    complete_reference_ids: list[str] = []
    for record_id, entry in rated_entries.items():
        scores = _valid_taste_scores(entry)
        if entry.get("reference") is True and len(scores) == len(TASTE_DIMENSIONS):
            complete_reference_ids.append(record_id)
    for dimension in TASTE_DIMENSIONS:
        scores = [
            scores[dimension.key]
            for entry in rated_entries.values()
            if dimension.key in (scores := _valid_taste_scores(entry))
        ]
        taste.append(
            {
                "key": dimension.key,
                "title": dimension.title,
                "prompt": dimension.prompt,
                "scale": {"min": 1, "max": 5},
                "rated": len(scores),
                "mean": round(sum(scores) / len(scores), 2) if scores else None,
                "regression_gate": False,
            }
        )

    cohort_approved = ratings.get("reference_cohort_approved") is True
    eligible_for_activation = cohort_approved and bool(complete_reference_ids)

    return {
        "hard_gates": gates,
        "taste_dimensions": taste,
        "reference_cohort": {
            "record_ids": sorted(complete_reference_ids),
            "size": len(complete_reference_ids),
            "owner_approved": cohort_approved,
        },
        "subjective_regression_gates_enabled": False,
        "eligible_for_subjective_gate_activation": eligible_for_activation,
        "subjective_gate_status": (
            "eligible but disabled pending a separate activation decision"
            if eligible_for_activation
            else "disabled; a complete owner-rated cohort and explicit approval are required"
        ),
    }


def rules() -> tuple[tuple[str, QualityDimension], ...]:
    return tuple((f"QG{index}", dimension) for index, dimension in enumerate(HARD_GATES, start=1))
