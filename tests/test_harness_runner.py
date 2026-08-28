from __future__ import annotations

import json

from tripplanner.observability import app_event
from tripplanner.validation.harness import run_scenario
from tripplanner.validation.harness.evals import scenario_by_id


def test_runner_correlates_execution_and_writes_report(tmp_path) -> None:
    output = tmp_path / "reports" / "run.json"

    def execute() -> dict[str, str]:
        app_event("outbound_http", endpoint="example.com", status="ok", ms=12)
        return {"trip_id": "trip-1"}

    report = run_scenario(
        "smoke",
        execute,
        run_id="run-1",
        quality=lambda result: {"passed": result == {"trip_id": "trip-1"}},
        output_path=output,
    )

    assert report["run"] == {
        "run_id": "run-1",
        "scenario_id": "smoke",
        "environment": "local",
    }
    assert report["amplification"]["outbound_requests"] == 1
    assert report["quality"]["passed"] is True
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_harness_eval_namespace_preserves_legacy_scenarios() -> None:
    assert scenario_by_id("family_dubai_accessible").name == "Dubai family trip with elderly parent"
