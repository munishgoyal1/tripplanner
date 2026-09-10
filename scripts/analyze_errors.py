"""Generate a read-only local or canary failure report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tripplanner.alert_events import recent as alert_events_recent  # noqa: E402
from tripplanner.error_analysis import (  # noqa: E402
    failures_from_azure_result,
    failures_from_local_log,
    render_report,
    shared_diagnostics_dir,
)


def _run_az(arguments: list[str]) -> Any:
    completed = subprocess.run(
        ["az", *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _canary_failures(resource_group: str, workspace_id: str, hours: int):
    if not workspace_id:
        workspace_ids = _run_az(
            [
                "monitor",
                "log-analytics",
                "workspace",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[?starts_with(name, 'canary-logs-')].customerId",
            ]
        )
        if not isinstance(workspace_ids, list) or len(workspace_ids) != 1:
            raise RuntimeError(
                f"Expected one canary Log Analytics workspace in {resource_group}; "
                f"found {len(workspace_ids) if isinstance(workspace_ids, list) else 0}."
            )
        workspace_id = str(workspace_ids[0])
    query = (ROOT / "infra" / "queries" / "application-failures.kql").read_text(
        encoding="utf-8"
    )
    payload = _run_az(
        [
            "monitor",
            "log-analytics",
            "query",
            "--workspace",
            workspace_id,
            "--analytics-query",
            query,
            "--timespan",
            f"PT{hours}H",
        ]
    )
    return failures_from_azure_result(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("local", "canary"))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--resource-group", default="rg-tripplanner-canary")
    parser.add_argument("--workspace-id", default="")
    args = parser.parse_args()

    if args.hours < 1:
        parser.error("--hours must be at least 1")
    diagnostics_dir = shared_diagnostics_dir(ROOT)
    local_log_path = args.log_path or diagnostics_dir / "local-app.jsonl"
    if args.environment == "local":
        failures = failures_from_local_log(local_log_path)
    else:
        failures = _canary_failures(args.resource_group, args.workspace_id, args.hours)

    # Durable alert-condition history (application failures, latency, throttling,
    # circuit-breaker, cache degradation, Cosmos 429s, GCP quota) -- captured
    # in-app, independent of whether the alert's own email was ever seen.
    alert_days = max(1, -(-args.hours // 24))  # ceil(hours / 24)
    try:
        alerts = alert_events_recent(limit=200, days=alert_days)
    except Exception as exc:  # noqa: BLE001 - a scan must still report failures found so far
        print(f"Warning: could not read alert_events ({type(exc).__name__}).")
        alerts = []

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = args.report_path or diagnostics_dir / (
        f"{args.environment}-errors-{timestamp}.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(args.environment, failures, hours=args.hours, alert_signals=alerts),
        encoding="utf-8",
    )
    print(
        f"Wrote {report_path} ({len(failures)} failure records, "
        f"{len(alerts)} alert signals fired)."
    )
    return 1 if (failures or alerts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
