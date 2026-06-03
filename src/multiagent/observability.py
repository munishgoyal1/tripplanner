"""Structured logging + PII-safe app events + restricted audit log.

The app keeps **two distinct log streams**:

1. APP LOG (stdout, queryable in Log Analytics / Kusto)
   - Everything emitted via the standard ``logging`` module.
   - A PII redaction filter scrubs emails, phones, IPs, bearer tokens, and
     known-secret patterns from the message text.
   - Structured events should use :func:`app_event`. Field names listed in
     :data:`_SENSITIVE_FIELDS` are replaced with ``"<redacted>"`` BEFORE the
     event ever hits stdout, even if the caller passes them.
   - User identifiers are hashed via :func:`hash_user_id` so traces can still
     be correlated without storing the raw identifier in the app log.

2. AUDIT LOG (restricted sink, NOT visible on stdout)
   - Raw, un-redacted records written via :func:`audit_event`.
   - Hosted: a separate Cosmos container ``audit_events`` (write-only path
     from the app; reads are out-of-band via Azure Portal / ``az cosmosdb``).
   - Local: ``~/.multiagent/audit/<YYYY-MM-DD>.jsonl``.
   - Never echoed to stdout, never returned to a user-facing response.

The split lets us query app behavior (RPS, error kinds, tool latencies,
unique users by hash) in Log Analytics without exposing personal data, while
keeping a separate restricted store for the rare investigation that needs
the raw text.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import re
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PII patterns and sensitive field names
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d \-]{7,}\d")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CREDIT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)
# Catches `api_key=abc...`, `secret: abc...`, `password="abc..."` patterns.
_KEYVAL_SECRET_RE = re.compile(
    r"(api[_-]?key|secret|password|token|authorization)"
    r"(\s*[:=]\s*['\"]?)([A-Za-z0-9._\-]{16,})",
    re.IGNORECASE,
)

# Fields whose VALUE is replaced with "<redacted>" before structured events
# are written to the app log. The audit log gets the original value.
# Match is case-insensitive on the exact field name (not a substring) so
# benign keys like "username" or "displayed_name" aren't wiped.
_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "address",
        "answer",
        "card_number",
        "content",
        "credit_card",
        "destination",
        "display_name",
        "dob",
        "email",
        "first_name",
        "full_name",
        "iban",
        "last_name",
        "message",
        "name",
        "origin",
        "passport",
        "phone",
        "query",
        "ssn",
        "text",
        "user_message",
    }
)


def redact_text(s: Any) -> Any:
    """Replace email/phone/IP/secret patterns in a string with placeholders.

    Non-string values are returned unchanged. Safe to call on log messages
    that may already contain redacted placeholders (idempotent enough).
    """
    if not isinstance(s, str):
        return s
    out = _EMAIL_RE.sub("<email>", s)
    out = _BEARER_RE.sub("Bearer <token>", out)
    out = _KEYVAL_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", out)
    out = _CREDIT_RE.sub("<card>", out)
    out = _PHONE_RE.sub("<phone>", out)
    out = _IPV4_RE.sub("<ip>", out)
    return out


def redact_value(v: Any) -> Any:
    """Recursively redact strings inside dicts/lists. Field-name wipe is NOT
    applied here -- only inside :func:`app_event`. Use this when you want
    "scrub the obvious PII patterns from arbitrary nested data"."""
    if isinstance(v, str):
        return redact_text(v)
    if isinstance(v, dict):
        return {k: redact_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [redact_value(x) for x in v]
    if isinstance(v, tuple):
        return tuple(redact_value(x) for x in v)
    return v


def hash_user_id(user_id: str | None) -> str:
    """Return a stable, irreversible 12-char hash of ``user_id`` for the app log.

    Same input always produces the same output (so we can count uniques and
    follow a user's session across log entries) but the raw identifier --
    including OAuth subject ids and guest UUIDs -- never appears in stdout.
    """
    if not user_id:
        return "anon"
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"u_{digest[:12]}"


# ---------------------------------------------------------------------------
# logging.Filter / Formatter
# ---------------------------------------------------------------------------


class PiiRedactingFilter(logging.Filter):
    """Apply :func:`redact_text` to the formatted message and to scalar args.

    Runs BEFORE the formatter so JSON output already contains the scrubbed
    text. We deliberately mutate ``record.msg`` and ``record.args`` because
    formatters re-resolve ``%`` arguments at format time -- patching only
    ``record.message`` would not survive ``%`` interpolation.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact_value(v) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(redact_value(a) for a in record.args)
                else:
                    record.args = redact_value(record.args)
        except Exception:  # never block a log line because the filter blew up
            pass
        return True


_RESERVED_LOGRECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Compact JSON formatter. Includes ``extra=`` fields, hashes any
    ``user_id`` extra, and scrubs PII from string values."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        base: dict[str, Any] = {
            "ts": _dt.datetime.fromtimestamp(record.created, _dt.timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Pull any structured fields the caller passed via extra=
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key.startswith("_"):
                continue
            if key == "user_id":
                base["user"] = hash_user_id(str(value) if value else None)
                continue
            if key.lower() in _SENSITIVE_FIELDS:
                base[key] = "<redacted>"
            else:
                base[key] = redact_value(value)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str, ensure_ascii=False)


class _TextFormatterWithPid(logging.Formatter):
    """Slightly richer than the default text formatter -- prepends a short
    logger name and the level. Used in local dev mode."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        ts = _dt.datetime.fromtimestamp(record.created, _dt.timezone.utc).strftime("%H:%M:%S")
        return f"{ts} {record.levelname:<5} {record.name}: {record.getMessage()}"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_SETUP_LOCK = threading.Lock()
_SETUP_DONE = False


def _is_hosted() -> bool:
    """True when we're running on a server (Container Apps, etc.)."""
    return bool(os.environ.get("COSMOS_ENDPOINT") or os.environ.get("CONTAINER_APP_NAME"))


def setup_logging(force: bool = False) -> None:
    """Install the PII filter + chosen formatter on the root logger.

    Called once at process start by every entrypoint (api.py, cli.py,
    web/app.py). Subsequent calls are no-ops unless ``force=True`` (used by
    tests).

    Environment knobs:
      - ``LOG_LEVEL``  (default ``INFO``)
      - ``LOG_JSON``   (``1`` / ``0``; auto-on when ``_is_hosted()``)
    """
    global _SETUP_DONE
    with _SETUP_LOCK:
        if _SETUP_DONE and not force:
            return
        level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        json_env = os.environ.get("LOG_JSON")
        if json_env is None:
            use_json = _is_hosted()
        else:
            use_json = json_env.lower() in ("1", "true", "yes", "on")

        root = logging.getLogger()
        # Reset existing handlers so reconfigures (e.g. tests) take effect.
        for h in list(root.handlers):
            root.removeHandler(h)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.addFilter(PiiRedactingFilter())
        handler.setFormatter(JsonFormatter() if use_json else _TextFormatterWithPid())
        root.addHandler(handler)
        root.setLevel(level)

        # Quiet some noisy third-party loggers in normal mode.
        for noisy in ("azure", "httpx", "httpcore", "urllib3", "openai"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _SETUP_DONE = True


# ---------------------------------------------------------------------------
# Structured event helpers
# ---------------------------------------------------------------------------

_APP_EVENT_LOGGER = logging.getLogger("multiagent.event")


def app_event(kind: str, user_id: str | None = None, **fields: Any) -> None:
    """Emit a structured, PII-safe event to the APP log (stdout).

    Field names that appear in :data:`_SENSITIVE_FIELDS` are dropped --
    replaced with ``"<redacted>"`` -- before the event is written. The
    ``user_id`` is hashed via :func:`hash_user_id`. Free-form string values
    are scrubbed for emails, phones, secrets, etc.

    Example::

        app_event("tool_call", user_id, tool="search_flights_duffel",
                  status="ok", ms=842)
    """
    safe: dict[str, Any] = {}
    for k, v in fields.items():
        if k.lower() in _SENSITIVE_FIELDS:
            safe[k] = "<redacted>"
        else:
            safe[k] = redact_value(v)
    safe["user_id"] = user_id  # JsonFormatter hashes this
    safe["event_kind"] = kind
    _APP_EVENT_LOGGER.info("event %s", kind, extra=safe)


# ---------------------------------------------------------------------------
# Audit sink
# ---------------------------------------------------------------------------

_AUDIT_LOCK = threading.Lock()
_AUDIT_CONTAINER_NAME = "audit_events"


def _audit_dir() -> Path:
    return Path.home() / ".multiagent" / "audit"


def _write_audit_local(rec: dict[str, Any]) -> None:
    target = _audit_dir()
    target.mkdir(parents=True, exist_ok=True)
    fname = target / f"{_dt.date.today().isoformat()}.jsonl"
    line = json.dumps(rec, default=str, ensure_ascii=False)
    with _AUDIT_LOCK:
        with fname.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _write_audit_cosmos(rec: dict[str, Any]) -> bool:
    """Try the Cosmos audit container. Returns True on success."""
    try:
        from multiagent import storage_cosmos  # local import (lazy)

        if not storage_cosmos.is_enabled():
            return False
        container = storage_cosmos._container(_AUDIT_CONTAINER_NAME)  # noqa: SLF001
        container.upsert_item(body=rec)
        return True
    except Exception as exc:  # noqa: BLE001
        # Audit failures are non-fatal -- fall through to local file. We log
        # at WARNING so the issue is visible without flooding stdout.
        logging.getLogger(__name__).warning("audit cosmos write failed: %s", exc)
        return False


def audit_event(kind: str, user_id: str | None, **fields: Any) -> None:
    """Persist a RAW event with full PII to the restricted audit sink.

    Hosted: written to Cosmos container ``audit_events`` (partition key
    ``/user_id``). Local: appended to
    ``~/.multiagent/audit/<YYYY-MM-DD>.jsonl``. Never echoed to stdout.

    Use sparingly -- only for records that genuinely need the raw text
    (user message bodies, tool arguments under investigation, account-level
    actions). Everything else should use :func:`app_event` instead.
    """
    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "ts": _dt.datetime.now(_dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "kind": kind,
        "user_id": user_id or "anon",
    }
    for k, v in fields.items():
        # Allow callers to overwrite the auto-generated fields if they really
        # want to (e.g. supplying a deterministic id for idempotency).
        rec[k] = v
    if _write_audit_cosmos(rec):
        return
    _write_audit_local(rec)


def audit_enabled_for_user_messages() -> bool:
    """Honor the ``AUDIT_USER_MESSAGES`` env switch. Off by default."""
    val = os.environ.get("AUDIT_USER_MESSAGES", "")
    return val.lower() in ("1", "true", "yes", "on")
