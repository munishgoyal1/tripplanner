"""PII-safe classification and reporting for local and canary failures."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tripplanner.observability import redact_text


@dataclass(frozen=True)
class Failure:
    timestamp: str
    category: str
    signature: str


def classify_event(event: dict[str, Any]) -> Failure | None:
    normalized = {str(key).lower(): value for key, value in event.items()}
    event_kind = str(normalized.get("event_kind") or normalized.get("eventkind") or "")
    outcome = str(normalized.get("outcome") or "").lower()
    status = str(normalized.get("status") or "").lower()
    level = str(normalized.get("level") or "").upper()
    error_type = _safe_label(normalized.get("error") or normalized.get("errortype"))
    logger = _safe_label(normalized.get("logger"))
    tool = _safe_label(normalized.get("tool"))
    timestamp = str(normalized.get("ts") or normalized.get("timestamp") or "unknown")

    if event_kind == "chat_operation" and outcome == "error":
        return Failure(timestamp, "chat", f"chat:{error_type or 'unknown'}")
    if event_kind == "tool_call" and status == "error":
        return Failure(timestamp, "tool", f"tool:{tool or 'unknown'}:{error_type or 'unknown'}")
    if level in {"ERROR", "CRITICAL"}:
        return Failure(timestamp, "application", f"application:{logger or 'unknown'}")
    return None


def failures_from_local_log(path: Path) -> list[Failure]:
    failures: list[Failure] = []
    candidates = [path, *sorted(path.parent.glob(f"{path.name}.*"))]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and (failure := classify_event(event)):
                failures.append(failure)
    return failures


def failures_from_azure_result(payload: Any) -> list[Failure]:
    events: list[dict[str, Any]] = []
    if isinstance(payload, list):
        events = [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict):
        for table in payload.get("tables", []):
            columns = [column["name"] for column in table.get("columns", [])]
            events.extend(dict(zip(columns, row, strict=False)) for row in table.get("rows", []))
    return [failure for event in events if (failure := classify_event(event))]


def render_report(
    environment: str,
    failures: Iterable[Failure],
    *,
    hours: int,
    generated_at: dt.datetime | None = None,
) -> str:
    records = list(failures)
    generated = generated_at or dt.datetime.now(dt.UTC)
    generated_text = generated.isoformat(timespec="seconds").replace("+00:00", "Z")
    lines = [
        f"# {environment.title()} Error Analysis",
        "",
        f"Generated: {generated_text}",
        f"Window: last {hours} hours",
        f"Status: {'FAILURES DETECTED' if records else 'No failures detected'}",
        f"Failure records: {len(records)}",
        "",
    ]
    if records:
        counts = Counter((record.category, record.signature) for record in records)
        lines.extend(
            ["## Failure Groups", "", "| Category | Signature | Count |", "|---|---|---:|"]
        )
        for (category, signature), count in sorted(counts.items()):
            lines.append(f"| {category} | `{signature}` | {count} |")
        lines.extend(["", "## Recommended Checks", ""])
        categories = {record.category for record in records}
        if "application" in categories:
            lines.append(
                "- Inspect the affected Container App revision and surrounding sanitized logs."
            )
        if "chat" in categories:
            lines.append(
                "- Compare chat failure classes with admission, model, and persistence events."
            )
        if "tool" in categories:
            lines.append(
                "- Review the named tool's provider health, configuration, latency, "
                "and cache behavior."
            )
        lines.append("- Re-run this report after the fix and confirm the next window is clean.")
    else:
        lines.extend(
            ["## Result", "", "No matching application, chat, or tool failures were found."]
        )
    return "\n".join(lines) + "\n"


def _safe_label(value: Any) -> str:
    if value is None:
        return ""
    return str(redact_text(str(value))).replace("|", "/").replace("`", "'")[:120]
