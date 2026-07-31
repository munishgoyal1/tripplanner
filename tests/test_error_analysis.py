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
    worker = tmp_path / "tripplanner.worktrees" / "worker-1"
    worker.mkdir(parents=True)
    monkeypatch.setattr(
        "tripplanner.error_analysis.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=str(primary / ".git") + "\n"
        ),
    )

    assert shared_diagnostics_dir(worker) == primary / "logs" / "diagnostics"


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
    assert "param enableFailureAlerts = true" in production
    assert "munishgoyal1@gmail.com" in production
    assert "enableFailureAlerts" not in canary
    assert 'event_kind == "chat_operation" and outcome == "error"' in query
    assert 'event_kind == "tool_call" and status == "error"' in query
