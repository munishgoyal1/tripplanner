from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

CORE_SCENARIOS = (
    "new_trip_cold",
    "new_trip_warm",
    "existing_trip_cold",
    "existing_trip_warm",
)
RESILIENCE_SCENARIOS = ("provider_degraded", "model_throttled")
REQUIRED_SCENARIOS = (*CORE_SCENARIOS, *RESILIENCE_SCENARIOS)
MAX_P95_MS = 120_000.0
MAX_ROUND_RATIO = 0.70


class RuntimeEvidenceError(RuntimeError):
    pass


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    rank = max(1, int((len(ordered) * percentage + 99) // 100))
    return ordered[min(rank, len(ordered)) - 1]


def _scenario(report: dict[str, Any]) -> str:
    return str((report.get("run") or {}).get("scenario_id") or "")


def _quality_score(report: dict[str, Any]) -> float:
    quality = report.get("quality") or {}
    if quality.get("passed") is not True:
        raise RuntimeEvidenceError(f"{_scenario(report)} did not pass quality checks")
    return float(quality.get("score", 1.0))


def compare_reports(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> dict[str, Any]:
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in candidate:
        by_scenario[_scenario(report)].append(report)
    missing = [name for name in REQUIRED_SCENARIOS if not by_scenario[name]]
    if missing:
        raise RuntimeEvidenceError(
            f"Candidate evidence is missing scenarios: {', '.join(missing)}"
        )

    baseline_core = [report for report in baseline if _scenario(report) in CORE_SCENARIOS]
    candidate_core = [report for report in candidate if _scenario(report) in CORE_SCENARIOS]
    if not baseline_core:
        raise RuntimeEvidenceError("Baseline evidence has no core trip scenarios")

    baseline_rounds = sum(
        int((report.get("model") or {}).get("rounds") or 0)
        for report in baseline_core
    )
    candidate_rounds = sum(
        int((report.get("model") or {}).get("rounds") or 0)
        for report in candidate_core
    )
    round_ratio = candidate_rounds / baseline_rounds if baseline_rounds else 1.0
    if round_ratio > MAX_ROUND_RATIO:
        raise RuntimeEvidenceError(
            f"Model rounds fell by only {(1 - round_ratio) * 100:.1f}%; 30% is required"
        )

    durations = [
        float((report.get("performance") or {}).get("scenario_wall_ms") or 0)
        for report in candidate
    ]
    p95_ms = _percentile(durations, 95)
    if p95_ms > MAX_P95_MS:
        raise RuntimeEvidenceError(
            f"Candidate p95 is {p95_ms:.1f} ms; limit is {MAX_P95_MS:.1f} ms"
        )

    baseline_quality = sum(_quality_score(report) for report in baseline_core) / len(
        baseline_core
    )
    candidate_quality = sum(_quality_score(report) for report in candidate) / len(
        candidate
    )
    if candidate_quality < baseline_quality:
        raise RuntimeEvidenceError(
            f"Quality fell from {baseline_quality:.4f} to {candidate_quality:.4f}"
        )

    throttled = by_scenario["model_throttled"]
    if not any(
        int((report.get("model") or {}).get("throttled_rounds") or 0)
        for report in throttled
    ):
        raise RuntimeEvidenceError("Model-throttled evidence did not exercise throttling")

    return {
        "status": "passed",
        "baseline_git_shas": sorted(
            {str((report.get("run") or {}).get("git_sha") or "unknown") for report in baseline}
        ),
        "candidate_git_shas": sorted(
            {str((report.get("run") or {}).get("git_sha") or "unknown") for report in candidate}
        ),
        "model_rounds": {
            "baseline": baseline_rounds,
            "candidate": candidate_rounds,
            "reduction": round(1 - round_ratio, 4),
        },
        "p95_ms": p95_ms,
        "quality": {
            "baseline": round(baseline_quality, 4),
            "candidate": round(candidate_quality, 4),
        },
        "scenarios": list(REQUIRED_SCENARIOS),
    }


def _load(paths: list[Path]) -> list[dict[str, Any]]:
    files = [
        file
        for path in paths
        for file in (sorted(path.rglob("*.json")) if path.is_dir() else [path])
    ]
    return [json.loads(file.read_text(encoding="utf-8")) for file in files]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare representative trip runtime evidence without calling providers."
    )
    parser.add_argument("--baseline", type=Path, action="append", required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--report-path", type=Path)
    args = parser.parse_args()
    result = compare_reports(_load(args.baseline), _load(args.candidate))
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report_path:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
