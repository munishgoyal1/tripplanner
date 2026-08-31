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
   - Local: ``~/.tripplanner/audit/<YYYY-MM-DD>.jsonl``.
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
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
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


def model_rate_limit_fields(error: BaseException, deployment: str) -> dict[str, Any]:
    """Return a strict whitelist of safe Azure OpenAI 429 metadata."""
    if type(error).__name__ != "RateLimitError":
        return {}

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}

    def header_int(name: str) -> int | None:
        try:
            value = headers.get(name)
            return max(0, int(float(value))) if value is not None else None
        except (TypeError, ValueError):
            return None

    remaining_requests = header_int("x-ratelimit-remaining-requests")
    remaining_tokens = header_int("x-ratelimit-remaining-tokens")
    retry_after_ms = header_int("retry-after-ms")
    if retry_after_ms is None:
        retry_after_seconds = header_int("retry-after")
        retry_after_ms = retry_after_seconds * 1000 if retry_after_seconds is not None else None

    if remaining_tokens == 0 and remaining_requests == 0:
        scope = "tokens_and_requests"
    elif remaining_tokens == 0 or (
        remaining_tokens is not None
        and remaining_requests is not None
        and remaining_requests > 0
    ):
        scope = "tokens"
    elif remaining_requests == 0:
        scope = "requests"
    else:
        scope = "unknown"

    status_code = getattr(error, "status_code", None) or getattr(
        response, "status_code", None
    )
    code = getattr(error, "code", None)
    safe_code = (
        str(code)
        if code is not None and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(code))
        else None
    )
    fields: dict[str, Any] = {
        "model_provider": "azure_openai",
        "model_deployment": deployment,
        "rate_limit_scope": scope,
    }
    if isinstance(status_code, int):
        fields["provider_status"] = status_code
    if safe_code:
        fields["provider_error_code"] = safe_code
    if retry_after_ms is not None:
        fields["retry_after_ms"] = retry_after_ms
    if remaining_requests is not None:
        fields["remaining_requests"] = remaining_requests
    if remaining_tokens is not None:
        fields["remaining_tokens"] = remaining_tokens
    return fields


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
            "ts": _dt.datetime.fromtimestamp(record.created, _dt.UTC)
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
            base["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(base, default=str, ensure_ascii=False)


class _TextFormatterWithPid(logging.Formatter):
    """Slightly richer than the default text formatter -- prepends a short
    logger name and the level. Used in local dev mode."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        ts = _dt.datetime.fromtimestamp(record.created, _dt.UTC).strftime("%H:%M:%S")
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
            - ``APP_LOG_PATH`` (optional rotating PII-safe JSON file for local analysis)
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
            h.close()
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.addFilter(PiiRedactingFilter())
        handler.setFormatter(JsonFormatter() if use_json else _TextFormatterWithPid())
        root.addHandler(handler)

        app_log_path = os.environ.get("APP_LOG_PATH")
        if app_log_path:
            path = Path(app_log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path,
                maxBytes=5_000_000,
                backupCount=2,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.addFilter(PiiRedactingFilter())
            file_handler.setFormatter(JsonFormatter())
            root.addHandler(file_handler)
        root.setLevel(level)

        # Quiet some noisy third-party loggers in normal mode.
        for noisy in ("azure", "httpx", "httpcore", "urllib3", "openai"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _SETUP_DONE = True


# ---------------------------------------------------------------------------
# Structured event helpers
# ---------------------------------------------------------------------------

_APP_EVENT_LOGGER = logging.getLogger("tripplanner.event")
_EVENT_OBSERVERS_LOCK = threading.Lock()
_EVENT_OBSERVERS: list[Any] = []


def add_event_observer(observer: Any) -> None:
    with _EVENT_OBSERVERS_LOCK:
        _EVENT_OBSERVERS.append(observer)


def remove_event_observer(observer: Any) -> None:
    with _EVENT_OBSERVERS_LOCK:
        if observer in _EVENT_OBSERVERS:
            _EVENT_OBSERVERS.remove(observer)


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
    from tripplanner.validation.harness.context import current_context

    context = current_context()
    if context is not None:
        fields = {**context.event_fields(), **fields}
    try:
        from tripplanner.usage_attribution import current_attribution

        fields = {**current_attribution().fields(), **fields}
    except Exception:
        pass
    safe: dict[str, Any] = {}
    for k, v in fields.items():
        if k.lower() in _SENSITIVE_FIELDS:
            safe[k] = "<redacted>"
        else:
            safe[k] = redact_value(v)
    safe["user_id"] = user_id  # JsonFormatter hashes this
    safe["event_kind"] = kind
    try:
        from tripplanner.usage_attribution import append_current_event

        append_current_event(kind, safe)
    except Exception:
        pass
    with _EVENT_OBSERVERS_LOCK:
        observers = tuple(_EVENT_OBSERVERS)
    for observer in observers:
        try:
            observer(kind, safe)
        except Exception:
            continue
    _APP_EVENT_LOGGER.info("event %s", kind, extra=safe)


@contextmanager
def timed_operation(kind: str, operation: str, **fields: Any) -> Iterator[None]:
    """Emit one content-free terminal duration event for an operation."""
    started = time.perf_counter()
    status = "ok"
    error = None
    try:
        yield
    except Exception as exc:
        status = "error"
        error = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        from tripplanner.ops_metrics import record_operation

        record_operation(kind, operation, status, duration_ms)
        app_event(
            kind,
            operation=operation,
            status=status,
            ms=duration_ms,
            **({"error": error} if error else {}),
            **fields,
        )


# ---------------------------------------------------------------------------
# Audit sink
# ---------------------------------------------------------------------------

_AUDIT_LOCK = threading.Lock()
_AUDIT_CONTAINER_NAME = "audit_events"


def _audit_dir() -> Path:
    return Path.home() / ".tripplanner" / "audit"


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
        from tripplanner import storage_cosmos  # local import (lazy)

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
    ``~/.tripplanner/audit/<YYYY-MM-DD>.jsonl``. Never echoed to stdout.

    Use sparingly -- only for records that genuinely need the raw text
    (user message bodies, tool arguments under investigation, account-level
    actions). Everything else should use :func:`app_event` instead.
    """
    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "ts": _dt.datetime.now(_dt.UTC)
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


# ---------------------------------------------------------------------------
# Per-tool metrics
# ---------------------------------------------------------------------------
#
# We accumulate lightweight counters and a small recent-latency window for
# every tool the agent invokes. The same wrapper that runs the cache lookup
# in ``tools_cache.py`` reports a result here, so a tool that's served from
# cache shows up with ``cache_hit=True`` and (near-) zero latency.
#
# This stays purely in-process — it's meant for instant `/metrics/tools`
# introspection during a session and for emitting a structured `tool_call`
# app event each time. Long-horizon aggregation is out of scope (that's
# what Log Analytics is for, via the existing app_event stream).

_METRICS_LOCK = threading.Lock()
_TOOL_METRICS: dict[str, dict[str, Any]] = {}
_RECENT_LATENCIES_WINDOW = 50  # keep last 50 latencies per tool for p50/p95


def record_tool_call(
    tool_name: str,
    *,
    duration_ms: float,
    status: str,
    cache_hit: bool = False,
    cache_scope: str | None = None,
    user_id: str | None = None,
    error: str | None = None,
) -> None:
    """Record a single tool invocation.

    ``status`` is one of ``"ok"``, ``"error"``. ``cache_hit`` is True when the
    result was served from ``tools_cache`` (so we can show hit-rate per tool).
    ``cache_scope`` is ``"global"`` or ``"user"`` when available.
    ``error`` is the exception class name when status="error".

    Emits a PII-safe ``tool_call`` app event as a side-effect — this is the
    one place that fans out the metric to BOTH the in-memory aggregator
    (for live introspection) and the structured log (for Log Analytics).
    """
    with _METRICS_LOCK:
        m = _TOOL_METRICS.setdefault(
            tool_name,
            {
                "calls": 0,
                "errors": 0,
                "cache_hits": 0,
                "total_ms": 0.0,
                "recent_ms": [],
                "error_types": {},
            },
        )
        m["calls"] += 1
        if status == "error":
            m["errors"] += 1
            if error:
                error_types: dict[str, int] = m["error_types"]
                error_types[error] = error_types.get(error, 0) + 1
        if cache_hit:
            m["cache_hits"] += 1
        # We still record latency on errors so a slow-failing tool surfaces.
        m["total_ms"] += duration_ms
        recent: list[float] = m["recent_ms"]
        recent.append(duration_ms)
        if len(recent) > _RECENT_LATENCIES_WINDOW:
            del recent[: len(recent) - _RECENT_LATENCIES_WINDOW]

    app_event(
        "tool_call",
        user_id=user_id,
        tool=tool_name,
        status=status,
        ms=round(duration_ms, 2),
        cache_hit=cache_hit,
        **({"cache_scope": cache_scope} if cache_scope else {}),
        **({"error": error} if error else {}),
    )


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Tiny nearest-rank percentile — good enough for a 50-sample window."""
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, int(round(pct / 100.0 * (len(sorted_values) - 1)))))
    return round(sorted_values[k], 2)


def tool_metrics_snapshot() -> dict[str, dict[str, Any]]:
    """Return a copy of the metrics table with derived stats per tool.

    Each value carries: calls, errors, cache_hits, error_rate, hit_rate,
    avg_ms (over all calls), p50_ms / p95_ms (over the recent window).
    """
    out: dict[str, dict[str, Any]] = {}
    with _METRICS_LOCK:
        for name, m in _TOOL_METRICS.items():
            calls = m["calls"]
            recent_sorted = sorted(m["recent_ms"])
            out[name] = {
                "calls": calls,
                "errors": m["errors"],
                "cache_hits": m["cache_hits"],
                "error_rate": round(m["errors"] / calls, 3) if calls else 0.0,
                "hit_rate": round(m["cache_hits"] / calls, 3) if calls else 0.0,
                "avg_ms": round(m["total_ms"] / calls, 2) if calls else 0.0,
                "p50_ms": _percentile(recent_sorted, 50),
                "p95_ms": _percentile(recent_sorted, 95),
                "error_types": dict(
                    sorted(m["error_types"].items(), key=lambda item: item[1], reverse=True)[:5]
                ),
            }
    return out


def reset_tool_metrics() -> None:
    """Test hook: wipe accumulated metrics."""
    with _METRICS_LOCK:
        _TOOL_METRICS.clear()

