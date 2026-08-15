"""Drive the real planner to produce corpus trips, within a budget.

This is the only part of the harness that spends money, so it is deliberately
cautious: it refuses to start without headroom, measures what each request
actually cost from the usage ledger rather than estimating, records every trip
it produced, and stops the moment the budget or the target is reached.

Re-running it tops the corpus up. A request that already produced a trip is
never paid for twice.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tripplanner.validation import budget as budget_module
from tripplanner.validation.emulator import assert_sandbox_database, read_trips
from tripplanner.validation.matrix import REQUESTS, TripRequest

MANIFEST_FILE = "manifest.json"
TRIPS_DIR = "trips"
#: A planning turn is slow; the probe on 2026-08-15 took over two minutes.
REQUEST_TIMEOUT_SEC = 900


@dataclass
class Produced:
    slug: str
    shape: str
    trip_id: str
    days: int
    stops: int
    spent_inr: float
    seconds: float
    user_id: str


def manifest_path(corpus_root: Path) -> Path:
    return corpus_root / MANIFEST_FILE


def load_manifest(corpus_root: Path) -> dict[str, Any]:
    path = manifest_path(corpus_root)
    if not path.exists():
        return {"version": 1, "produced": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "produced": []}
    if not isinstance(payload.get("produced"), list):
        return {"version": 1, "produced": []}
    return payload


def already_produced(corpus_root: Path) -> set[str]:
    return {
        str(entry.get("slug"))
        for entry in load_manifest(corpus_root)["produced"]
        if entry.get("trip_id")
    }


def save_manifest(corpus_root: Path, manifest: dict[str, Any]) -> None:
    manifest_path(corpus_root).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(corpus_root).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _usage_for(database: str, user_id: str) -> dict[str, Any]:
    """What this user has cost so far, straight from the app's own ledger."""
    from tripplanner.validation.emulator import _client, assert_sandbox_database

    name = assert_sandbox_database(database)
    try:
        rows = list(
            _client()
            .get_database_client(name)
            .get_container_client("users")
            .query_items(
                query="SELECT * FROM c WHERE c.user_id=@u AND STARTSWITH(c.id, 'usage')",
                parameters=[{"name": "@u", "value": user_id}],
                enable_cross_partition_query=True,
            )
        )
    except Exception:  # noqa: BLE001 - absent usage means we cannot price this run
        return {}
    return rows[0] if rows else {}


def _spent_usd(database: str, user_id: str) -> float:
    """Cumulative spend for this user, so a run can price its own attempt by difference."""
    return float(_usage_for(database, user_id).get("cost_usd") or 0.0)


def _ask(api: str, message: str, user_id: str, request_id: str) -> None:
    body = json.dumps(
        {"message": message, "user_id": user_id, "request_id": request_id}
    ).encode()
    request = urllib.request.Request(
        f"{api.rstrip('/')}/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
        response.read()


def _saved_trip(database: str, user_id: str) -> dict[str, Any] | None:
    """The planned trip this request produced, if it produced one at all.

    A request that only asked a clarifying question still costs money, so the
    caller must be able to tell the difference.
    """
    for trip in read_trips(database, user_id=user_id):
        days = [day for day in (trip.get("day_wise_itinerary") or []) if isinstance(day, dict)]
        if days and any(day.get("stops") for day in days):
            return trip
    return None


def build(
    corpus_root: Path,
    *,
    database: str,
    api: str,
    target: int,
    requested_budget_inr: float | None = None,
    requests: tuple[TripRequest, ...] = REQUESTS,
    on_progress: Any = None,
) -> dict[str, Any]:
    """Generate trips until the target, the budget, or the matrix runs out."""
    assert_sandbox_database(database)
    allowed = budget_module.authorize(corpus_root, requested_budget_inr)
    manifest = load_manifest(corpus_root)
    done = already_produced(corpus_root)
    trips_dir = corpus_root / TRIPS_DIR
    trips_dir.mkdir(parents=True, exist_ok=True)

    spent = 0.0
    produced: list[Produced] = []
    stopped = "matrix"
    model = ""

    for request in requests:
        if len(produced) >= target:
            stopped = "target"
            break
        if spent >= allowed.budget_inr:
            stopped = "budget"
            break
        if request.slug in done:
            continue

        user_id = f"corpus-{request.slug}"
        # A repeat attempt needs its own request id, or the API replays the earlier
        # completed turn and the slug can never recover from a failed first run.
        request_id = f"{user_id}-{uuid.uuid4().hex[:12]}"
        before_usd = _spent_usd(database, user_id)
        started = time.monotonic()
        try:
            _ask(api, request.message, user_id, request_id)
        except (urllib.error.URLError, TimeoutError) as error:
            if on_progress:
                on_progress(f"  {request.slug}: request failed ({error})")
            continue
        seconds = time.monotonic() - started

        usage = _usage_for(database, user_id)
        cost_inr = max(0.0, float(usage.get("cost_usd") or 0.0) - before_usd) * allowed.usd_inr
        model = str(usage.get("model") or model)
        spent += cost_inr

        trip = _saved_trip(database, user_id)
        if trip is None:
            if on_progress:
                on_progress(
                    f"  {request.slug}: no itinerary saved "
                    f"(INR {cost_inr:.1f}, {seconds:.0f}s)"
                )
            continue

        days = [day for day in (trip.get("day_wise_itinerary") or []) if isinstance(day, dict)]
        entry = Produced(
            slug=request.slug,
            shape=request.shape,
            trip_id=str(trip.get("id") or trip.get("trip_id") or request.slug),
            days=len(days),
            stops=sum(len(day.get("stops") or []) for day in days),
            spent_inr=round(cost_inr, 2),
            seconds=round(seconds, 1),
            user_id=user_id,
        )
        (trips_dir / f"{request.slug}.json").write_text(
            json.dumps(trip, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        produced.append(entry)
        manifest["produced"].append({**asdict(entry), "at": datetime.now(UTC).isoformat()})
        save_manifest(corpus_root, manifest)
        if on_progress:
            on_progress(
                f"  {request.slug}: {entry.days}d/{entry.stops} stops "
                f"(INR {cost_inr:.1f}, {seconds:.0f}s)"
            )

    budget_module.record(
        corpus_root,
        spent_inr_amount=spent,
        trips=len(produced),
        model=model or "unknown",
        stopped_because=stopped,
        usd_inr_rate=allowed.usd_inr,
    )
    return {
        "produced": [asdict(entry) for entry in produced],
        "spent_inr": round(spent, 2),
        "budget_inr": allowed.budget_inr,
        "stopped_because": stopped,
        "corpus_total": len(load_manifest(corpus_root)["produced"]),
    }
