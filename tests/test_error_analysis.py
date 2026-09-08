from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

from tripplanner.error_analysis import (
    classify_event,
    failures_from_azure_result,
    failures_from_local_log,
    render_report,
    shared_diagnostics_dir,
)


def test_shared_diagnostics_dir_uses_primary_git_worktree(monkeypatch, tmp_path: Path) -> None:
    primary = tmp_path / "tripplanner"
    sandbox = tmp_path / "tripplanner.worktrees" / "sbx-1-diagnostics"
    sandbox.mkdir(parents=True)
    monkeypatch.setattr(
        "tripplanner.error_analysis.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=str(primary / ".git") + "\n"
        ),
    )

    assert shared_diagnostics_dir(sandbox) == primary / "logs" / "diagnostics"


def test_classifies_only_failure_signals() -> None:
    assert classify_event({"event_kind": "chat_operation", "outcome": "completed"}) is None
    assert classify_event({"event_kind": "chat_operation", "outcome": "capped"}) is None
    assert classify_event({"event_kind": "tool_call", "status": "ok"}) is None
    assert classify_event({"level": "INFO"}) is None

    chat = classify_event(
        {
            "ts": "2026-07-30T10:00:00Z",
            "event_kind": "chat_operation",
            "outcome": "error",
            "error": "TimeoutError",
        }
    )
    tool = classify_event(
        {"event_kind": "tool_call", "status": "error", "tool": "routing", "error": "HTTPError"}
    )
    application = classify_event({"level": "CRITICAL", "logger": "tripplanner.api"})

    assert chat and chat.signature == "chat:TimeoutError"
    assert tool and tool.signature == "tool:routing:HTTPError"
    assert application and application.signature == "application:tripplanner.api"


def test_rate_limit_signature_includes_safe_provider_scope() -> None:
    failure = classify_event(
        {
            "event_kind": "chat_operation",
            "outcome": "error",
            "error": "RateLimitError",
            "rate_limit_scope": "tokens",
        }
    )

    assert failure and failure.signature == "chat:RateLimitError:tokens"


def test_reads_current_and_rotated_local_json_without_raw_messages(tmp_path: Path) -> None:
    path = tmp_path / "local-app.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"level": "INFO", "msg": "ok"}),
                json.dumps({"level": "ERROR", "logger": "tripplanner.api", "msg": "private"}),
                "not json",
            ]
        ),
        encoding="utf-8",
    )
    path.with_name("local-app.jsonl.1").write_text(
        json.dumps({"event_kind": "tool_call", "status": "error", "tool": "weather"}),
        encoding="utf-8",
    )

    failures = failures_from_local_log(path)
    report = render_report(
        "local",
        failures,
        hours=24,
        generated_at=dt.datetime(2026, 7, 30, tzinfo=dt.UTC),
    )

    assert len(failures) == 2
    assert "application:tripplanner.api" in report
    assert "tool:weather:unknown" in report
    assert "private" not in report


def test_parses_log_analytics_table_shape_and_redacts_labels() -> None:
    payload = {
        "tables": [
            {
                "columns": [
                    {"name": "Timestamp"},
                    {"name": "EventKind"},
                    {"name": "Outcome"},
                    {"name": "ErrorType"},
                ],
                "rows": [["2026-07-30T10:00:00Z", "chat_operation", "error", "alice@example.com"]],
            }
        ]
    }

    failures = failures_from_azure_result(payload)

    assert failures[0].signature == "chat:<email>"


def test_infrastructure_enables_email_alerts_only_in_production() -> None:
    root = Path(__file__).parents[1]
    template = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    production = (root / "infra" / "prod.bicepparam").read_text(encoding="utf-8")
    canary = (root / "infra" / "canary.bicepparam").read_text(encoding="utf-8")
    query = (root / "infra" / "queries" / "application-failures.kql").read_text(
        encoding="utf-8"
    )

    assert "param enableFailureAlerts bool = false" in template
    assert "if (enableFailureAlerts)" in template
    assert "loadTextContent('queries/application-failures.kql')" in template
    assert "autoMitigate: true" in template
    assert "muteActionsDuration" not in template
    assert "param enableFailureAlerts = true" in production
    assert "munishgoyal@aitripplanner.co" in production
    assert "enableFailureAlerts" not in canary
    assert 'event_kind == "chat_operation" and outcome == "error"' in query
    assert 'event_kind == "tool_call" and status == "error"' in query


def test_infrastructure_alerts_on_runtime_degradation_with_volume_guards() -> None:
    root = Path(__file__).parents[1]
    template = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    queries = {
        name: (root / "infra" / "queries" / name).read_text(encoding="utf-8")
        for name in (
            "chat-latency-burn.kql",
            "model-throttling.kql",
            "provider-circuit-open.kql",
            "cache-degradation.kql",
        )
    }

    assert "resource operationalAlertRules" in template
    assert "if (enableFailureAlerts)" in template
    assert "actionGroups: [failureAlertActions.id]" in template
    for alert_name, severity in (
        ("chat-latency-burn", 2),
        ("model-throttling", 2),
        ("provider-circuit-open", 3),
        ("cache-degradation", 3),
    ):
        alert_block = template.split(f"name: '{alert_name}'", 1)[1].split("query:", 1)[0]
        assert "displayName: '[${namePrefix}]" in alert_block
        assert f"severity: {severity}" in alert_block
    assert "resource cosmosThrottlingAlert" in template
    cosmos_block = template.split("resource cosmosThrottlingAlert", 1)[1].split(
        "resource env", 1
    )[0]
    assert "description: '[${namePrefix}]" in cosmos_block
    assert "severity: 3" in cosmos_block
    assert "windowSize: 'PT15M'" in cosmos_block
    assert "metricName: 'TotalRequests'" in cosmos_block
    assert "name: 'StatusCode'" in cosmos_block
    assert "values: ['429']" in cosmos_block
    assert "threshold: 20" in cosmos_block
    assert "Samples >= 5 and P95DurationMs > 120000" in queries[
        "chat-latency-burn.kql"
    ]
    assert "Samples >= 5 and Throttles >= 2" in queries["model-throttling.kql"]
    assert "OpenSignals >= 3 and LastSeen - FirstSeen >= 5m" in queries[
        "provider-circuit-open.kql"
    ]
    assert "Accesses >= 20 and MissRate >= 0.5" in queries[
        "cache-degradation.kql"
    ]


def test_infrastructure_wires_openrouteservice_from_environment_files() -> None:
    root = Path(__file__).parents[1]
    template = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    production = (root / "infra" / "prod.bicepparam").read_text(encoding="utf-8")
    canary = (root / "infra" / "canary.bicepparam").read_text(encoding="utf-8")

    assert "param openRouteServiceApiKey string = ''" in template
    assert "param openRouteServiceBaseUrl string = 'https://api.openrouteservice.org'" in template
    assert "param openRouteServiceRouteTtlSec int = 21600" in template
    assert "{ name: 'openrouteservice-api-key', value: openRouteServiceApiKey }" in template
    assert "{ name: 'OPENROUTESERVICE_API_KEY', secretRef: 'openrouteservice-api-key' }" in template
    assert "{ name: 'OPENROUTESERVICE_BASE_URL', value: openRouteServiceBaseUrl }" in template
    assert "{ name: 'OPENROUTESERVICE_ROUTE_TTL_SEC', value: string(openRouteServiceRouteTtlSec) }" in template

    assert "readEnvironmentVariable('OPENROUTESERVICE_API_KEY', '')" in canary
    assert "readEnvironmentVariable('OPENROUTESERVICE_BASE_URL', 'https://api.openrouteservice.org')" in canary
    assert "int(readEnvironmentVariable('OPENROUTESERVICE_ROUTE_TTL_SEC', '21600'))" in canary

    assert "readEnvironmentVariable('OPENROUTESERVICE_API_KEY', '')" in production
    assert "readEnvironmentVariable('OPENROUTESERVICE_BASE_URL', 'https://api.openrouteservice.org')" in production
    assert "int(readEnvironmentVariable('OPENROUTESERVICE_ROUTE_TTL_SEC', '21600'))" in production
