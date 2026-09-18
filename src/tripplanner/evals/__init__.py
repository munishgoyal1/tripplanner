"""Evaluation ownership, with the original plan-eval public API preserved."""

from importlib import import_module

__all__ = [
    "SCENARIOS", "CheckResult", "EvalCheck", "EvalResult", "EvalScenario",
    "evaluate_plan", "format_result", "main", "scenario_by_id",
]


def __getattr__(name: str):
    if name in __all__:
        return getattr(import_module("tripplanner.evals.deterministic.plan"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
