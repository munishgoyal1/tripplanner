"""Private, correlated diagnostic events, independent of rotating application logs."""

from __future__ import annotations

import base64
import contextvars
import gzip
import hashlib
import itertools
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

TRACE = contextvars.ContextVar("flight_trace", default="")
SPAN = contextvars.ContextVar("flight_span", default="")
IDENTITY = contextvars.ContextVar("flight_identity", default=None)
_SUPPRESSED = contextvars.ContextVar("flight_suppressed", default=False)
_lock = threading.Lock()
_drain_lock = threading.Lock()
_sequence = itertools.count()
_worker = None
_last_error = ""
_last_uploaded = ""
_SECRET = re.compile(
    r"authorization|cookie|api.?key|secret|password|access.?token|refresh.?token|"
    r"client.?credential|connection.?string|passport.?number|card.?number|cvv|^key$|^sig$",
    re.I,
)
_INLINE = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access_token|refresh_token|password|secret|"
    r"authorization|cookie|key|sig)[\"']?\s*[:=]\s*)([\"']?)([^\s\"'&,;}]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_TTL = 7 * 24 * 60 * 60
_DEFAULT_WORKER_BATCH_SIZE = 25


def enabled():
    return os.getenv("TRIPPLANNER_FLIGHT_RECORDER", "1").lower() not in {"0", "false", "off"}


def root():
    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    # Never allow configuration to escape the private recorder directory.
    environment = re.sub(r"[^a-zA-Z0-9_-]", "_", environment)
    return (
        Path(
            os.getenv(
                "TRIPPLANNER_FLIGHT_RECORDER_DIR",
                str(Path.home() / ".tripplanner" / "flight-recorder"),
            )
        )
        / environment
    )


def sanitize(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python", serialize_as_any=True)
    if isinstance(value, dict):
        return {
            str(k): "<redacted>" if _SECRET.search(str(k)) else sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        if re.match(r"^data:[^\s;,]+[;,]", value):
            return {"omitted": "inline binary", "characters": len(value)}
        return _BEARER.sub("Bearer <redacted>", _INLINE.sub(r"\1\2<redacted>", value))
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return sanitize(str(value))


def _failure(exc):
    global _last_error
    name = type(exc).__name__
    if name != _last_error:
        logging.getLogger(__name__).error("flight_recorder_degraded: %s", name)
    _last_error = name


def record(kind, **payload):
    """Persist before returning; telemetry failures never fail a traveller's request."""
    if not enabled() or _SUPPRESSED.get():
        return
    token = _SUPPRESSED.set(True)
    try:
        from tripplanner.usage_attribution import current_attribution
        from tripplanner.user_context import get_user_id

        attribution = current_attribution().fields()
        event_id = uuid.uuid4().hex
        sequence = next(_sequence)
        event = sanitize(
            {
                **attribution,
                **payload,
                "sequence": sequence,
                "schema_version": 1,
                "event_id": event_id,
                "kind": kind,
                "recorded_at": datetime.now(UTC).isoformat(),
                "unix_time": time.time(),
                "trace_id": TRACE.get()
                or attribution.get("interaction_id")
                or SPAN.get()
                or event_id,
                "span_id": payload.get("span_id", SPAN.get()),
                "user_id": payload.get("user_id")
                or (IDENTITY.get() or {}).get("user_id")
                or get_user_id()
                or "unattributed",
                "pid": os.getpid(),
            }
        )
        directory = root()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / f"{time.time_ns()}-{sequence:012d}-{event_id}.json"
        raw = json.dumps(event, ensure_ascii=False).encode("utf-8")
        with target.with_suffix(".tmp").open("wb") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        target.with_suffix(".tmp").replace(target)
        _start_worker()
    except Exception as exc:
        _failure(exc)
    finally:
        _SUPPRESSED.reset(token)


def _upload(event):
    from tripplanner import storage_cosmos

    raw = json.dumps(event, ensure_ascii=False).encode("utf-8")
    packed = base64.b64encode(gzip.compress(raw)).decode("ascii")
    chunks = [packed[i : i + 128000] for i in range(0, len(packed), 128000)]
    for index, chunk in enumerate(chunks):
        storage_cosmos.upsert_doc(
            "flight_recorder",
            event["user_id"],
            f"{event['event_id']}-{index}",
            {
                "event_id": event["event_id"],
                "trace_id": event["trace_id"],
                "trip_id": event.get("trip_id", ""),
                "kind": event["kind"],
                "recorded_at": event["recorded_at"],
                "index": index,
                "chunks": len(chunks),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "encoding": "gzip+base64",
                "payload": chunk,
                "ttl": _TTL,
            },
        )


def _drain_once(limit: int | None = None) -> int:
    """Retry spooled events idempotently; keep failed uploads for the next pass."""
    global _last_error, _last_uploaded
    from tripplanner import storage_cosmos

    uploaded = 0
    token = _SUPPRESSED.set(True)
    try:
        remote = storage_cosmos.is_enabled()
        hosted = root().name in {"prod", "production", "canary"}
        if hosted and not remote:
            raise RuntimeError("Hosted recorder has no durable Cosmos sink")
        paths = sorted(root().glob("*.json"))
        if limit is not None:
            paths = paths[:limit]
        for path in paths:
            event = json.loads(path.read_text(encoding="utf-8"))
            if remote:
                _upload(event)
                _last_uploaded = event["recorded_at"]
                path.unlink()
                uploaded += 1
            elif time.time() - event["unix_time"] > _TTL:
                path.unlink()
        _last_error = ""
    except Exception as exc:
        _failure(exc)
    finally:
        _SUPPRESSED.reset(token)
    return uploaded


def drain_once():
    with _drain_lock:
        _drain_once()


def _worker_batch_size() -> int:
    try:
        configured = int(
            os.getenv(
                "TRIPPLANNER_FLIGHT_RECORDER_BATCH_SIZE",
                str(_DEFAULT_WORKER_BATCH_SIZE),
            )
        )
    except (TypeError, ValueError):
        configured = _DEFAULT_WORKER_BATCH_SIZE
    return max(1, min(configured, 500))


def clear_user(user_id):
    from tripplanner import storage_cosmos

    with _drain_lock:
        for path in root().glob("*.json"):
            if json.loads(path.read_text(encoding="utf-8")).get("user_id") == user_id:
                path.unlink()
        if storage_cosmos.is_enabled():
            storage_cosmos.delete_docs("flight_recorder", user_id)


class RecorderLogHandler(logging.Handler):
    def emit(self, entry):
        if not entry.name.startswith("tripplanner") or entry.name == __name__:
            return
        if hasattr(entry, "event_kind"):
            return
        record(
            "log.message",
            logger=entry.name,
            level=entry.levelname,
            message=entry.getMessage(),
            exception=(
                logging.Formatter().formatException(entry.exc_info) if entry.exc_info else None
            ),
        )


def _start_worker():
    global _worker
    if os.getenv("TRIPPLANNER_FLIGHT_RECORDER_WORKER", "1") == "0":
        return
    with _lock:
        if _worker is not None and _worker.is_alive():
            return

        def run():
            while True:
                batch_size = _worker_batch_size()
                with _drain_lock:
                    uploaded = _drain_once(limit=batch_size)
                if uploaded:
                    logging.getLogger(__name__).info(
                        "FLIGHT RECORDER uploaded batch=%s",
                        uploaded,
                        extra={
                            "event_kind": "flight_recorder_batch",
                            "uploaded": uploaded,
                            "batch_size": batch_size,
                        },
                    )
                time.sleep(2 if uploaded == batch_size else 10)

        _worker = threading.Thread(target=run, name="flight-recorder", daemon=True)
        _worker.start()


def status():
    return {
        "enabled": enabled(),
        "last_error": _last_error,
        "last_uploaded_at": _last_uploaded,
        "spooled_events": sum(1 for _ in root().glob("*.json")),
    }


def decode_chunks(chunks):
    """Reject incomplete/corrupt evidence instead of returning a misleading partial event."""
    chunks = sorted(chunks, key=lambda c: c["index"])
    if not chunks or [c["index"] for c in chunks] != list(range(chunks[0]["chunks"])):
        raise ValueError("Incomplete flight recorder event")
    if len({(c["event_id"], c["sha256"], c["chunks"]) for c in chunks}) != 1:
        raise ValueError("Mixed flight recorder chunks")
    raw = gzip.decompress(base64.b64decode("".join(c["payload"] for c in chunks)))
    if hashlib.sha256(raw).hexdigest() != chunks[0]["sha256"]:
        raise ValueError("Flight recorder checksum mismatch")
    return json.loads(raw)


def export_events(user_id, *, trip_id="", trace_id="", cosmos=False):
    """Return a user's trace, including early research before a new trip acquired its ID."""
    events = {}
    for path in root().glob("*.json"):
        event = json.loads(path.read_text(encoding="utf-8"))
        if event.get("user_id") == user_id:
            events[event["event_id"]] = event
    if cosmos:
        from tripplanner import storage_cosmos

        groups = {}
        token = _SUPPRESSED.set(True)
        try:
            for chunk in storage_cosmos.query_docs("flight_recorder", user_id):
                groups.setdefault(chunk["event_id"], []).append(chunk)
        finally:
            _SUPPRESSED.reset(token)
        for event_id, chunks in groups.items():
            events[event_id] = decode_chunks(chunks)
    values = list(events.values())
    traces = {e["trace_id"] for e in values if not trip_id or e.get("trip_id") == trip_id}
    return sorted(
        (
            e
            for e in values
            if e["trace_id"] in traces and (not trace_id or e["trace_id"] == trace_id)
        ),
        key=lambda e: (e["unix_time"], e.get("sequence", 0)),
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Export private flight evidence to a local file")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--trip-id", default="")
    parser.add_argument("--trace-id", default="")
    parser.add_argument("--cosmos", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    events = export_events(
        args.user_id, trip_id=args.trip_id, trace_id=args.trace_id, cosmos=args.cosmos
    )
    # Exclusive creation protects an existing investigation from accidental overwrite.
    with args.output.open("x", encoding="utf-8") as stream:
        if os.name != "nt":
            os.fchmod(stream.fileno(), 0o600)
        json.dump({"schema_version": 1, "events": events}, stream, ensure_ascii=False, indent=2)
    print(f"Exported {len(events)} events to {args.output}")


if __name__ == "__main__":
    main()
