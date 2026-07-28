"""Per-trip chat transcript persistence (frontend-agnostic).

The visible conversation + itinerary summary must survive a browser refresh and
follow saved-trip switches (Mumbai chat vs. Vietnam chat). We persist the clean
Human/AI text turns — the same list the API keeps as the agent's LLM context —
so a reload yields valid context and an identical transcript.

Two backends, auto-selected (mirrors ``trip_planner``):
- **Cosmos DB** ``users`` container, docs ``chat_<trip_id>`` and
    ``chat_operations`` (hosted mode)
- **Local JSON** matching files under ``~/.tripplanner/chats/`` otherwise
    (per-user subdir for non-``local`` identities)

A conversation that happens before any trip exists lives in the ``_general``
bucket; once a trip is created it is migrated into that trip's bucket. The
principal-scoped operation index retains the latest 80 completed requests so a
retry still replays after the active trip changes or a guest identity is adopted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.user_context import get_user_id

_CHATS_DIR = Path.home() / ".tripplanner" / "chats"
_COSMOS_USERS_CONTAINER = "users"
_GENERAL = "_general"
_OPERATIONS_DOC_ID = "chat_operations"
_MAX_TURNS = 80  # keep the persisted transcript bounded
_MAX_RECENT_WRITES = 80
_MAX_RECENT_OPERATIONS = 80
_MAX_WRITE_ATTEMPTS = 3
_LOCAL_LOCKS: dict[str, Lock] = {}
_LOCAL_LOCKS_GUARD = Lock()


def _doc_id(trip_id: str | None) -> str:
    return f"chat_{trip_id or _GENERAL}"


def _resolve_dir() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _CHATS_DIR
    return Path.home() / ".tripplanner" / "users" / uid / "chats"


def _serialize(messages: list[BaseMessage], *, bounded: bool = True) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in messages:
        mtype = getattr(m, "type", "")
        role = "user" if mtype == "human" else "assistant" if mtype == "ai" else None
        if role is None:
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        if not text.strip():
            continue
        rows.append({"role": role, "text": text})
    return rows[-_MAX_TURNS:] if bounded else rows


def _deserialize(rows: list[dict[str, Any]]) -> list[BaseMessage]:
    msgs: list[BaseMessage] = []
    for r in rows:
        text = str(r.get("text") or "")
        if not text.strip():
            continue
        if r.get("role") == "user":
            msgs.append(HumanMessage(content=text))
        else:
            msgs.append(AIMessage(content=text))
    return msgs


def _read_body(trip_id: str | None) -> dict[str, Any]:
    if storage_cosmos.is_enabled():
        doc = storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _doc_id(trip_id)
        )
        return dict(doc or {})
    path = _resolve_dir() / f"{_doc_id(trip_id)}.json"
    if path.exists():
        try:
            return dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _read_rows(trip_id: str | None) -> list[dict[str, Any]]:
    return list(_read_body(trip_id).get("messages") or [])


def _read_operations_body() -> dict[str, Any]:
    if storage_cosmos.is_enabled():
        doc = storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _OPERATIONS_DOC_ID
        )
        return dict(doc or {})
    path = _resolve_dir() / f"{_OPERATIONS_DOC_ID}.json"
    if path.exists():
        try:
            return dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def load(trip_id: str | None) -> list[BaseMessage]:
    """LangChain message history for a trip's conversation (for the agent)."""
    return _deserialize(_read_rows(trip_id))


def load_for_request(
    trip_id: str | None, request_id: str | None
) -> list[BaseMessage]:
    """Load history without an interrupted attempt of the operation being retried."""
    if not request_id:
        return load(trip_id)
    request_key = _request_key(request_id)
    return _deserialize(
        [row for row in _read_rows(trip_id) if row.get("request_key") != request_key]
    )


def _operation_result(body: dict[str, Any], request_key: str) -> dict[str, str] | None:
    for operation in reversed(body.get("recent_operations") or []):
        if operation.get("key") == request_key and operation.get("status") == "completed":
            return {
                "reply": str(operation.get("reply") or ""),
                "agent": str(operation.get("agent") or "trip"),
                "trip_id": str(operation.get("trip_id") or ""),
                "message": str(operation.get("message") or ""),
            }
    return None


def completed_request(request_id: str | None) -> dict[str, str] | None:
    """Return a completed operation independently of the active trip bucket."""
    if not request_id:
        return None
    request_key = _request_key(request_id)
    return _operation_result(_read_operations_body(), request_key)


def completed_operation(
    trip_id: str | None, request_id: str | None
) -> dict[str, str] | None:
    if not request_id:
        return None
    request_key = _request_key(request_id)
    return completed_request(request_id) or _operation_result(
        _read_body(trip_id), request_key
    )


def transcript(trip_id: str | None) -> list[dict[str, str]]:
    """The display transcript ([{role, text}]) for the SPA to re-render."""
    return [
        {"role": str(r.get("role") or "assistant"), "text": str(r.get("text") or "")}
        for r in _read_rows(trip_id)
        if str(r.get("text") or "").strip()
    ]


def _longest_common_block(
    current: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> tuple[int, int]:
    """Return the incoming start and length of the longest contiguous overlap."""
    best_start = 0
    best_length = 0
    for current_start in range(len(current)):
        for incoming_start in range(len(incoming)):
            length = 0
            while (
                current_start + length < len(current)
                and incoming_start + length < len(incoming)
                and current[current_start + length] == incoming[incoming_start + length]
            ):
                length += 1
            if length > best_length:
                best_start = incoming_start
                best_length = length
    return best_start, best_length


def _write_key(
    trip_id: str | None,
    base_rows: list[dict[str, Any]],
    suffix_rows: list[dict[str, Any]],
    request_id: str | None = None,
) -> str:
    if request_id:
        return _request_key(request_id)
    payload = json.dumps(
        {
            "trip_id": trip_id or _GENERAL,
            "base": base_rows,
            "suffix": suffix_rows,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_key(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _completed_operation_entry(
    request_key: str,
    suffix_rows: list[dict[str, Any]],
    agent: str,
    trip_id: str | None,
) -> dict[str, str]:
    reply = next(
        (
            str(row.get("text") or "")
            for row in reversed(suffix_rows)
            if row.get("role") == "assistant"
        ),
        "",
    )
    message = next(
        (
            str(row.get("text") or "")
            for row in suffix_rows
            if row.get("role") == "user"
        ),
        "",
    )
    return {
        "key": request_key,
        "status": "completed",
        "reply": reply,
        "agent": agent,
        "trip_id": trip_id or "",
        "message": message,
    }


def _merge_operation_index(
    current: dict[str, Any], operation: dict[str, str]
) -> dict[str, Any] | None:
    operations = list(current.get("recent_operations") or [])
    for index, existing in enumerate(operations):
        if existing.get("key") != operation["key"]:
            continue
        if (
            not existing.get("trip_id")
            and operation.get("trip_id")
            and str(existing.get("reply") or "") == operation.get("reply")
        ):
            operations[index] = {
                **existing,
                **operation,
                "message": operation.get("message") or existing.get("message") or "",
            }
            updated = dict(current)
            updated["recent_operations"] = operations[-_MAX_RECENT_OPERATIONS:]
            return updated
        return None
    updated = dict(current)
    updated["recent_operations"] = (operations + [operation])[-_MAX_RECENT_OPERATIONS:]
    return updated


def _record_completed_operation(operation: dict[str, str]) -> None:
    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _COSMOS_USERS_CONTAINER, user_id, _OPERATIONS_DOC_ID
            )
            body = current.body if current is not None else {}
            updated = _merge_operation_index(body, operation)
            if updated is None:
                return
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _COSMOS_USERS_CONTAINER, user_id, _OPERATIONS_DOC_ID, updated
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _COSMOS_USERS_CONTAINER,
                        user_id,
                        _OPERATIONS_DOC_ID,
                        updated,
                        current.version,
                    )
                return
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        return

    path = _resolve_dir() / f"{_OPERATIONS_DOC_ID}.json"
    with _local_lock(path):
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (json.JSONDecodeError, OSError):
            current = {}
        updated = _merge_operation_index(dict(current), operation)
        if updated is not None:
            atomic_write_json(path, updated, indent=2)


def ensure_completed_turn(request_id: str, operation: dict[str, str]) -> None:
    """Repair a transcript after the principal operation index was saved first."""
    target = operation.get("trip_id") or None
    turn = _serialize(
        [
            HumanMessage(content=operation.get("message") or ""),
            AIMessage(content=operation["reply"]),
        ],
        bounded=False,
    )
    _append_rows(
        target,
        [],
        turn,
        request_id=request_id,
        completed=True,
        agent=operation.get("agent") or "trip",
    )


def _remove_completed_operations(trip_id: str | None) -> None:
    target = trip_id or ""
    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _COSMOS_USERS_CONTAINER, user_id, _OPERATIONS_DOC_ID
            )
            if current is None:
                return
            operations = [
                operation
                for operation in current.body.get("recent_operations") or []
                if str(operation.get("trip_id") or "") != target
            ]
            if operations == list(current.body.get("recent_operations") or []):
                return
            updated = dict(current.body)
            updated["recent_operations"] = operations
            try:
                storage_cosmos.replace_doc_if_version(
                    _COSMOS_USERS_CONTAINER,
                    user_id,
                    _OPERATIONS_DOC_ID,
                    updated,
                    current.version,
                )
                return
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        return

    path = _resolve_dir() / f"{_OPERATIONS_DOC_ID}.json"
    with _local_lock(path):
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (json.JSONDecodeError, OSError):
            return
        operations = [
            operation
            for operation in current.get("recent_operations") or []
            if str(operation.get("trip_id") or "") != target
        ]
        if operations != list(current.get("recent_operations") or []):
            updated = dict(current)
            updated["recent_operations"] = operations
            atomic_write_json(path, updated, indent=2)


def _merge_body(
    current: dict[str, Any],
    suffix_rows: list[dict[str, Any]],
    write_key: str,
    *,
    request_key: str | None = None,
    completed: bool = True,
    agent: str = "trip",
    trip_id: str | None = None,
) -> dict[str, Any] | None:
    writes = [str(value) for value in current.get("recent_writes") or []]
    operations = list(current.get("recent_operations") or [])
    existing_operation = next(
        (operation for operation in operations if operation.get("key") == request_key),
        None,
    )
    if (
        not suffix_rows
        or write_key in writes
        or (existing_operation and existing_operation.get("status") == "completed")
    ):
        return None
    rows = list(current.get("messages") or [])
    if request_key:
        rows = [row for row in rows if row.get("request_key") != request_key]
        operations = [operation for operation in operations if operation.get("key") != request_key]
    if request_key and not completed:
        suffix_rows = [
            {**row, "request_key": request_key, "interrupted": True}
            for row in suffix_rows
        ]
    rows.extend(suffix_rows)
    updated = dict(current)
    updated["messages"] = rows[-_MAX_TURNS:]
    if request_key:
        reply = next(
            (
                str(row.get("text") or "")
                for row in reversed(suffix_rows)
                if row.get("role") == "assistant"
            ),
            "",
        )
        message = next(
            (
                str(row.get("text") or "")
                for row in suffix_rows
                if row.get("role") == "user"
            ),
            "",
        )
        operations.append(
            {
                "key": request_key,
                "status": "completed" if completed else "interrupted",
                "reply": reply,
                "agent": agent,
                "trip_id": trip_id or "",
                "message": message,
            }
        )
        updated["recent_operations"] = operations[-_MAX_RECENT_OPERATIONS:]
    if completed:
        updated["recent_writes"] = (writes + [write_key])[-_MAX_RECENT_WRITES:]
    return updated


def _merge_migrated_body(
    current: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any] | None:
    current_rows = list(current.get("messages") or [])
    source_rows = list(source.get("messages") or [])
    row_counts = [
        [0] * (len(source_rows) + 1) for _ in range(len(current_rows) + 1)
    ]
    for current_index in range(len(current_rows) - 1, -1, -1):
        for source_index in range(len(source_rows) - 1, -1, -1):
            if current_rows[current_index] == source_rows[source_index]:
                row_counts[current_index][source_index] = (
                    row_counts[current_index + 1][source_index + 1] + 1
                )
            else:
                row_counts[current_index][source_index] = max(
                    row_counts[current_index + 1][source_index],
                    row_counts[current_index][source_index + 1],
                )

    merged_rows: list[dict[str, Any]] = []
    current_index = 0
    source_index = 0
    while current_index < len(current_rows) and source_index < len(source_rows):
        if current_rows[current_index] == source_rows[source_index]:
            merged_rows.append(current_rows[current_index])
            current_index += 1
            source_index += 1
        elif (
            row_counts[current_index + 1][source_index]
            >= row_counts[current_index][source_index + 1]
        ):
            merged_rows.append(current_rows[current_index])
            current_index += 1
        else:
            merged_rows.append(source_rows[source_index])
            source_index += 1
    merged_rows.extend(current_rows[current_index:])
    merged_rows.extend(source_rows[source_index:])

    writes = [str(value) for value in current.get("recent_writes") or []]
    writes.extend(
        value
        for value in (str(item) for item in source.get("recent_writes") or [])
        if value not in writes
    )
    operations = list(current.get("recent_operations") or [])
    operation_keys = {str(operation.get("key") or "") for operation in operations}
    operations.extend(
        operation
        for operation in source.get("recent_operations") or []
        if str(operation.get("key") or "") not in operation_keys
    )
    if (
        merged_rows == current_rows
        and writes == list(current.get("recent_writes") or [])
        and operations == list(current.get("recent_operations") or [])
    ):
        return None
    updated = dict(current)
    updated["messages"] = merged_rows[-_MAX_TURNS:]
    updated["recent_writes"] = writes[-_MAX_RECENT_WRITES:]
    updated["recent_operations"] = operations[-_MAX_RECENT_OPERATIONS:]
    return updated


def _local_lock(path: Path) -> Lock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, Lock())


def _append_rows(
    trip_id: str | None,
    base_rows: list[dict[str, Any]],
    suffix_rows: list[dict[str, Any]],
    *,
    request_id: str | None = None,
    completed: bool = True,
    agent: str = "trip",
) -> None:
    write_key = _write_key(trip_id, base_rows, suffix_rows, request_id)
    request_key = _request_key(request_id) if request_id else None
    completed_operation_entry = (
        _completed_operation_entry(request_key, suffix_rows, agent, trip_id)
        if request_key and completed
        else None
    )
    if completed_operation_entry is not None:
        _record_completed_operation(completed_operation_entry)
    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        doc_id = _doc_id(trip_id)
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _COSMOS_USERS_CONTAINER, user_id, doc_id
            )
            body = current.body if current is not None else {}
            updated = _merge_body(
                body,
                suffix_rows,
                write_key,
                request_key=request_key,
                completed=completed,
                agent=agent,
                trip_id=trip_id,
            )
            if updated is None:
                existing = _operation_result(body, request_key) if request_key else None
                if existing is not None:
                    _record_completed_operation(
                        {
                            "key": str(request_key),
                            "status": "completed",
                            **existing,
                        }
                    )
                return
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _COSMOS_USERS_CONTAINER, user_id, doc_id, updated
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _COSMOS_USERS_CONTAINER,
                        user_id,
                        doc_id,
                        updated,
                        current.version,
                    )
                return
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        return

    path = _resolve_dir() / f"{_doc_id(trip_id)}.json"
    with _local_lock(path):
        current_body = _read_body(trip_id)
        updated = _merge_body(
            current_body,
            suffix_rows,
            write_key,
            request_key=request_key,
            completed=completed,
            agent=agent,
            trip_id=trip_id,
        )
        if updated is not None:
            atomic_write_json(path, updated, indent=2)
        elif request_key:
            existing = _operation_result(current_body, request_key)
            if existing is not None:
                _record_completed_operation(
                    {
                        "key": request_key,
                        "status": "completed",
                        **existing,
                    }
                )


def _associate_migrated_operations(
    source: dict[str, Any], trip_id: str | None
) -> None:
    for operation in source.get("recent_operations") or []:
        if operation.get("status") != "completed" or not operation.get("key"):
            continue
        _record_completed_operation(
            {
                "key": str(operation["key"]),
                "status": "completed",
                "reply": str(operation.get("reply") or ""),
                "agent": str(operation.get("agent") or "trip"),
                "trip_id": trip_id or "",
                "message": str(operation.get("message") or ""),
            }
        )


def _merge_migrated_document(
    trip_id: str | None,
    source: dict[str, Any],
    *,
    associate_operations: bool = True,
) -> None:
    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        doc_id = _doc_id(trip_id)
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _COSMOS_USERS_CONTAINER, user_id, doc_id
            )
            body = current.body if current is not None else {}
            updated = _merge_migrated_body(body, source)
            if updated is None:
                if associate_operations:
                    _associate_migrated_operations(source, trip_id)
                return
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _COSMOS_USERS_CONTAINER, user_id, doc_id, updated
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _COSMOS_USERS_CONTAINER, user_id, doc_id, updated, current.version
                    )
                if associate_operations:
                    _associate_migrated_operations(source, trip_id)
                return
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        return

    path = _resolve_dir() / f"{_doc_id(trip_id)}.json"
    with _local_lock(path):
        updated = _merge_migrated_body(_read_body(trip_id), source)
        if updated is not None:
            atomic_write_json(path, updated, indent=2)
        if associate_operations:
            _associate_migrated_operations(source, trip_id)


def export_state(trip_ids: list[str]) -> dict[str, Any]:
    """Snapshot known chat buckets and replay metadata for identity adoption."""
    buckets: dict[str, dict[str, Any]] = {}
    for trip_id in [None, *dict.fromkeys(trip_ids)]:
        body = _read_body(trip_id)
        if body:
            buckets[trip_id or _GENERAL] = body
    return {"buckets": buckets, "operations": _read_operations_body()}


def adopt_state(state: dict[str, Any]) -> bool:
    """Merge another principal's chat state without replacing existing chats."""
    copied = False
    for bucket, source in (state.get("buckets") or {}).items():
        if not isinstance(source, dict) or not source:
            continue
        trip_id = None if bucket == _GENERAL else str(bucket)
        _merge_migrated_document(
            trip_id,
            source,
            associate_operations=False,
        )
        copied = True
    for operation in (state.get("operations") or {}).get("recent_operations") or []:
        if not isinstance(operation, dict) or operation.get("status") != "completed":
            continue
        _record_completed_operation(
            {str(key): str(value or "") for key, value in operation.items()}
        )
        copied = True
    return copied


def reconcile_general(trip_id: str | None) -> None:
    """Finish an interrupted first-trip move when both buckets still exist."""
    if not trip_id:
        return
    if storage_cosmos.is_enabled():
        user_id = get_user_id()
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            source = storage_cosmos.read_doc_versioned(
                _COSMOS_USERS_CONTAINER, user_id, _doc_id(None)
            )
            if source is None:
                return
            if source.body:
                _merge_migrated_document(trip_id, source.body)
            try:
                storage_cosmos.delete_doc_if_version(
                    _COSMOS_USERS_CONTAINER,
                    user_id,
                    _doc_id(None),
                    source.version,
                )
                return
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise
        return

    source_path = _resolve_dir() / f"{_doc_id(None)}.json"
    with _local_lock(source_path):
        source_body = _read_body(None)
        if source_body:
            _merge_migrated_document(trip_id, source_body)
            source_path.unlink(missing_ok=True)


def save(trip_id: str | None, messages: list[BaseMessage]) -> None:
    """Merge a complete history snapshot without truncating concurrent suffixes."""
    incoming = _serialize(messages, bounded=False)
    current = _read_rows(trip_id)
    incoming_start, overlap = _longest_common_block(current, incoming)
    matched_end = incoming_start + overlap
    if overlap and matched_end == len(incoming):
        return
    base_rows = incoming[:matched_end]
    suffix_rows = incoming[matched_end:]
    _append_rows(trip_id, base_rows, suffix_rows)


def persist_turn(
    tid_before: str | None,
    tid_after: str | None,
    base_history: list[BaseMessage],
    completed_turn: list[BaseMessage],
    carryover_text: str = "",
    *,
    request_id: str | None = None,
    completed: bool = True,
    agent: str = "trip",
) -> str | None:
    """Persist one chat turn, handling a mid-chat destination switch.

    ``base_history`` is the transcript loaded before the turn and
    ``completed_turn`` is the exact Human/AI suffix produced by this request.
    Returns the bucket id actually written.

    Cases:
    - **No trip change** (``tid_after == tid_before``) or no trip yet: save the
      whole ``history`` under the active bucket — the existing behaviour.
    - **First trip created** (``tid_before is None`` → real id): migrate the whole
      pre-trip conversation into the new trip's bucket and clear ``_general``.
    - **Destination switch** between two real trips (Mexico → Kashmir): the prior
      trip's bucket already holds everything up to this turn, so leave it intact.
      The new trip gets ONLY this turn (the switch Human + AI), optionally seeded
      with a visible ``carryover_text`` note at the top when it's a brand-new
      bucket. Resuming an already-chatted trip just appends this turn to it.
    """
    base_rows = _serialize(base_history, bounded=False)
    turn_rows = _serialize(completed_turn, bounded=False)
    if tid_after is None or tid_after == tid_before:
        target = tid_after if tid_after is not None else tid_before
        _append_rows(
            target,
            base_rows,
            turn_rows,
            request_id=request_id,
            completed=completed,
            agent=agent,
        )
        return target

    if tid_before is None:
        if storage_cosmos.is_enabled():
            user_id = get_user_id()
            for attempt in range(_MAX_WRITE_ATTEMPTS):
                source = storage_cosmos.read_doc_versioned(
                    _COSMOS_USERS_CONTAINER, user_id, _doc_id(None)
                )
                if source is None:
                    break
                if source.body:
                    _merge_migrated_document(tid_after, source.body)
                _append_rows(
                    tid_after,
                    base_rows,
                    turn_rows,
                    request_id=request_id,
                    completed=completed,
                    agent=agent,
                )
                try:
                    storage_cosmos.delete_doc_if_version(
                        _COSMOS_USERS_CONTAINER,
                        user_id,
                        _doc_id(None),
                        source.version,
                    )
                except storage_cosmos.WriteConflictError:
                    if attempt == _MAX_WRITE_ATTEMPTS - 1:
                        raise
                    continue
                break
            else:
                raise storage_cosmos.WriteConflictError(
                    "Chat migration source kept changing"
                )
            if source is None:
                _append_rows(
                    tid_after,
                    base_rows,
                    turn_rows,
                    request_id=request_id,
                    completed=completed,
                    agent=agent,
                )
            return tid_after

        source_path = _resolve_dir() / f"{_doc_id(None)}.json"
        with _local_lock(source_path):
            source_body = _read_body(None)
            if source_body:
                _merge_migrated_document(tid_after, source_body)
            _append_rows(
                tid_after,
                base_rows,
                turn_rows,
                request_id=request_id,
                completed=completed,
                agent=agent,
            )
            source_path.unlink(missing_ok=True)
        return tid_after

    # Switch between two distinct, real trips.
    existing_new = _read_rows(tid_after)
    if existing_new:
        _append_rows(
            tid_after,
            base_rows,
            turn_rows,
            request_id=request_id,
            completed=completed,
            agent=agent,
        )
    else:
        suffix: list[BaseMessage] = []
        if carryover_text.strip():
            suffix.append(AIMessage(content=carryover_text.strip()))
        suffix.extend(completed_turn)
        _append_rows(
            tid_after,
            base_rows,
            _serialize(suffix, bounded=False),
            request_id=request_id,
            completed=completed,
            agent=agent,
        )
    return tid_after


def clear(trip_id: str | None) -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _doc_id(trip_id)
        )
        _remove_completed_operations(trip_id)
        return
    (_resolve_dir() / f"{_doc_id(trip_id)}.json").unlink(missing_ok=True)
    _remove_completed_operations(trip_id)


def clear_all() -> int:
    """Delete every persisted chat transcript for the current user."""
    if storage_cosmos.is_enabled():
        return storage_cosmos.delete_docs(
            _COSMOS_USERS_CONTAINER,
            get_user_id(),
            id_prefix="chat_",
        )

    deleted = 0
    d = _resolve_dir()
    if not d.exists():
        return 0
    for path in d.glob("chat_*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted

