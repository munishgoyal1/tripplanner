"""Append-only feedback for saved trips."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tripplanner import storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.user_context import get_user_id

_COSMOS_CONTAINER = "trip_feedback"
_LOCAL_ROOT = Path.home() / ".tripplanner" / "trip_feedback"


def _local_dir() -> Path:
    return _LOCAL_ROOT / get_user_id()


def append(
    *,
    trip_id: str,
    trip_revision: str,
    sentiment: str | None,
    rating: int | None,
    comment: str | None,
    surface: str,
    client: str,
    identified: bool,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    feedback_id = f"fb_{uuid4().hex}"
    submission = {
        "feedback_id": feedback_id,
        "trip_id": trip_id,
        "trip_revision": trip_revision,
        "identified": identified,
        "sentiment": sentiment,
        "rating": rating,
        "comment": (comment or "").strip() or None,
        "day": None,
        "surface": surface,
        "client": client,
        "created_at": created_at,
    }
    if storage_cosmos.is_enabled():
        storage_cosmos.create_doc_if_absent(
            _COSMOS_CONTAINER, get_user_id(), feedback_id, submission
        )
    else:
        directory = _local_dir()
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(directory / f"{feedback_id}.json", submission, indent=2)
    return submission


def amend(
    feedback_id: str,
    *,
    trip_id: str,
    rating: int | None,
    comment: str | None,
) -> dict[str, Any] | None:
    if storage_cosmos.is_enabled():
        submission = storage_cosmos.read_doc(_COSMOS_CONTAINER, get_user_id(), feedback_id)
        if not submission or submission.get("trip_id") != trip_id:
            return None
        submission["rating"] = rating
        submission["comment"] = (comment or "").strip() or None
        storage_cosmos.upsert_doc(_COSMOS_CONTAINER, get_user_id(), feedback_id, submission)
        return submission

    path = _local_dir() / f"{feedback_id}.json"
    try:
        submission = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if submission.get("trip_id") != trip_id:
        return None
    submission["rating"] = rating
    submission["comment"] = (comment or "").strip() or None
    atomic_write_json(path, submission, indent=2)
    return submission


def delete_for_trip(trip_id: str) -> int:
    if storage_cosmos.is_enabled():
        rows = storage_cosmos.query_docs(_COSMOS_CONTAINER, get_user_id())
        matching = [row for row in rows if row.get("trip_id") == trip_id]
        for row in matching:
            feedback_id = str(row.get("feedback_id") or "")
            if feedback_id:
                storage_cosmos.delete_doc(_COSMOS_CONTAINER, get_user_id(), feedback_id)
        return len(matching)

    deleted = 0
    for path in _local_dir().glob("fb_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("trip_id") != trip_id:
                continue
            path.unlink(missing_ok=True)
            deleted += 1
        except (OSError, json.JSONDecodeError):
            continue
    return deleted


def clear() -> int:
    if storage_cosmos.is_enabled():
        return storage_cosmos.delete_docs(_COSMOS_CONTAINER, get_user_id())

    deleted = 0
    for path in _local_dir().glob("fb_*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted
