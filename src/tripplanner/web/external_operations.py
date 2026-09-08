"""Durable idempotency records for outbound provider writes."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from tripplanner import storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.user_context import get_user_id

_CONTAINER = "users"
_DOC_ID = "external_operations"
_MAX_OPERATIONS = 80
_MAX_WRITE_ATTEMPTS = 3
_LOCAL_LOCKS: dict[str, Lock] = {}
_LOCAL_LOCKS_GUARD = Lock()


class IdempotencyConflictError(ValueError):
    """A request ID was reused for a different outbound operation."""


def request_key(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def payload_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def provider_operation_id(request_id: str) -> str:
    source = f"{get_user_id()}:{request_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source))


def _local_path() -> Path:
    user_id = get_user_id()
    if user_id == "local":
        return Path.home() / ".tripplanner" / f"{_DOC_ID}.json"
    return Path.home() / ".tripplanner" / "users" / user_id / f"{_DOC_ID}.json"


def _local_lock() -> Lock:
    key = str(_local_path())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, Lock())


def _read() -> dict[str, Any]:
    if storage_cosmos.is_enabled():
        return dict(storage_cosmos.read_doc(_CONTAINER, get_user_id(), _DOC_ID) or {})
    path = _local_path()
    if not path.exists():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {}


def _find(body: dict[str, Any], key: str) -> dict[str, Any] | None:
    for operation in reversed(body.get("operations") or []):
        if operation.get("key") == key:
            return dict(operation)
    return None


def get(request_id: str, fingerprint: str) -> dict[str, Any] | None:
    operation = _find(_read(), request_key(request_id))
    if operation and operation.get("fingerprint") != fingerprint:
        raise IdempotencyConflictError("request_id was already used for different email content")
    return operation


def _updated_body(
    body: dict[str, Any], key: str, fingerprint: str, values: dict[str, Any]
) -> dict[str, Any]:
    operations = [
        dict(operation)
        for operation in body.get("operations") or []
        if operation.get("key") != key
    ]
    operations.append({"key": key, "fingerprint": fingerprint, **values})
    return {"operations": operations[-_MAX_OPERATIONS:]}


def _mutate(
    request_id: str, fingerprint: str, values: dict[str, Any]
) -> dict[str, Any]:
    key = request_key(request_id)
    if not storage_cosmos.is_enabled():
        with _local_lock():
            body = _read()
            existing = _find(body, key)
            if existing and existing.get("fingerprint") != fingerprint:
                raise IdempotencyConflictError(
                    "request_id was already used for different email content"
                )
            updated = _updated_body(body, key, fingerprint, values)
            atomic_write_json(_local_path(), updated)
            return dict(_find(updated, key) or {})

    for _ in range(_MAX_WRITE_ATTEMPTS):
        versioned = storage_cosmos.read_doc_versioned(
            _CONTAINER, get_user_id(), _DOC_ID
        )
        body = dict(versioned.body if versioned else {})
        existing = _find(body, key)
        if existing and existing.get("fingerprint") != fingerprint:
            raise IdempotencyConflictError(
                "request_id was already used for different email content"
            )
        updated = _updated_body(body, key, fingerprint, values)
        try:
            if versioned:
                storage_cosmos.replace_doc_if_version(
                    _CONTAINER,
                    get_user_id(),
                    _DOC_ID,
                    updated,
                    versioned.version,
                )
            else:
                storage_cosmos.create_doc_if_absent(
                    _CONTAINER, get_user_id(), _DOC_ID, updated
                )
            return dict(_find(updated, key) or {})
        except storage_cosmos.WriteConflictError:
            continue
    raise storage_cosmos.WriteConflictError("external operation conflicts exhausted")


def claim_pending(
    request_id: str, fingerprint: str, *, provider: str
) -> tuple[dict[str, Any], bool]:
    """Claim a new provider write; return the existing record when already claimed."""
    key = request_key(request_id)
    if not storage_cosmos.is_enabled():
        with _local_lock():
            body = _read()
            existing = _find(body, key)
            if existing:
                if existing.get("fingerprint") != fingerprint:
                    raise IdempotencyConflictError(
                        "request_id was already used for different email content"
                    )
                return existing, False
            updated = _updated_body(
                body,
                key,
                fingerprint,
                {"status": "pending", "provider": provider},
            )
            atomic_write_json(_local_path(), updated)
            return dict(_find(updated, key) or {}), True

    for _ in range(_MAX_WRITE_ATTEMPTS):
        versioned = storage_cosmos.read_doc_versioned(
            _CONTAINER, get_user_id(), _DOC_ID
        )
        body = dict(versioned.body if versioned else {})
        existing = _find(body, key)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise IdempotencyConflictError(
                    "request_id was already used for different email content"
                )
            return existing, False
        updated = _updated_body(
            body,
            key,
            fingerprint,
            {"status": "pending", "provider": provider},
        )
        try:
            if versioned:
                storage_cosmos.replace_doc_if_version(
                    _CONTAINER,
                    get_user_id(),
                    _DOC_ID,
                    updated,
                    versioned.version,
                )
            else:
                storage_cosmos.create_doc_if_absent(
                    _CONTAINER, get_user_id(), _DOC_ID, updated
                )
            return dict(_find(updated, key) or {}), True
        except storage_cosmos.WriteConflictError:
            continue
    raise storage_cosmos.WriteConflictError("external operation conflicts exhausted")


def record_completed(
    request_id: str,
    fingerprint: str,
    *,
    provider: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    return _mutate(
        request_id,
        fingerprint,
        {"status": "completed", "provider": provider, "result": result},
    )
