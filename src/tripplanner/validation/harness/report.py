"""Unified harness report assembly and policy-independent evidence export."""

from __future__ import annotations

from typing import Any

from tripplanner.validation.harness.evaluators import (
    evaluate_amplification,
    evaluate_cache,
    evaluate_cost,
    evaluate_model,
    evaluate_performance,
)
from tripplanner.validation.harness.evidence import HarnessEvidence


def build_report(
    evidence: HarnessEvidence,
    *,
    quality: dict[str, Any] | None = None,
    billing: dict[str, Any] | None = None,
    git_sha: str = "unknown",
) -> dict[str, Any]:
    """Build one report while preserving measured, estimated, and billed layers."""
    cost = evaluate_cost(evidence)
    cost["billing_reconciliation"] = billing or {
        "status": "not_available",
        "source": "cloud_billing_export",
    }
    return {
        "version": 2,
        "run": {
            "run_id": evidence.run_id,
            "scenario_id": evidence.scenario_id,
            "environment": evidence.environment,
            "git_sha": git_sha,
        },
        "cost": cost,
        "model": evaluate_model(evidence),
        "cache": evaluate_cache(evidence),
        "amplification": evaluate_amplification(evidence),
        "performance": evaluate_performance(evidence),
        "quality": quality or {
            "status": "not_evaluated",
            "subjective_evaluation_costed_separately": True,
        },
    }
