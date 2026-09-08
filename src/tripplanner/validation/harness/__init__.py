"""Scenario execution and evidence capture for the validation harness."""

from tripplanner.validation.harness.context import HarnessContext, harness_scope
from tripplanner.validation.harness.evidence import EvidenceCollector, HarnessEvidence
from tripplanner.validation.harness.report import build_report
from tripplanner.validation.harness.runner import plan_quality, run_scenario

__all__ = [
    "EvidenceCollector",
    "HarnessContext",
    "HarnessEvidence",
    "build_report",
    "harness_scope",
    "plan_quality",
    "run_scenario",
]
