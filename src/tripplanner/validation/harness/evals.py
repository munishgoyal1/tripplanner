"""Harness namespace for deterministic plan-quality evaluations.

The legacy ``tripplanner.evals`` module remains available to existing scripts and
callers. Harness orchestration imports through this module so eval execution and
reporting have one stable validation namespace while compatibility is preserved.
"""

from tripplanner.evals import (
    SCENARIOS,
    CheckResult,
    EvalCheck,
    EvalResult,
    EvalScenario,
    evaluate_plan,
    format_result,
    scenario_by_id,
)

__all__ = [
    "SCENARIOS",
    "CheckResult",
    "EvalCheck",
    "EvalResult",
    "EvalScenario",
    "evaluate_plan",
    "format_result",
    "scenario_by_id",
]
