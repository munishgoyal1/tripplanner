from __future__ import annotations

import pytest

from scripts import runtime_evidence_gate


def _report(
    scenario: str,
    *,
    rounds: int,
    quality: float = 1.0,
    wall_ms: float = 80_000.0,
    throttled: int = 0,
    sha: str = "candidate",
) -> dict:
    return {
        "run": {"scenario_id": scenario, "git_sha": sha},
        "model": {"rounds": rounds, "throttled_rounds": throttled},
        "performance": {"scenario_wall_ms": wall_ms},
        "quality": {"passed": True, "score": quality},
    }


def _reports(rounds: int, *, sha: str) -> list[dict]:
    return [
        _report(scenario, rounds=rounds, sha=sha)
        for scenario in runtime_evidence_gate.CORE_SCENARIOS
    ] + [
        _report("provider_degraded", rounds=rounds, sha=sha),
        _report("model_throttled", rounds=rounds, throttled=1, sha=sha),
    ]


def test_gate_accepts_thirty_percent_fewer_rounds_without_quality_loss() -> None:
    result = runtime_evidence_gate.compare_reports(
        _reports(10, sha="baseline"),
        _reports(7, sha="candidate"),
    )

    assert result["status"] == "passed"
    assert result["model_rounds"]["reduction"] == 0.3
    assert result["candidate_git_shas"] == ["candidate"]


def test_gate_rejects_insufficient_model_round_reduction() -> None:
    with pytest.raises(runtime_evidence_gate.RuntimeEvidenceError, match="30%"):
        runtime_evidence_gate.compare_reports(
            _reports(10, sha="baseline"),
            _reports(8, sha="candidate"),
        )


def test_gate_rejects_quality_or_resilience_gaps() -> None:
    candidate = _reports(7, sha="candidate")
    candidate[0]["quality"]["passed"] = False
    with pytest.raises(runtime_evidence_gate.RuntimeEvidenceError, match="quality"):
        runtime_evidence_gate.compare_reports(_reports(10, sha="baseline"), candidate)

    candidate = _reports(7, sha="candidate")
    candidate[-1]["model"]["throttled_rounds"] = 0
    with pytest.raises(runtime_evidence_gate.RuntimeEvidenceError, match="throttling"):
        runtime_evidence_gate.compare_reports(_reports(10, sha="baseline"), candidate)
