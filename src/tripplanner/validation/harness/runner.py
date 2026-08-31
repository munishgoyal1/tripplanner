"""Scenario orchestration for correlated execution, evaluation, and report export."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from tripplanner.observability import timed_operation
from tripplanner.validation.harness.context import harness_scope
from tripplanner.validation.harness.evals import EvalResult, EvalScenario, evaluate_plan
from tripplanner.validation.harness.evidence import EvidenceCollector
from tripplanner.validation.harness.report import build_report


def plan_quality(
    scenario: EvalScenario,
    plan: dict[str, Any],
    final_reply: str = "",
) -> dict[str, Any]:
    result = evaluate_plan(scenario, plan, final_reply)
    return _eval_result(result)


def _eval_result(result: EvalResult) -> dict[str, Any]:
    return {
        "source": "deterministic_plan_evaluation",
        "scenario_id": result.scenario_id,
        "score": result.score,
        "passed": result.passed,
        "checks": [
            {
                "id": check.id,
                "description": check.description,
                "passed": check.passed,
                "reason": check.reason,
                "weight": check.weight,
            }
            for check in result.checks
        ],
        "subjective_evaluation_costed_separately": True,
    }


def run_scenario(
    scenario_id: str,
    execute: Callable[[], dict[str, Any] | None],
    *,
    environment: str = "local",
    run_id: str | None = None,
    quality: Callable[[dict[str, Any] | None], dict[str, Any]] | None = None,
    billing: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute one scenario and return its correlated unified report."""
    actual_run_id = run_id or uuid4().hex
    with harness_scope(scenario_id, run_id=actual_run_id, environment=environment):
        with EvidenceCollector(actual_run_id, scenario_id, environment) as collector:
            with timed_operation("scenario_operation", "execute"):
                result = execute()

    quality_result = quality(result) if quality else None
    report = build_report(collector.evidence, quality=quality_result, billing=billing)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        output_path.write_text(payload, encoding="utf-8")
    return report
