"""Durable environment-wide admission limits for model-bearing conversations."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.agents.trip_agent import latest_user_has_planning_intent
from tripplanner.graph_policy import (
    latest_user_requests_different_trip,
    latest_user_starts_new_trip,
    pending_trip_kickoff_answer,
)
from tripplanner.json_store import atomic_write_json

ConversationCategory = Literal["new_trip", "existing_trip_turn", "continuation"]

_CONTAINER = "users"
_PARTITION = "_system"
_DOCUMENT_ID = "conversation_limits_v1"
_MAX_WRITE_ATTEMPTS = 5
_MAX_RECENT_REQUESTS = 500
_LOCAL_LOCK = Lock()

_ENV_NAMES = {
    ("new_trip", "daily"): "CHAT_NEW_TRIP_LIMIT_DAILY",
    ("existing_trip_turn", "daily"): "CHAT_EXISTING_TRIP_TURN_LIMIT_DAILY",
    ("new_trip", "weekly"): "CHAT_NEW_TRIP_LIMIT_WEEKLY",
    ("existing_trip_turn", "weekly"): "CHAT_EXISTING_TRIP_TURN_LIMIT_WEEKLY",
    ("new_trip", "lifetime"): "CHAT_NEW_TRIP_LIMIT_LIFETIME",
    ("existing_trip_turn", "lifetime"): "CHAT_EXISTING_TRIP_TURN_LIMIT_LIFETIME",
}


class ConversationLimitError(RuntimeError):
    def __init__(
        self,
        *,
        category: ConversationCategory,
        window: str,
        used: int,
        limit: int,
        resets_at: str | None,
    ) -> None:
        super().__init__(f"{category} {window} limit reached")
        self.category = category
        self.window = window
        self.used = used
        self.limit = limit
        self.resets_at = resets_at

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": "conversation_limit_reached",
            "category": self.category,
            "window": self.window,
            "used": self.used,
            "limit": self.limit,
            "resets_at": self.resets_at,
        }


def classify_conversation(
    history: Sequence[BaseMessage],
    message: str,
    active_trip: dict[str, Any],
) -> ConversationCategory:
    messages = [*history, HumanMessage(content=message)]
    if pending_trip_kickoff_answer(messages):
        return "continuation"
    if (
        latest_user_starts_new_trip(messages)
        or latest_user_requests_different_trip(messages, active_trip)
        or (
            not str(active_trip.get("destination") or "").strip()
            and latest_user_has_planning_intent(messages)
        )
    ):
        return "new_trip"
    return "existing_trip_turn"


def _limit(category: str, window: str) -> int:
    try:
        return max(0, int(os.getenv(_ENV_NAMES[(category, window)], "0")))
    except (TypeError, ValueError):
        return 0


def _window_key(window: str, now: datetime) -> str:
    if window == "daily":
        return now.strftime("%Y-%m-%d")
    if window == "weekly":
        return now.strftime("%G-W%V")
    return "lifetime"


def _resets_at(window: str, now: datetime) -> str | None:
    if window == "daily":
        reset = datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1)
    elif window == "weekly":
        reset = datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(
            days=7 - now.weekday()
        )
    else:
        return None
    return reset.isoformat().replace("+00:00", "Z")


def _empty_body() -> dict[str, Any]:
    return {"version": 1, "windows": {}, "recent_requests": []}


def _local_path() -> Path:
    root = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))
    return root / "operations" / f"{_DOCUMENT_ID}.json"


def _read_local() -> dict[str, Any]:
    path = _local_path()
    if not path.exists():
        return _empty_body()
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _request_key(user_id: str, request_id: str | None) -> str | None:
    if not request_id:
        return None
    return hashlib.sha256(f"{user_id}\0{request_id}".encode()).hexdigest()


def _updated_body(
    current: dict[str, Any],
    *,
    category: Literal["new_trip", "existing_trip_turn"],
    request_key: str | None,
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    recent = [str(value) for value in current.get("recent_requests") or []]
    if request_key and request_key in recent:
        return current, False

    windows = dict(current.get("windows") or {})
    prepared: dict[str, dict[str, Any]] = {}
    for window in ("daily", "weekly", "lifetime"):
        key = _window_key(window, now)
        stored = dict(windows.get(window) or {})
        counts = dict(stored.get("counts") or {}) if stored.get("key") == key else {}
        used = int(counts.get(category) or 0)
        limit = _limit(category, window)
        if limit > 0 and used >= limit:
            raise ConversationLimitError(
                category=category,
                window=window,
                used=used,
                limit=limit,
                resets_at=_resets_at(window, now),
            )
        prepared[window] = {"key": key, "counts": counts}

    for window, bucket in prepared.items():
        counts = dict(bucket["counts"])
        counts[category] = int(counts.get(category) or 0) + 1
        windows[window] = {"key": bucket["key"], "counts": counts}

    updated = dict(current)
    updated.update(
        {
            "version": 1,
            "windows": windows,
            "recent_requests": (
                recent + ([request_key] if request_key else [])
            )[-_MAX_RECENT_REQUESTS:],
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        }
    )
    return updated, True


def reserve(
    category: ConversationCategory,
    *,
    user_id: str,
    request_id: str | None,
    now: datetime | None = None,
) -> bool:
    if category == "continuation":
        return False
    now = (now or datetime.now(UTC)).astimezone(UTC)
    request_key = _request_key(user_id, request_id)

    if storage_cosmos.is_enabled():
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _CONTAINER, _PARTITION, _DOCUMENT_ID
            )
            body = dict(current.body) if current is not None else _empty_body()
            updated, changed = _updated_body(
                body,
                category=category,
                request_key=request_key,
                now=now,
            )
            if not changed:
                return False
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _CONTAINER, _PARTITION, _DOCUMENT_ID, updated
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _CONTAINER,
                        _PARTITION,
                        _DOCUMENT_ID,
                        updated,
                        current.version,
                    )
                return True
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        raise storage_cosmos.WriteConflictError("Conversation limit ledger kept changing")

    with _LOCAL_LOCK:
        body = _read_local()
        updated, changed = _updated_body(
            body,
            category=category,
            request_key=request_key,
            now=now,
        )
        if changed:
            atomic_write_json(_local_path(), updated, indent=2)
        return changed


def snapshot(now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if storage_cosmos.is_enabled():
        body = storage_cosmos.read_doc(_CONTAINER, _PARTITION, _DOCUMENT_ID) or {}
    else:
        with _LOCAL_LOCK:
            body = _read_local()
    stored_windows = dict(body.get("windows") or {})
    result: dict[str, Any] = {}
    for window in ("daily", "weekly", "lifetime"):
        key = _window_key(window, now)
        stored = dict(stored_windows.get(window) or {})
        counts = dict(stored.get("counts") or {}) if stored.get("key") == key else {}
        categories: dict[str, Any] = {}
        for category in ("new_trip", "existing_trip_turn"):
            used = int(counts.get(category) or 0)
            limit = _limit(category, window)
            categories[category] = {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used) if limit > 0 else None,
            }
        result[window] = {
            "key": key,
            "resets_at": _resets_at(window, now),
            "categories": categories,
        }
    return result
