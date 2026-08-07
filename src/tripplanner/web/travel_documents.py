"""Traveller document vault — extracted fields only, never the original file.

One typed store with one permission, retention, and deletion contract. Two
flows are exposed on top of it: ``traveler`` records (person-scoped, reused
across trips) and ``trip`` records (booking references, added in a later
stage). A visa is a *type* inside the traveller flow, not a separate store.

Two backends, auto-selected (mirrors ``chat_store``):
- **Cosmos DB** ``documents`` container, one doc per record, partitioned by
  ``/user_id`` (hosted mode).
- **Local JSON** at ``~/.tripplanner/documents.json`` otherwise (per-user
  subdirectory for non-``local`` identities).

Invariants this module is responsible for:
- No field outside :data:`FIELD_ALLOWLIST` is ever persisted, so extraction
  cannot smuggle unexpected personal data into storage.
- An identity number is reduced to its last four digits before it is written.
  The rest is never captured, so there is nothing to reveal, encrypt, or leak.
- No record can point at a file. There is no ``blob_path`` and no upload path.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from tripplanner import storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.user_context import get_user_id

_DOCS_FILE = Path.home() / ".tripplanner" / "documents.json"
_COSMOS_CONTAINER = "documents"
_LOCAL_LOCK = Lock()
_MAX_RECORDS_PER_USER = 120

DOCUMENT_TYPES = (
    "passport",
    "visa",
    "insurance",
    "vaccination",
    "licence",
    "idp",
    "loyalty",
)

TYPE_LABELS: dict[str, str] = {
    "passport": "Passport",
    "visa": "Visa",
    "insurance": "Travel insurance",
    "vaccination": "Vaccination certificate",
    "licence": "Driving licence",
    "idp": "International Driving Permit",
    "loyalty": "Loyalty programme",
}

_COMMON_FIELDS = {
    "holder_name",
    "issuing_country",
    "nationality",
    "number_last4",
    "date_of_birth",
    "expiry",
}

FIELD_ALLOWLIST: dict[str, set[str]] = {
    "passport": _COMMON_FIELDS,
    "visa": _COMMON_FIELDS
    | {"destination_country", "entry_type", "valid_from", "valid_to", "max_stay_days"},
    "insurance": {
        "holder_name",
        "provider",
        "policy_reference",
        "medical_cover_amount",
        "currency",
        "assistance_phone",
        "valid_from",
        "valid_to",
    },
    "vaccination": {"holder_name", "vaccine", "administered_on", "certificate_reference", "expiry"},
    "licence": _COMMON_FIELDS | {"categories"},
    "idp": _COMMON_FIELDS | {"linked_licence"},
    "loyalty": {"holder_name", "program", "membership_reference", "tier"},
}

# Fields whose entire value is the point of holding them. Everything else that
# looks like an identity number is reduced to its last four digits.
_WHOLE_VALUE_FIELDS = {
    "policy_reference",
    "membership_reference",
    "certificate_reference",
    "assistance_phone",
    "linked_licence",
}

_DATE_FIELDS = {"expiry", "date_of_birth", "valid_from", "valid_to", "administered_on"}
_INT_FIELDS = {"medical_cover_amount", "max_stay_days"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGITS = re.compile(r"[^0-9A-Za-z]")


class DocumentError(ValueError):
    """The submitted record cannot be stored as described."""


def traveller_key(relationship: str | None, name: str | None) -> str:
    """Stable key for a traveller, matching the ``family_members`` identity."""
    relation = str(relationship or "").strip().lower()
    person = str(name or "").strip().lower()
    if not person:
        return "self"
    return f"{relation}:{person}" if relation else person


def mask_identity_number(value: Any) -> str:
    """Reduce an identity number to its last four alphanumeric characters."""
    cleaned = _DIGITS.sub("", str(value or ""))
    return cleaned[-4:].upper() if cleaned else ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_date(value: Any) -> str:
    text = str(value or "").strip()
    return text if _ISO_DATE.match(text) else ""


def sanitize_fields(document_type: str, fields: Any) -> dict[str, Any]:
    """Keep only allowlisted fields, masked and normalised.

    Anything the caller sends that is not declared for this document type is
    dropped rather than stored, so an extraction that hallucinates a field
    cannot widen what the vault holds.
    """
    allowed = FIELD_ALLOWLIST.get(document_type)
    if allowed is None:
        raise DocumentError(f"Unknown document type: {document_type}")
    incoming = fields if isinstance(fields, dict) else {}
    clean: dict[str, Any] = {}
    for key, raw in incoming.items():
        name = str(key).strip().lower()
        if name in {"number", "document_number", "identity_number"}:
            name = "number_last4"
        if name not in allowed:
            continue
        if name == "number_last4":
            masked = mask_identity_number(raw)
            if masked:
                clean[name] = masked
            continue
        if name in _DATE_FIELDS:
            value = _clean_date(raw)
            if value:
                clean[name] = value
            continue
        if name in _INT_FIELDS:
            try:
                clean[name] = int(float(str(raw).replace(",", "").strip()))
            except (TypeError, ValueError):
                pass
            continue
        value = str(raw or "").strip()[:120]
        if value:
            clean[name] = value
    return clean


def _sanitize_provenance(provenance: Any) -> dict[str, Any]:
    incoming = provenance if isinstance(provenance, dict) else {}
    source = str(incoming.get("source_kind") or "manual").strip().lower()
    if source not in {"manual", "image", "text"}:
        source = "manual"
    try:
        confidence = round(float(incoming.get("confidence") or 0.0), 3)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "source_kind": source,
        "confidence": max(0.0, min(1.0, confidence)),
        "confirmed_by_user": bool(incoming.get("confirmed_by_user", True)),
        "captured_at": str(incoming.get("captured_at") or _now()),
    }


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return the storable shape of a caller-supplied record."""
    document_type = str(record.get("type") or "").strip().lower()
    if document_type not in DOCUMENT_TYPES:
        raise DocumentError(f"Unknown document type: {document_type or '(missing)'}")

    scope = str(record.get("scope") or "traveler").strip().lower()
    if scope not in {"traveler", "trip"}:
        raise DocumentError(f"Unknown scope: {scope}")

    fields = sanitize_fields(document_type, record.get("fields"))
    if not fields:
        raise DocumentError("Nothing usable was confirmed for this document.")

    now = _now()
    return {
        "id": str(record.get("id") or "").strip() or f"doc-{uuid.uuid4().hex[:12]}",
        "scope": scope,
        "type": document_type,
        "status": "ready",
        "traveller_key": str(record.get("traveller_key") or "self").strip().lower(),
        "traveller_name": str(record.get("traveller_name") or "").strip()[:80],
        "trip_id": str(record.get("trip_id") or "").strip() or None,
        "fields": fields,
        "provenance": _sanitize_provenance(record.get("provenance")),
        "created_at": str(record.get("created_at") or now),
        "updated_at": now,
    }


# ------------------------------------------------------------------ storage


def _local_path() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _DOCS_FILE
    return Path.home() / ".tripplanner" / "users" / uid / "documents.json"


def _read_local() -> list[dict[str, Any]]:
    path = _local_path()
    if not path.exists():
        return []
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = body.get("documents") if isinstance(body, dict) else body
    return [row for row in rows or [] if isinstance(row, dict)]


def _write_local(rows: list[dict[str, Any]]) -> None:
    atomic_write_json(_local_path(), {"documents": rows}, indent=2)


def list_documents(scope: str | None = "traveler") -> list[dict[str, Any]]:
    """Every stored record for the current user, newest first."""
    if storage_cosmos.is_enabled():
        rows = storage_cosmos.query_docs(_COSMOS_CONTAINER, get_user_id())
    else:
        rows = _read_local()
    if scope:
        rows = [row for row in rows if str(row.get("scope") or "traveler") == scope]
    return sorted(rows, key=lambda row: str(row.get("updated_at") or ""), reverse=True)


def save_document(record: dict[str, Any]) -> dict[str, Any]:
    """Persist one confirmed record; returns the stored shape."""
    stored = normalize_record(record)
    if storage_cosmos.is_enabled():
        existing = storage_cosmos.read_doc(_COSMOS_CONTAINER, get_user_id(), stored["id"])
        if existing is None and len(list_documents(None)) >= _MAX_RECORDS_PER_USER:
            raise DocumentError("This account already holds the maximum number of documents.")
        if isinstance(existing, dict) and existing.get("created_at"):
            stored["created_at"] = str(existing["created_at"])
        storage_cosmos.upsert_doc(_COSMOS_CONTAINER, get_user_id(), stored["id"], stored)
        return stored

    with _LOCAL_LOCK:
        rows = _read_local()
        for index, row in enumerate(rows):
            if row.get("id") == stored["id"]:
                stored["created_at"] = str(row.get("created_at") or stored["created_at"])
                rows[index] = stored
                break
        else:
            if len(rows) >= _MAX_RECORDS_PER_USER:
                raise DocumentError("This account already holds the maximum number of documents.")
            rows.append(stored)
        _write_local(rows)
    return stored


def delete_document(document_id: str) -> bool:
    """Delete one record. Returns whether anything was removed."""
    target = str(document_id or "").strip()
    if not target:
        return False
    if storage_cosmos.is_enabled():
        existing = storage_cosmos.read_doc(_COSMOS_CONTAINER, get_user_id(), target)
        if existing is None:
            return False
        storage_cosmos.delete_doc(_COSMOS_CONTAINER, get_user_id(), target)
        return True

    with _LOCAL_LOCK:
        rows = _read_local()
        remaining = [row for row in rows if row.get("id") != target]
        if len(remaining) == len(rows):
            return False
        _write_local(remaining)
    return True


def clear_all_documents() -> int:
    """Delete every record for the current user. Returns the count removed."""
    if storage_cosmos.is_enabled():
        return storage_cosmos.delete_docs(_COSMOS_CONTAINER, get_user_id())

    with _LOCAL_LOCK:
        rows = _read_local()
        if not rows:
            return 0
        _write_local([])
    return len(rows)
