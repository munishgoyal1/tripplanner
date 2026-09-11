"""The one cost control: measured INR spend against daily/weekly/monthly ceilings.

This module replaces the previous family of proxy limits (per-trip Places call
counters, per-turn tool-phase budgets, durable new-trip/turn counters, a per-user
monthly USD cap). Those counted *trips* and *calls* as a stand-in for money and
mispriced a real trip by roughly 4x in either direction. This counts money.

Two things are persisted from one write path:

1. **Window counters** -- environment-wide INR spent in the current day, ISO week
   and calendar month, plus in-flight reservations. Admission checks these.
2. **Per-trip cost documents** -- what each trip actually cost, broken down by
   provider, operation and LLM turns, with an anomaly flag. These feed the
   operations dashboard and are how an unoptimized flow gets identified, rather
   than being silently truncated mid-itinerary by a call budget.

Reserve-then-reconcile
----------------------
A turn reserves a pessimistic estimate at admission and reconciles it to actual
cost when the turn's usage batch flushes. Without the reservation step, N
concurrent turns each read the same "spent so far" and all pass a check none of
them would pass individually -- which is how a ceiling ends up not stopping
anything. Reservations expire so a crashed process cannot hold budget forever.

Unknown cost is never free
--------------------------
A billable call whose SKU carries no price estimate would otherwise contribute
zero and let spend run past the ceiling unseen. When a batch contains any such
call, the whole interaction is charged at the rolling P95 for its category if
that exceeds the priced sum. This is what protects against the cost estimator
itself breaking, and is why the deleted conversation counters are not needed as
a second mechanism.

UNITS: every amount in this module, in its storage documents, and in its API is
**INR**. Provider records arrive as ``estimated_cost_usd`` and cross into INR
exactly once, through ``cost_model.usd_to_inr``, at ingestion in ``_batch_cost``.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from tripplanner import cost_model, limits_config, storage_cosmos
from tripplanner.json_store import atomic_write_json

CostCategory = Literal["new_trip", "trip_update"]

_CONTAINER = "trip_costs"
_WINDOWS_DOC_ID = "_windows_v1"
_TRIP_DOC_PREFIX = "trip_"
_MAX_WRITE_ATTEMPTS = 5
_MAX_RECENT_COSTS = 200
_RESERVATION_TTL_SEC = 900  # a turn that has not settled in 15 minutes is gone
_LOCAL_LOCK = Lock()


class CostCeilingError(RuntimeError):
    """Raised when admitting a turn would breach an INR ceiling."""

    def __init__(
        self,
        *,
        window: str,
        spent_inr: float,
        pending_inr: float,
        ceiling_inr: float,
        resets_at: str | None,
    ) -> None:
        super().__init__(f"{window} cost ceiling reached")
        self.window = window
        self.spent_inr = round(spent_inr, 2)
        self.pending_inr = round(pending_inr, 2)
        self.ceiling_inr = round(ceiling_inr, 2)
        self.resets_at = resets_at

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": "cost_ceiling_reached",
            "window": self.window,
            "spent_inr": self.spent_inr,
            "pending_inr": self.pending_inr,
            "ceiling_inr": self.ceiling_inr,
            "currency": "INR",
            "resets_at": self.resets_at,
        }


class LedgerUnavailableError(RuntimeError):
    """The ledger could not be read or written, so spend is unknown."""


@dataclass(frozen=True)
class Reservation:
    id: str
    category: str
    amount_inr: float


# --- Window keys -------------------------------------------------------------


def _window_key(window: str, now: datetime) -> str:
    if window == "daily":
        return now.strftime("%Y-%m-%d")
    if window == "weekly":
        return now.strftime("%G-W%V")
    return now.strftime("%Y-%m")


def _resets_at(window: str, now: datetime) -> str:
    midnight = datetime(now.year, now.month, now.day, tzinfo=UTC)
    if window == "daily":
        reset = midnight + timedelta(days=1)
    elif window == "weekly":
        reset = midnight + timedelta(days=7 - now.weekday())
    else:
        reset = (
            datetime(now.year + 1, 1, 1, tzinfo=UTC)
            if now.month == 12
            else datetime(now.year, now.month + 1, 1, tzinfo=UTC)
        )
    return reset.isoformat().replace("+00:00", "Z")


def _environment() -> str:
    return cost_model.environment()


# --- Storage -----------------------------------------------------------------


def _local_root() -> Path:
    return Path(os.getenv("TRIPPLANNER_HOME", str(Path.home() / ".tripplanner")))


def _local_windows_path() -> Path:
    return _local_root() / "operations" / f"cost_ledger_{_environment()}.json"


def _local_trips_dir() -> Path:
    path = _local_root() / "trip_costs" / _environment()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)[:120]


def _empty_windows() -> dict[str, Any]:
    return {
        "version": 1,
        "environment": _environment(),
        "windows": {
            window: {"key": "", "spent_inr": 0.0}
            for window in limits_config.COST_CEILING_WINDOWS
        },
        "reservations": {},
        "recent_costs_inr": {"new_trip": [], "trip_update": []},
        "settled_interactions": [],
    }


def _read_local_windows() -> dict[str, Any]:
    path = _local_windows_path()
    if not path.exists():
        return _empty_windows()
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return _empty_windows()


# --- Cost extraction ---------------------------------------------------------


def _billable(record: dict[str, Any]) -> bool:
    return bool(record.get("billable")) and record.get("event_type") != "cache_hit"


def _record_cost_inr(record: dict[str, Any]) -> float | None:
    """INR cost of one provider record, or ``None`` when it carries no estimate.

    This is the single crossing from the USD provider catalog into the INR the
    rest of this module speaks.
    """
    estimate_usd = record.get("estimated_cost_usd")
    if estimate_usd is None:
        return None
    return cost_model.usd_to_inr(estimate_usd) * max(1, int(record.get("units") or 1))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = (percentile / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _category(interaction_kind: str) -> CostCategory:
    return "new_trip" if interaction_kind == "new_trip" else "trip_update"


def _is_trip_interaction(interaction_kind: str) -> bool:
    """Whether this interaction's cost should shape the reservation percentiles.

    ``usage_scope`` wraps more than chat turns -- destination guides, corpus
    generation, CLI runs. All of their spend counts against the ceiling, but
    folding it into the per-category samples would drag the estimate for what a
    planning turn costs toward work that is not a planning turn.
    """
    return interaction_kind in {"new_trip", "trip_update"}


def estimate_reserve_inr(category: str, body: dict[str, Any] | None = None) -> float:
    """Pessimistic INR to hold while a turn of ``category`` runs."""
    settings = cost_model.reservation_settings()
    seeds = settings.get("seedReserveInr", {})
    seed = float(seeds.get(category, seeds.get("new_trip", 60.0)))
    recent = list((body or {}).get("recent_costs_inr", {}).get(category) or [])
    if len(recent) < int(settings.get("minSamples", 5)):
        return seed
    value = _percentile(recent, float(settings.get("reservePercentile", 75)))
    return max(float(value or seed), seed * 0.25)


def _unknown_cost_floor_inr(category: str, body: dict[str, Any]) -> float:
    settings = cost_model.reservation_settings()
    seeds = settings.get("seedUnknownInr", {})
    seed = float(seeds.get(category, seeds.get("new_trip", 120.0)))
    recent = list(body.get("recent_costs_inr", {}).get(category) or [])
    if len(recent) < int(settings.get("minSamples", 5)):
        return seed
    value = _percentile(recent, float(settings.get("unknownCostPercentile", 95)))
    return max(float(value or seed), seed * 0.25)


def _batch_cost(
    records: Iterable[dict[str, Any]], category: str, body: dict[str, Any]
) -> tuple[float, int]:
    """Return ``(charged_inr, unknown_calls)`` for one settled interaction."""
    priced_inr = 0.0
    unknown_calls = 0
    for record in records:
        if not _billable(record):
            continue
        cost_inr = _record_cost_inr(record)
        if cost_inr is None:
            unknown_calls += 1
            continue
        priced_inr += cost_inr
    if unknown_calls:
        return max(priced_inr, _unknown_cost_floor_inr(category, body)), unknown_calls
    return priced_inr, 0


# --- Window document mutation ------------------------------------------------


def _rolled_windows(body: dict[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
    stored = dict(body.get("windows") or {})
    rolled: dict[str, dict[str, Any]] = {}
    for window in limits_config.COST_CEILING_WINDOWS:
        key = _window_key(window, now)
        bucket = dict(stored.get(window) or {})
        spent = float(bucket.get("spent_inr") or 0.0) if bucket.get("key") == key else 0.0
        rolled[window] = {"key": key, "spent_inr": spent}
    return rolled


def _live_reservations(body: dict[str, Any], now: datetime) -> dict[str, Any]:
    cutoff = now - timedelta(seconds=_RESERVATION_TTL_SEC)
    live: dict[str, Any] = {}
    for reservation_id, entry in dict(body.get("reservations") or {}).items():
        try:
            created = datetime.fromisoformat(str(entry.get("created_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if created >= cutoff:
            live[reservation_id] = entry
    return live


def _reserved_total_inr(reservations: dict[str, Any]) -> float:
    return sum(float(entry.get("amount_inr") or 0.0) for entry in reservations.values())


def _with_reservation(
    body: dict[str, Any], *, category: str, reservation_id: str, now: datetime
) -> tuple[dict[str, Any], Reservation]:
    windows = _rolled_windows(body, now)
    reservations = _live_reservations(body, now)
    # A retried request reuses its interaction id, so replace its own prior hold
    # rather than stacking a second one on top of it.
    reservations.pop(reservation_id, None)
    pending_inr = _reserved_total_inr(reservations)
    amount_inr = estimate_reserve_inr(category, body)

    for window in limits_config.COST_CEILING_WINDOWS:
        ceiling_inr = limits_config.cost_ceiling_inr(window)
        spent_inr = windows[window]["spent_inr"]
        if spent_inr + pending_inr + amount_inr > ceiling_inr:
            raise CostCeilingError(
                window=window,
                spent_inr=spent_inr,
                pending_inr=pending_inr,
                ceiling_inr=ceiling_inr,
                resets_at=_resets_at(window, now),
            )

    reservation = Reservation(id=reservation_id, category=category, amount_inr=amount_inr)
    reservations[reservation.id] = {
        "amount_inr": amount_inr,
        "category": category,
        "created_at": now.isoformat().replace("+00:00", "Z"),
    }
    updated = dict(body)
    updated.update(
        {
            "version": 1,
            "environment": _environment(),
            "windows": windows,
            "reservations": reservations,
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        }
    )
    return updated, reservation


def _with_settlement(
    body: dict[str, Any],
    *,
    reservation_id: str,
    interaction_id: str,
    category: str,
    is_trip: bool,
    now: datetime,
    records: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], float, int] | None:
    settled = [str(value) for value in body.get("settled_interactions") or []]
    if interaction_id and interaction_id in settled:
        return None

    windows = _rolled_windows(body, now)
    reservations = _live_reservations(body, now)
    reservations.pop(reservation_id, None)

    charged_inr, unknown_calls = _batch_cost(records, category, body)
    for window in limits_config.COST_CEILING_WINDOWS:
        windows[window]["spent_inr"] = round(windows[window]["spent_inr"] + charged_inr, 4)

    recent = dict(body.get("recent_costs_inr") or {})
    if is_trip and charged_inr > 0:
        bucket = [float(value) for value in recent.get(category) or []]
        bucket.append(round(charged_inr, 4))
        recent[category] = bucket[-_MAX_RECENT_COSTS:]

    updated = dict(body)
    updated.update(
        {
            "version": 1,
            "environment": _environment(),
            "windows": windows,
            "reservations": reservations,
            "recent_costs_inr": recent,
            "settled_interactions": (
                settled + ([interaction_id] if interaction_id else [])
            )[-_MAX_RECENT_COSTS:],
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        }
    )
    return updated, charged_inr, unknown_calls


def _mutate_windows(mutator) -> Any:
    """Apply ``mutator(body) -> (updated_body, result) | None`` under optimistic
    concurrency.

    Read-modify-write with a version check and bounded retries, rather than a
    blind upsert: two turns settling at once would otherwise each write a total
    computed from the state before the other, and the ceiling would drift down
    from real spend exactly when traffic is heaviest.
    """
    if storage_cosmos.is_enabled():
        environment = _environment()
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            current = storage_cosmos.read_doc_versioned(
                _CONTAINER, environment, _WINDOWS_DOC_ID
            )
            body = dict(current.body) if current is not None else _empty_windows()
            outcome = mutator(body)
            if outcome is None:
                return None
            updated, result = outcome
            try:
                if current is None:
                    storage_cosmos.create_doc_if_absent(
                        _CONTAINER, environment, _WINDOWS_DOC_ID, updated
                    )
                else:
                    storage_cosmos.replace_doc_if_version(
                        _CONTAINER, environment, _WINDOWS_DOC_ID, updated, current.version
                    )
                return result
            except storage_cosmos.WriteConflictError:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    raise LedgerUnavailableError("cost ledger kept changing under contention")
        raise LedgerUnavailableError("cost ledger kept changing under contention")

    with _LOCAL_LOCK:
        body = _read_local_windows()
        outcome = mutator(body)
        if outcome is None:
            return None
        updated, result = outcome
        atomic_write_json(_local_windows_path(), updated, indent=2)
        return result


# --- Public admission API ----------------------------------------------------


def reserve(
    category: str, *, interaction_id: str = "", now: datetime | None = None
) -> Reservation | None:
    """Hold a pessimistic INR estimate for a turn about to run.

    The hold is keyed by ``interaction_id`` so ``settle`` can find and release it
    with nothing threaded through the call stack, and so a retry of the same
    request replaces its own hold instead of stacking another.

    Raises ``CostCeilingError`` when the hold would breach a ceiling. Returns
    ``None`` when the ledger is unavailable and policy allows the turn anyway.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    normalized = _category(category)
    reservation_id = interaction_id.strip() or uuid.uuid4().hex
    try:
        return _mutate_windows(
            lambda body: _with_reservation(
                body, category=normalized, reservation_id=reservation_id, now=now
            )
        )
    except CostCeilingError as exc:
        if limits_config.cost_ceiling_enforced():
            raise
        _log(
            "cost_ceiling_would_block",
            category=normalized,
            window=exc.window,
            spent_inr=exc.spent_inr,
            ceiling_inr=exc.ceiling_inr,
        )
        return None
    except Exception as exc:  # noqa: BLE001 - storage faults decide by policy, not by luck
        if limits_config.cost_ceiling_deny_on_ledger_error():
            raise LedgerUnavailableError(str(exc)) from exc
        _log("cost_ledger_unavailable", stage="reserve", error=type(exc).__name__)
        return None


def settle(
    attribution: dict[str, Any],
    records: Sequence[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> None:
    """Reconcile a finished interaction: replace its reservation with actual INR
    spend and fold the same records into the trip's cost document."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    interaction_kind = str(attribution.get("interaction_kind") or "")
    category = _category(interaction_kind)
    is_trip = _is_trip_interaction(interaction_kind)
    interaction_id = str(attribution.get("interaction_id") or "")
    reservation_id = interaction_id

    def mutator(body: dict[str, Any]) -> tuple[dict[str, Any], tuple[float, int]] | None:
        result = _with_settlement(
            body,
            reservation_id=reservation_id,
            interaction_id=interaction_id,
            category=category,
            is_trip=is_trip,
            now=now,
            records=records,
        )
        if result is None:
            return None
        updated, charged, unknown = result
        return updated, (charged, unknown)

    try:
        outcome = _mutate_windows(mutator)
    except Exception as exc:  # noqa: BLE001 - accounting must never break a turn
        _log("cost_ledger_unavailable", stage="settle", error=type(exc).__name__)
        return
    if outcome is None:
        return
    charged_inr, unknown_calls = outcome

    try:
        _update_trip_document(
            attribution, records, charged_inr=charged_inr, category=category, now=now
        )
    except Exception as exc:  # noqa: BLE001
        _log("trip_cost_write_failed", error=type(exc).__name__)

    _log(
        "cost_settled",
        **attribution,
        category=category,
        cost_inr=round(charged_inr, 2),
        unknown_cost_calls=unknown_calls,
    )


def release(interaction_id: str, *, now: datetime | None = None) -> None:
    """Drop the hold for a turn that never ran. Reservations also expire on their
    own, so a failure here costs headroom only until the TTL passes."""
    if not interaction_id:
        return
    now = (now or datetime.now(UTC)).astimezone(UTC)

    def mutator(body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        reservations = _live_reservations(body, now)
        reservations.pop(interaction_id, None)
        updated = dict(body)
        updated["reservations"] = reservations
        return updated, True

    try:
        _mutate_windows(mutator)
    except Exception:  # noqa: BLE001
        pass


# --- Per-trip cost documents -------------------------------------------------


def _trip_doc_id(trip_id: str) -> str:
    return f"{_TRIP_DOC_PREFIX}{_safe_id(trip_id)}"


def _empty_trip_doc(trip_id: str, destination: str, now: datetime) -> dict[str, Any]:
    stamp = now.isoformat().replace("+00:00", "Z")
    return {
        "trip_id": trip_id,
        "destination": destination,
        "environment": _environment(),
        "first_seen_at": stamp,
        "last_activity_at": stamp,
        "turns": {},
        "llm": {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_inr": 0.0,
        },
        "providers": {},
        "totals": {
            "calls": 0,
            "cache_hits": 0,
            "cost_inr": 0.0,
            "savings_inr": 0.0,
            "unknown_cost_calls": 0,
        },
        "anomaly": {"flagged": False, "ratio_to_median": None, "reason": ""},
    }


def _fold_records(doc: dict[str, Any], records: Sequence[dict[str, Any]]) -> None:
    llm = dict(doc.get("llm") or {})
    providers = dict(doc.get("providers") or {})
    totals = dict(doc.get("totals") or {})

    for record in records:
        provider = str(record.get("provider") or "unknown")
        operation = str(record.get("operation") or "request")
        units = max(1, int(record.get("units") or 1))

        if record.get("event_type") == "cache_hit":
            totals["cache_hits"] = int(totals.get("cache_hits") or 0) + units
            totals["savings_inr"] = round(
                float(totals.get("savings_inr") or 0.0)
                + cost_model.usd_to_inr(record.get("estimated_savings_usd") or 0.0),
                4,
            )
            continue

        cost_inr = _record_cost_inr(record) if _billable(record) else 0.0
        if _billable(record) and cost_inr is None:
            totals["unknown_cost_calls"] = int(totals.get("unknown_cost_calls") or 0) + 1
            cost_inr = 0.0

        totals["calls"] = int(totals.get("calls") or 0) + units
        totals["cost_inr"] = round(float(totals.get("cost_inr") or 0.0) + (cost_inr or 0.0), 4)

        if provider == "azure_openai":
            llm["calls"] = int(llm.get("calls") or 0) + 1
            llm["prompt_tokens"] = int(llm.get("prompt_tokens") or 0) + int(
                record.get("prompt_tokens") or 0
            )
            llm["completion_tokens"] = int(llm.get("completion_tokens") or 0) + int(
                record.get("completion_tokens") or 0
            )
            llm["cost_inr"] = round(float(llm.get("cost_inr") or 0.0) + (cost_inr or 0.0), 4)
            continue

        entry = dict(providers.get(provider) or {"calls": 0, "cost_inr": 0.0, "by_operation": {}})
        entry["calls"] = int(entry.get("calls") or 0) + units
        entry["cost_inr"] = round(float(entry.get("cost_inr") or 0.0) + (cost_inr or 0.0), 4)
        by_operation = dict(entry.get("by_operation") or {})
        by_operation[operation] = int(by_operation.get(operation) or 0) + units
        entry["by_operation"] = by_operation
        providers[provider] = entry

    doc["llm"] = llm
    doc["providers"] = providers
    doc["totals"] = totals


def _flag_anomaly(doc: dict[str, Any], category: str, body_recent: Sequence[float]) -> None:
    settings = cost_model.anomaly_settings()
    minimum = int(settings.get("minSamplesForMedian", 5))
    floor_inr = float(settings.get("absoluteFloorInr", 150.0))
    ratio_limit = float(settings.get("ratioToMedian", 3.0))
    cost_inr = float((doc.get("totals") or {}).get("cost_inr") or 0.0)

    if len(body_recent) < minimum:
        doc["anomaly"] = {"flagged": False, "ratio_to_median": None, "reason": ""}
        return
    median = _percentile(body_recent, 50) or 0.0
    ratio = round(cost_inr / median, 2) if median > 0 else None
    flagged = bool(cost_inr > floor_inr and ratio is not None and ratio > ratio_limit)
    doc["anomaly"] = {
        "flagged": flagged,
        "ratio_to_median": ratio,
        "reason": (
            f"{ratio}x the median {category.replace('_', ' ')} cost of INR {median:.0f}"
            if flagged
            else ""
        ),
    }
    if flagged:
        _log(
            "trip_cost_anomaly",
            trip_id=str(doc.get("trip_id") or ""),
            destination=str(doc.get("destination") or ""),
            cost_inr=round(cost_inr, 2),
            ratio_to_median=ratio,
        )


def _update_trip_document(
    attribution: dict[str, Any],
    records: Sequence[dict[str, Any]],
    *,
    charged_inr: float,
    category: str,
    now: datetime,
) -> None:
    trip_id = str(attribution.get("trip_id") or "").strip()
    if not trip_id or trip_id == "unattributed":
        return

    destination = str(attribution.get("trip_name") or attribution.get("destination") or "")
    environment = _environment()
    doc_id = _trip_doc_id(trip_id)

    def build(existing: dict[str, Any] | None) -> dict[str, Any]:
        doc = dict(existing) if existing else _empty_trip_doc(trip_id, destination, now)
        if destination:
            doc["destination"] = destination
        doc["last_activity_at"] = now.isoformat().replace("+00:00", "Z")
        turns = dict(doc.get("turns") or {})
        turns[category] = int(turns.get(category) or 0) + 1
        doc["turns"] = turns
        _fold_records(doc, records)
        return doc

    recent = _recent_costs_for(category)
    if storage_cosmos.is_enabled():
        existing = storage_cosmos.read_doc(_CONTAINER, environment, doc_id)
        doc = build(existing)
        _flag_anomaly(doc, category, recent)
        storage_cosmos.upsert_doc(_CONTAINER, environment, doc_id, doc)
        return

    path = _local_trips_dir() / f"{_safe_id(trip_id)}.json"
    with _LOCAL_LOCK:
        existing = None
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = None
        doc = build(existing)
        _flag_anomaly(doc, category, recent)
        atomic_write_json(path, doc, indent=2)


def _recent_costs_for(category: str) -> list[float]:
    try:
        body = _read_windows_body()
    except Exception:  # noqa: BLE001
        return []
    return [float(value) for value in (body.get("recent_costs_inr") or {}).get(category) or []]


def _read_windows_body() -> dict[str, Any]:
    if storage_cosmos.is_enabled():
        return dict(
            storage_cosmos.read_doc(_CONTAINER, _environment(), _WINDOWS_DOC_ID)
            or _empty_windows()
        )
    with _LOCAL_LOCK:
        return _read_local_windows()


# --- Reporting ---------------------------------------------------------------


def snapshot(now: datetime | None = None) -> dict[str, Any]:
    """Ceiling state for the operations dashboard. All amounts INR."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        body = _read_windows_body()
    except Exception:  # noqa: BLE001
        body = _empty_windows()
    windows = _rolled_windows(body, now)
    reservations = _live_reservations(body, now)
    pending_inr = _reserved_total_inr(reservations)

    result: dict[str, Any] = {
        "currency": "INR",
        "enforced": limits_config.cost_ceiling_enforced(),
        "environment": _environment(),
        "pending_inr": round(pending_inr, 2),
        "windows": {},
    }
    for window in limits_config.COST_CEILING_WINDOWS:
        ceiling_inr = limits_config.cost_ceiling_inr(window)
        spent_inr = windows[window]["spent_inr"]
        result["windows"][window] = {
            "key": windows[window]["key"],
            "spent_inr": round(spent_inr, 2),
            "ceiling_inr": round(ceiling_inr, 2),
            "remaining_inr": round(max(0.0, ceiling_inr - spent_inr - pending_inr), 2),
            "used_pct": round(100.0 * (spent_inr + pending_inr) / ceiling_inr, 1)
            if ceiling_inr > 0
            else None,
            "resets_at": _resets_at(window, now),
        }
    return result


def _load_all_trip_docs() -> list[dict[str, Any]]:
    if storage_cosmos.is_enabled():
        try:
            return storage_cosmos.operations_query(
                _CONTAINER,
                "SELECT * FROM c WHERE c.user_id = @env AND STARTSWITH(c.id, @prefix) "
                "ORDER BY c.last_activity_at DESC",
                [
                    {"name": "@env", "value": _environment()},
                    {"name": "@prefix", "value": _TRIP_DOC_PREFIX},
                ],
            )
        except Exception:  # noqa: BLE001
            return []
    docs: list[dict[str, Any]] = []
    for path in _local_trips_dir().glob("*.json"):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    docs.sort(key=lambda doc: str(doc.get("last_activity_at") or ""), reverse=True)
    return docs


def _one_line(doc: dict[str, Any]) -> str:
    """Compact human summary of one trip's cost, for the dashboard table."""
    totals = doc.get("totals") or {}
    llm = doc.get("llm") or {}
    turns = sum(int(value) for value in (doc.get("turns") or {}).values())
    google = (doc.get("providers") or {}).get("google") or {}
    by_operation = google.get("by_operation") or {}
    parts = [
        f"INR {float(totals.get('cost_inr') or 0):.0f}",
        f"{turns} turn{'s' if turns != 1 else ''}",
        f"{int(llm.get('calls') or 0)} LLM calls",
    ]
    if google:
        detail = " / ".join(
            f"{count} {name.replace('_', ' ')}"
            for name, count in sorted(by_operation.items(), key=lambda item: -item[1])[:2]
        )
        parts.append(f"{int(google.get('calls') or 0)} Google ({detail})" if detail else "Google")
    other_calls = sum(
        int((entry or {}).get("calls") or 0)
        for name, entry in (doc.get("providers") or {}).items()
        if name != "google"
    )
    if other_calls:
        parts.append(f"{other_calls} provider")
    calls = int(totals.get("calls") or 0)
    hits = int(totals.get("cache_hits") or 0)
    if calls + hits:
        parts.append(f"{round(100.0 * hits / (calls + hits))}% cached")
    return " · ".join(parts)


def recent_trips(
    limit: int = 20, trip_names: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Most recently active trips with their measured INR cost.

    ``trip_names`` maps trip id -> destination. Cost documents are written on the
    hot path from provider records alone, which carry no destination, so the
    readable name is resolved here from saved trips instead of costing a lookup
    per settled interaction.
    """
    names = trip_names or {}
    docs = _load_all_trip_docs()[: max(1, int(limit))]
    for doc in docs:
        trip_id = str(doc.get("trip_id") or "")
        if not doc.get("destination") and names.get(trip_id):
            doc["destination"] = names[trip_id]
        doc["summary"] = _one_line(doc)
    return docs


def aggregate() -> dict[str, Any]:
    """Cumulative and per-trip average INR across every recorded trip."""
    docs = _load_all_trip_docs()
    costs = [float((doc.get("totals") or {}).get("cost_inr") or 0.0) for doc in docs]
    total_inr = sum(costs)
    new_trip_turns = sum(int((doc.get("turns") or {}).get("new_trip") or 0) for doc in docs)
    update_turns = sum(int((doc.get("turns") or {}).get("trip_update") or 0) for doc in docs)
    body = _read_windows_body()
    recent = body.get("recent_costs_inr") or {}
    return {
        "currency": "INR",
        "trips": len(docs),
        "cumulative_inr": round(total_inr, 2),
        "average_per_trip_inr": round(total_inr / len(docs), 2) if docs else 0.0,
        "median_per_trip_inr": round(_percentile(costs, 50) or 0.0, 2),
        "p95_per_trip_inr": round(_percentile(costs, 95) or 0.0, 2),
        "turns": {"new_trip": new_trip_turns, "trip_update": update_turns},
        "average_per_turn_inr": {
            "new_trip": round(_percentile(recent.get("new_trip") or [], 50) or 0.0, 2),
            "trip_update": round(_percentile(recent.get("trip_update") or [], 50) or 0.0, 2),
        },
        "anomalies": sum(1 for doc in docs if (doc.get("anomaly") or {}).get("flagged")),
    }


def clear_for_tests() -> None:
    cost_model.reset_cache_for_tests()
    path = _local_windows_path()
    if path.exists():
        path.unlink(missing_ok=True)
    for trip_path in _local_trips_dir().glob("*.json"):
        trip_path.unlink(missing_ok=True)


def _log(event: str, **fields: Any) -> None:
    try:
        from tripplanner.observability import app_event

        app_event(event, **fields)
    except Exception:  # noqa: BLE001 - telemetry must never break accounting
        pass


__all__ = [
    "CostCategory",
    "CostCeilingError",
    "LedgerUnavailableError",
    "Reservation",
    "aggregate",
    "clear_for_tests",
    "estimate_reserve_inr",
    "recent_trips",
    "release",
    "reserve",
    "settle",
    "snapshot",
]
