"""Persist accepted finding groups and select newly observed failures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tripplanner.evals.findings import Group

BASELINE_VERSION = 1

def load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": BASELINE_VERSION, "accepted": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": BASELINE_VERSION, "accepted": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("accepted"), dict):
        return {"version": BASELINE_VERSION, "accepted": {}}
    return payload


def new_groups(groups: list[Group], baseline: dict[str, Any]) -> list[Group]:
    accepted = baseline.get("accepted") or {}
    return [item for item in groups if item.key not in accepted]


def stale_keys(groups: list[Group], baseline: dict[str, Any]) -> list[str]:
    """Accepted findings that no longer occur, so the baseline can shrink."""
    live = {item.key for item in groups}
    return sorted(key for key in (baseline.get("accepted") or {}) if key not in live)


def accept(groups: list[Group], baseline: dict[str, Any]) -> dict[str, Any]:
    """Record every current finding as known, preserving earlier acceptances."""
    accepted = dict(baseline.get("accepted") or {})
    today = datetime.now(UTC).date().isoformat()
    for item in groups:
        existing = accepted.get(item.key) or {}
        accepted[item.key] = {
            "rule": item.rule,
            "symptom": item.symptom,
            "accepted_on": existing.get("accepted_on") or today,
            "count_when_accepted": existing.get("count_when_accepted") or item.count,
            "example": existing.get("example") or item.exemplar.message,
        }
    return {"version": BASELINE_VERSION, "accepted": accepted}


def save_baseline(path: Path, baseline: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        "version": BASELINE_VERSION,
        "accepted": dict(sorted((baseline.get("accepted") or {}).items())),
    }
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
