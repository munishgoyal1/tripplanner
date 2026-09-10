"""Durable record of every alert condition firing/resolving, captured in-app.

Azure Monitor and GCP Monitoring alerts (`infra/main.bicep`,
`infra/gcp/apply-billing-guardrails.ps1`) notify by email only -- nothing
persists "alert X fired at time Y" anywhere queryable. This module closes
that gap by duplicating each alert's aggregate condition check in-process,
using the app's own event stream, and durably recording state transitions
(fired / resolved) to Cosmos (or a local JSONL fallback, matching
`provider_usage.py`'s dual-mode pattern) so the owner -- or an agent asked
to "scan all alerts" -- can see history independent of email.

Seven signals are tracked, mirroring the seven Azure/GCP alerts exactly:

  application_failure    ERROR/CRITICAL log lines, chat/tool errors
                          (infra/queries/application-failures.kql)
  chat_latency_burn       chat turn p95 duration burn
                          (infra/queries/chat-latency-burn.kql)
  model_throttling        Azure OpenAI rate-limit rate
                          (infra/queries/model-throttling.kql)
  provider_circuit_open   an outbound provider's circuit breaker stays open
                          (infra/queries/provider-circuit-open.kql)
  cache_degradation       cache miss rate
                          (infra/queries/cache-degradation.kql)
  cosmos_throttling       Cosmos DB HTTP 429s (infra/main.bicep
                          cosmosThrottlingAlert -- threshold/window sourced
                          from infra/billing-guardrails.json, a genuine ARM
                          value, unlike the KQL-embedded numbers above)
  gcp_quota_exceeded      a Google Places/Maps/Routes call was rejected by
                          GCP's own hard per-minute/day quota (any 429 means
                          the quota, already enforced by Google, was hit)

The four KQL-derived numeric thresholds (samples/rate/span) are hardcoded
here as Python constants, each commented with the exact `.kql` file they
mirror -- these stay out of user-facing config by design (the query bodies
themselves are not config-driven either; see infra/billing-guardrails.json's
top comment). Window sizes for those four are read from
`infra/billing-guardrails.json`'s `azureInfraHealthAlerts` section, which
*is* legitimate ARM config, so there is exactly one number for "how wide is
the window," not two.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)
_CONTAINER = "alert_events"
_LOCK = threading.Lock()
_HOSTED_ENVIRONMENTS = {"canary", "prod", "production"}
_LOCAL_RETENTION_DAYS = 180

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARDRAILS_PATH = _REPO_ROOT / "infra" / "billing-guardrails.json"

# --- KQL-mirroring thresholds (kept out of JSON config; see module docstring) ---
_CHAT_LATENCY_MIN_SAMPLES = 5
_CHAT_LATENCY_P95_THRESHOLD_MS = 120_000
_MODEL_THROTTLE_MIN_SAMPLES = 5
_MODEL_THROTTLE_MIN_COUNT = 2
_MODEL_THROTTLE_MIN_RATE = 0.2
_CIRCUIT_OPEN_MIN_SIGNALS = 3
_CIRCUIT_OPEN_MIN_SPAN_SEC = 5 * 60
_CACHE_DEGRADATION_MIN_ACCESSES = 20
_CACHE_DEGRADATION_MIN_MISS_RATE = 0.5
_APPLICATION_FAILURE_WINDOW_SEC = 300  # mirrors failureAlert's PT5M window
_GCP_QUOTA_WINDOW_SEC = 300


def _environment() -> str:
    return os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()


def _now() -> float:
    return time.monotonic()


_ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?$")


def _parse_iso_duration_seconds(value: str, default: int = 900) -> int:
    match = _ISO_DURATION_RE.match(value or "")
    if not match:
        return default
    hours, minutes = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60


_guardrails_cache: dict[str, Any] | None = None


def _guardrails() -> dict[str, Any]:
    global _guardrails_cache
    if _guardrails_cache is None:
        try:
            _guardrails_cache = json.loads(_GUARDRAILS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a bad/missing config file must not break the app
            _guardrails_cache = {}
    return _guardrails_cache


def _infra_alert(name: str) -> dict[str, Any]:
    infra_alerts = _guardrails().get("azureInfraHealthAlerts") or {}
    for alert in infra_alerts.get("operationalAlerts") or []:
        if alert.get("signal") == name:
            return alert
    return {}


def _window_seconds(signal: str, default: int) -> int:
    alert = _infra_alert(signal)
    if alert.get("windowSize"):
        return _parse_iso_duration_seconds(str(alert["windowSize"]), default)
    return default


def _severity(signal: str, default: int) -> int:
    alert = _infra_alert(signal)
    return int(alert.get("severity", default))


def _gcp_quota_severity() -> int:
    policy = _guardrails().get("gcpQuotaAlertPolicies") or {}
    label = str(
        (policy.get("severityByEnvironment") or {}).get(_environment())
        or (policy.get("severityByEnvironment") or {}).get("default")
        or "WARNING"
    ).upper()
    return 1 if label == "ERROR" else 2


def _cosmos_throttling_config() -> tuple[int, int, int]:
    alert = (_guardrails().get("azureInfraHealthAlerts") or {}).get("cosmosThrottlingAlert") or {}
    threshold = int(alert.get("threshold", 20))
    window = _parse_iso_duration_seconds(str(alert.get("windowSize") or ""), 900)
    severity = int(alert.get("severity", 3))
    return threshold, window, severity


# ---------------------------------------------------------------------------
# Rolling windows (per-signal; pruned lazily on access)
# ---------------------------------------------------------------------------

_chat_ops: deque[tuple[float, bool, bool]] = deque()  # (ts, is_error, is_throttled) + duration below
_chat_durations: deque[tuple[float, float]] = deque()  # (ts, duration_ms)
_circuit_open: dict[str, deque[float]] = defaultdict(deque)
_cache_access: deque[tuple[float, bool]] = deque()  # (ts, is_miss)
_cosmos_429: deque[float] = deque()
_gcp_429: deque[float] = deque()
_application_failures: deque[float] = deque()

# Open (firing, not yet resolved) records, keyed by signal or "signal:key".
_open_state: dict[str, dict[str, Any]] = {}


def _prune(window: deque, window_seconds: float, now: float) -> None:
    while window and now - window[0] > window_seconds:
        window.popleft()


def _prune_pairs(window: deque, window_seconds: float, now: float) -> None:
    while window and now - window[0][0] > window_seconds:
        window.popleft()


# ---------------------------------------------------------------------------
# Storage (Cosmos, with local-JSONL fallback -- mirrors provider_usage.py)
# ---------------------------------------------------------------------------


def _local_dir() -> Path:
    path = Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner"))) / _CONTAINER
    path.mkdir(parents=True, exist_ok=True)
    return path


def _local_path(day: str) -> Path:
    return _local_dir() / f"{day}.jsonl"


_last_prune_day = ""


def _prune_local() -> None:
    global _last_prune_day
    today = datetime.now(UTC).date()
    if _last_prune_day == today.isoformat():
        return
    cutoff = today - timedelta(days=_LOCAL_RETENTION_DAYS)
    for path in _local_dir().glob("*.jsonl"):
        try:
            if datetime.strptime(path.stem, "%Y-%m-%d").date() < cutoff:
                path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue
    _last_prune_day = today.isoformat()


def _write(record: dict[str, Any]) -> None:
    environment = record["environment"]
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            storage_cosmos.upsert_doc(_CONTAINER, environment, str(record["id"]), record)
            return
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("alert_events Cosmos write failed: %s", type(exc).__name__)

    if environment in _HOSTED_ENVIRONMENTS:
        return
    _prune_local()
    path = _local_path(str(record["fired_at"])[:10])
    with _LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def _open(signal: str, *, key: str | None = None, severity: int, detail: dict[str, Any]) -> None:
    state_key = f"{signal}:{key}" if key else signal
    if state_key in _open_state:
        _open_state[state_key]["last_seen"] = _now()
        return
    fired_at = datetime.now(UTC).isoformat()
    record = {
        "id": uuid.uuid4().hex,
        "environment": _environment(),
        "signal": signal,
        "key": key,
        "severity": severity,
        "state": "firing",
        "fired_at": fired_at,
        "resolved_at": None,
        "detail": detail,
    }
    _open_state[state_key] = {
        "id": record["id"],
        "fired_at": fired_at,
        "last_seen": _now(),
        "signal": signal,
        "key": key,
    }
    _write(record)


def _resolve(signal: str, *, key: str | None = None) -> None:
    state_key = f"{signal}:{key}" if key else signal
    state = _open_state.pop(state_key, None)
    if state is None:
        return
    _write(
        {
            "id": state["id"],
            "environment": _environment(),
            "signal": signal,
            "key": key,
            "state": "resolved",
            "fired_at": state["fired_at"],
            "resolved_at": datetime.now(UTC).isoformat(),
        }
    )


def _reap_stale(now: float, max_age_seconds: float = 1800.0) -> None:
    """Resolve open states whose signal has gone quiet (no new matching event
    to trigger re-evaluation). Called opportunistically on every observe()."""
    stale = [
        key
        for key, state in _open_state.items()
        if now - state["last_seen"] > max_age_seconds
    ]
    for state_key in stale:
        state = _open_state.pop(state_key, None)
        if state is not None:
            _write(
                {
                    "id": state["id"],
                    "environment": _environment(),
                    "signal": state["signal"],
                    "key": state["key"],
                    "state": "resolved",
                    "fired_at": state["fired_at"],
                    "resolved_at": datetime.now(UTC).isoformat(),
                }
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def observe(event_kind: str, fields: dict[str, Any]) -> None:
    """Feed one app_event into the alert-condition evaluators. Never raises."""
    try:
        _observe(event_kind, fields)
    except Exception:  # noqa: BLE001 - alert detection must never break a request
        _LOGGER.warning("alert_events.observe failed", exc_info=True)


def _observe(event_kind: str, fields: dict[str, Any]) -> None:
    now = _now()
    _reap_stale(now)

    if event_kind == "chat_operation":
        _observe_chat_operation(fields, now)
    elif event_kind == "tool_call":
        if str(fields.get("status")) == "error":
            _observe_application_failure(now)
    elif event_kind == "outbound_call":
        _observe_outbound_call(fields, now)
    elif event_kind == "cache_access":
        _observe_cache_access(fields, now)
    elif event_kind == "storage_operation":
        _observe_storage_operation(fields, now)


def observe_log_record(level_name: str) -> None:
    """Hook for setup_logging()'s handler -- ERROR/CRITICAL log lines aren't
    routed through app_event(), so this is a second, narrower entry point."""
    if level_name in ("ERROR", "CRITICAL"):
        try:
            now = _now()
            _reap_stale(now)
            _observe_application_failure(now)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("alert_events.observe_log_record failed", exc_info=True)


def _observe_application_failure(now: float) -> None:
    window = _window_seconds("application_failure", _APPLICATION_FAILURE_WINDOW_SEC)
    _application_failures.append(now)
    _prune(_application_failures, window, now)
    if _application_failures:
        _open(
            "application_failure",
            severity=_severity("application_failure", 1),
            detail={"window_count": len(_application_failures), "window_seconds": window},
        )


def _observe_chat_operation(fields: dict[str, Any], now: float) -> None:
    outcome = str(fields.get("outcome") or "")
    if outcome == "error":
        _observe_application_failure(now)

    window = _window_seconds("chat_latency_burn", 900)
    duration_ms = fields.get("duration_ms")
    if isinstance(duration_ms, (int, float)):
        _chat_durations.append((now, float(duration_ms)))
    _prune_pairs(_chat_durations, window, now)
    samples = len(_chat_durations)
    if samples >= _CHAT_LATENCY_MIN_SAMPLES:
        ordered = sorted(ms for _, ms in _chat_durations)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        if p95 > _CHAT_LATENCY_P95_THRESHOLD_MS:
            _open(
                "chat_latency_burn",
                severity=_severity("chat_latency_burn", 2),
                detail={"samples": samples, "p95_ms": round(p95, 1)},
            )
        else:
            _resolve("chat_latency_burn")
    else:
        _resolve("chat_latency_burn")

    throttled = outcome == "rate_limited" or bool(fields.get("rate_limit_scope"))
    _chat_ops.append((now, outcome == "error", throttled))
    while _chat_ops and now - _chat_ops[0][0] > window:
        _chat_ops.popleft()
    throttle_samples = len(_chat_ops)
    throttles = sum(1 for _, _, t in _chat_ops if t)
    if throttle_samples >= _MODEL_THROTTLE_MIN_SAMPLES:
        rate = throttles / throttle_samples
        if throttles >= _MODEL_THROTTLE_MIN_COUNT and rate >= _MODEL_THROTTLE_MIN_RATE:
            _open(
                "model_throttling",
                severity=_severity("model_throttling", 2),
                detail={"samples": throttle_samples, "throttles": throttles, "throttle_rate": round(rate, 3)},
            )
        else:
            _resolve("model_throttling")
    else:
        _resolve("model_throttling")


def _observe_outbound_call(fields: dict[str, Any], now: float) -> None:
    status = str(fields.get("status") or "")
    provider = str(fields.get("provider") or "")
    endpoint = str(fields.get("endpoint") or "")

    if status == "circuit_open" and provider:
        window = _circuit_open[provider]
        window.append(now)
        while window and now - window[0] > 3600:  # generous horizon; span check does the real work
            window.popleft()
        if len(window) >= _CIRCUIT_OPEN_MIN_SIGNALS and (window[-1] - window[0]) >= _CIRCUIT_OPEN_MIN_SPAN_SEC:
            _open(
                "provider_circuit_open",
                key=provider,
                severity=_severity("provider_circuit_open", 3),
                detail={"provider": provider, "open_signals": len(window), "span_seconds": round(window[-1] - window[0], 1)},
            )
        else:
            _resolve("provider_circuit_open", key=provider)
    elif provider:
        _resolve("provider_circuit_open", key=provider)

    http_status = fields.get("http_status")
    if provider == "google" and http_status == 429:
        window = _GCP_QUOTA_WINDOW_SEC
        _gcp_429.append(now)
        _prune(_gcp_429, window, now)
        _open(
            "gcp_quota_exceeded",
            severity=_gcp_quota_severity(),
            detail={"endpoint": endpoint, "window_count": len(_gcp_429), "window_seconds": window},
        )
    elif provider == "google":
        # A clean (non-429) Google call: age out old 429s and resolve if none remain.
        _prune(_gcp_429, _GCP_QUOTA_WINDOW_SEC, now)
        if not _gcp_429:
            _resolve("gcp_quota_exceeded")


def _observe_cache_access(fields: dict[str, Any], now: float) -> None:
    window = _window_seconds("cache_degradation", 900)
    result = str(fields.get("result") or "")
    _cache_access.append((now, result in ("miss", "refresh")))
    _prune_pairs(_cache_access, window, now)
    accesses = len(_cache_access)
    if accesses >= _CACHE_DEGRADATION_MIN_ACCESSES:
        misses = sum(1 for _, is_miss in _cache_access if is_miss)
        rate = misses / accesses
        if rate >= _CACHE_DEGRADATION_MIN_MISS_RATE:
            _open(
                "cache_degradation",
                severity=_severity("cache_degradation", 3),
                detail={"accesses": accesses, "misses": misses, "miss_rate": round(rate, 3)},
            )
        else:
            _resolve("cache_degradation")
    else:
        _resolve("cache_degradation")


def _observe_storage_operation(fields: dict[str, Any], now: float) -> None:
    if fields.get("store") != "cosmos":
        return
    threshold, window, severity = _cosmos_throttling_config()
    if fields.get("status") == "error" and fields.get("status_code") == 429:
        _cosmos_429.append(now)
    _prune(_cosmos_429, window, now)
    if len(_cosmos_429) >= threshold:
        _open(
            "cosmos_throttling",
            severity=severity,
            detail={"window_count": len(_cosmos_429), "window_seconds": window, "threshold": threshold},
        )
    else:
        _resolve("cosmos_throttling")


# ---------------------------------------------------------------------------
# Reads (for scripts/analyze_errors.py and the operations dashboard)
# ---------------------------------------------------------------------------


def _range(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    since = until - timedelta(days=max(1, min(365, int(days))))
    return since, until


def _all_records(days: int) -> list[dict[str, Any]]:
    since, until = _range(days)
    try:
        from tripplanner import storage_cosmos

        if storage_cosmos.is_enabled():
            rows = storage_cosmos.operations_query(
                _CONTAINER,
                "SELECT * FROM c WHERE c.fired_at >= @since",
                [{"name": "@since", "value": since.isoformat()}],
            )
            return [row for row in rows if str(row.get("fired_at") or "") >= since.isoformat()]
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("alert_events Cosmos read failed: %s", type(exc).__name__)
        return []

    rows: list[dict[str, Any]] = []
    day = since.date()
    while day <= until.date():
        path = _local_path(day.isoformat())
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if str(row.get("fired_at") or "") >= since.isoformat():
                        rows.append(row)
                except (json.JSONDecodeError, TypeError):
                    continue
        day += timedelta(days=1)
    return rows


def snapshot(days: int = 30) -> dict[str, Any]:
    """Counts by signal + severity, for the operations dashboard."""
    records = _all_records(days)
    by_signal: dict[str, dict[str, Any]] = {}
    for row in records:
        signal = str(row.get("signal") or "unknown")
        bucket = by_signal.setdefault(
            signal, {"fired": 0, "resolved": 0, "severity": row.get("severity")}
        )
        if row.get("state") == "firing":
            bucket["fired"] += 1
            if row.get("severity") is not None:
                bucket["severity"] = row["severity"]
        elif row.get("state") == "resolved":
            bucket["resolved"] += 1
    since, until = _range(days)
    return {
        "period_days": days,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "by_signal": by_signal,
        "total_fired": sum(b["fired"] for b in by_signal.values()),
    }


def recent(limit: int = 50, days: int = 30) -> list[dict[str, Any]]:
    """Most recently fired records, newest first."""
    records = [row for row in _all_records(days) if row.get("state") == "firing"]
    records.sort(key=lambda row: str(row.get("fired_at") or ""), reverse=True)
    return records[:limit]


class LogHandler(logging.Handler):
    """Feeds raw ERROR/CRITICAL log lines (not routed through app_event())
    into the application_failure signal. Register via setup_logging()."""

    def emit(self, entry: logging.LogRecord) -> None:
        if not entry.name.startswith("tripplanner") or entry.name == __name__:
            return
        if hasattr(entry, "event_kind"):
            return  # already an app_event(); handled via the event-observer path
        observe_log_record(entry.levelname)


def reset_for_tests() -> None:
    """Clear in-process state between tests."""
    for window in (_chat_ops, _chat_durations, _cache_access, _cosmos_429, _gcp_429, _application_failures):
        window.clear()
    _circuit_open.clear()
    _open_state.clear()
    global _guardrails_cache
    _guardrails_cache = None
