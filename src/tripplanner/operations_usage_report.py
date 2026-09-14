"""Local operations snapshots refreshed without blocking dashboard navigation."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from tripplanner.config import get_settings
from tripplanner.provider_usage import summary

_LOCK = threading.Lock()
_BUILD_LOCK = threading.Lock()
_ENTRIES: dict[str, dict[str, Any]] = {}
_MAX_REPORTS = 8
_FRESH_SECONDS = 60
_LOGGER = logging.getLogger(__name__)


def _path(kwargs: dict[str, Any]) -> Path:
    settings = get_settings()
    identity = json.dumps(
        {
            "version": 1,
            "endpoint": settings.cosmos_endpoint,
            "database": settings.cosmos_database,
            "today": datetime.now(UTC).date().isoformat(),
            **kwargs,
        },
        default=str,
        sort_keys=True,
    )
    root = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    return root / "operations" / "usage-reports" / (sha256(identity.encode()).hexdigest() + ".json")


def _read_saved(path: Path) -> dict[str, Any]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(saved, dict)
            and isinstance(saved.get("report"), dict)
            and isinstance(saved.get("generated_at"), (int, float))
        ):
            return saved
    except (OSError, ValueError, TypeError):
        pass
    return {"report": None, "generated_at": None}


def _save(path: Path, report: dict[str, Any], generated_at: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"report": report, "generated_at": generated_at}), encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    for old in sorted(path.parent.glob("*.json"), key=lambda item: item.stat().st_mtime)[:-32]:
        old.unlink(missing_ok=True)


def _refresh(path: Path, entry: dict[str, Any], kwargs: dict[str, Any], build=None) -> None:
    try:
        if build is not None:
            report = build()
        else:
            with _BUILD_LOCK:
                report = _compact_usage(summary(**kwargs, strict=True))
        generated_at = time.time()
        try:
            _save(path, report, generated_at)
        except OSError:
            _LOGGER.warning("Could not persist local operations report", exc_info=True)
        with _LOCK:
            entry.update(report=report, generated_at=generated_at, error=None)
    except Exception:  # noqa: BLE001 - keep the last successful report, with an explicit error
        _LOGGER.warning("Local operations report refresh failed", exc_info=True)
        with _LOCK:
            entry["error"] = "Report refresh failed. The last successful report is retained."
    finally:
        with _LOCK:
            entry["running"] = False
            entry["retry_at"] = time.time() + _FRESH_SECONDS


def _compact_usage(report: dict[str, Any]) -> dict[str, Any]:
    result = dict(report)
    # The dashboard drills into trip creation/updates only. Keep global totals,
    # but do not transfer thousands of never-rendered background detail rows.
    for field in ("by_trip", "by_provider", "by_operation", "by_interaction"):
        result[field] = [
            row
            for row in report.get(field, [])
            if row.get("interaction_kind") in {"new_trip", "trip_update"}
        ]
    return result


def _with_names(report: dict[str, Any] | None, names: dict[str, str]) -> dict[str, Any] | None:
    if report is None:
        return None
    result = _compact_usage(report)
    for field in ("by_trip", "by_provider", "by_operation", "by_interaction"):
        result[field] = [
            dict(row, trip_name=names.get(str(row.get("trip_id") or ""), ""))
            for row in result.get(field, [])
        ]
    return result


def get_report(**kwargs) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    names = kwargs.pop("trip_names", {})
    if not get_settings().cosmos_emulator:
        report = summary(**kwargs, trip_names=names)
        return report, {"state": "ready", "generated_at": datetime.now(UTC).isoformat()}
    path = _path(kwargs)
    key = str(path)
    with _LOCK:
        if key not in _ENTRIES:
            if len(_ENTRIES) >= _MAX_REPORTS:
                idle = next(
                    (key for key, entry in _ENTRIES.items() if not entry.get("running")), None
                )
                if idle is None:
                    return None, {"state": "pending", "generated_at": None}
                del _ENTRIES[idle]
            _ENTRIES[key] = _read_saved(path)
        entry = _ENTRIES[key]
        now = time.time()
        stale = entry["generated_at"] is None or now - entry["generated_at"] >= _FRESH_SECONDS
        if stale and not entry.get("running") and now >= entry.get("retry_at", 0):
            entry["running"] = True
            threading.Thread(
                target=_refresh,
                args=(path, entry, dict(kwargs)),
                daemon=True,
                name="operations-report-refresh",
            ).start()
        state = (
            "error"
            if entry.get("error")
            else "refreshing"
            if entry.get("running") and entry["report"] is not None
            else "pending"
            if entry["report"] is None
            else "ready"
        )
        report = entry["report"]
        generated_at = entry["generated_at"]
        error = entry.get("error")
    return _with_names(report, names), {
        "state": state,
        "generated_at": datetime.fromtimestamp(generated_at, UTC).isoformat()
        if generated_at
        else None,
        "error": error,
    }


def get_base(build, **identity) -> dict[str, Any]:
    if not get_settings().cosmos_emulator:
        return build()
    path = _path({"section": "overview-base", **identity})
    key = str(path)
    with _LOCK:
        entry = _ENTRIES.get(key)
        if entry is None:
            entry = _read_saved(path)
            if entry["report"] is None:
                entry = {"report": build(), "generated_at": time.time()}
                try:
                    _save(path, entry["report"], entry["generated_at"])
                except OSError:
                    _LOGGER.warning("Could not persist local operations overview", exc_info=True)
            if len(_ENTRIES) >= _MAX_REPORTS:
                idle = next(
                    (key for key, value in _ENTRIES.items() if not value.get("running")), None
                )
                if idle is None:
                    return dict(entry["report"])
                del _ENTRIES[idle]
            _ENTRIES[key] = entry
        now = time.time()
        if (
            now - entry["generated_at"] >= _FRESH_SECONDS
            and not entry.get("running")
            and now >= entry.get("retry_at", 0)
        ):
            entry["running"] = True
            threading.Thread(
                target=_refresh,
                args=(path, entry, {}, build),
                daemon=True,
                name="operations-overview-refresh",
            ).start()
        result = dict(entry["report"])
        result["overview_status"] = {
            "state": "error"
            if entry.get("error")
            else "refreshing"
            if entry.get("running")
            else "ready",
            "error": entry.get("error"),
        }
        return result
