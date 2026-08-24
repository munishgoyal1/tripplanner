"""Drive the real planner to produce corpus trips, within a budget.

This is the only part of the harness that spends money, so it is deliberately
cautious: it refuses to start without headroom, measures what each request
actually cost from the usage ledger rather than estimating, records every trip
it produced, and stops the moment the budget or the target is reached.

Re-running it tops the corpus up. A request that already produced a trip is
never paid for twice.
"""

from __future__ import annotations

import errno
import http.client
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tripplanner.validation import budget as budget_module
from tripplanner.validation import matrix as matrix_module
from tripplanner.validation.catalog import Catalog
from tripplanner.validation.emulator import assert_sandbox_database, read_trips
from tripplanner.validation.matrix import TripRequest

MANIFEST_FILE = "manifest.json"
TRIPS_DIR = "trips"
#: A planning turn is slow; the probe on 2026-08-15 took over two minutes.
REQUEST_TIMEOUT_SEC = 900
#: The API admits four at once, but four planning turns of ~30k prompt characters
#: crossed the model deployment's tokens-per-minute quota on 2026-08-16 and every
#: request came back throttled. The narrower limit is the provider's, not ours.
DEFAULT_WORKERS = 2
#: What to hold back for a request in flight before the run has priced one itself.
ASSUMED_COST_INR = 45.0
_RETRY_STATUS = frozenset({429, 503})
#: Long enough to outlast a token-per-minute window, short enough to notice.
_MAX_RETRY_WAIT_SEC = 180.0
#: A run left going overnight must not spend the whole budget on turns that save
#: nothing. Judged only once enough have finished to tell a bad run from a
#: request or two that legitimately needed a question.
MIN_ATTEMPTS_BEFORE_GIVING_UP = 10
MAX_BARREN_SHARE = 0.25
_MAX_ATTEMPTS = 4


def api_health_error(api: str, timeout: float = 3.0) -> str | None:
    """Return why the planner API cannot accept corpus work, or None when ready."""
    request = urllib.request.Request(f"{api.rstrip('/')}/health")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except (OSError, http.client.HTTPException) as error:
        return f"{type(error).__name__}: {error}"
    return None


def _is_connection_refused(error: BaseException) -> bool:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    return isinstance(reason, ConnectionRefusedError) or (
        isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
    )


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
    destination: str = ""
    emphasis: str = ""
    party: str = ""
    signature: str = ""
    scenario_expectations: tuple[str, ...] = ()
    budget_evidence_required: bool = False


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


def catalog_for(corpus_root: Path) -> Catalog:
    """What the corpus already covers, so the next request is something else."""
    return Catalog(
        entry
        for entry in load_manifest(corpus_root)["produced"]
        if entry.get("trip_id")
    )


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


@dataclass
class _Attempt:
    request: TripRequest
    cost_inr: float = 0.0
    seconds: float = 0.0
    trip: dict[str, Any] | None = None
    model: str = ""
    error: str = ""
    user_id: str = field(default="")


def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    """Wait as long as the server asked, not as long as we guessed.

    A token-per-minute throttle holds for a minute or more; retrying after two
    seconds spends the remaining attempts against a window that is still shut.
    """
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        asked = float(header) if header else 0.0
    except (TypeError, ValueError):
        asked = 0.0
    return min(_MAX_RETRY_WAIT_SEC, max(asked, min(30.0, 2.0 * attempt)))


def _send_with_retry(api: str, message: str, user_id: str, request_id: str) -> str | None:
    """One turn, retried on a refusal. Returns an error description or None."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _ask(api, message, user_id, request_id)
            return None
        except urllib.error.HTTPError as error:
            # A refused admission never ran, so the same id may be offered again.
            if error.code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS:
                return f"HTTP {error.code}"
            time.sleep(_retry_delay(error, attempt))
        except (OSError, http.client.HTTPException) as error:
            # A dropped connection may still have completed the turn, so the retry keeps
            # the request id: a finished turn replays instead of being paid for twice.
            if attempt == _MAX_ATTEMPTS:
                category = (
                    "API unavailable" if _is_connection_refused(error) else type(error).__name__
                )
                return f"{category}: {error}"
            time.sleep(min(30.0, 2.0 * attempt))
    return "exhausted attempts"


def _attempt(request: TripRequest, *, database: str, api: str, usd_inr: float) -> _Attempt:
    """One planning turn, priced by what this user's ledger moved by."""
    user_id = f"corpus-{request.slug}"
    # Built before the ledger is read, so nothing sits between that read and the
    # send: a concurrent attempt's spend would otherwise land in this one's cost.
    # A repeat attempt needs its own id, or the API replays the earlier completed
    # turn and the slug can never recover from a failed first run.
    request_id = f"{user_id}-{uuid.uuid4().hex[:12]}"
    before_usd = _spent_usd(database, user_id)
    started = time.monotonic()

    error = _send_with_retry(api, request.message, user_id, request_id)
    seconds = time.monotonic() - started
    usage = _usage_for(database, user_id)
    cost_inr = max(0.0, float(usage.get("cost_usd") or 0.0) - before_usd) * usd_inr
    if error:
        return _Attempt(request, cost_inr=cost_inr, seconds=seconds, error=error, user_id=user_id)
    return _Attempt(
        request,
        cost_inr=cost_inr,
        seconds=seconds,
        trip=_saved_trip(database, user_id),
        model=str(usage.get("model") or ""),
        user_id=user_id,
    )


def build(
    corpus_root: Path,
    *,
    database: str,
    api: str,
    target: int = 0,
    requested_budget_inr: float | None = None,
    requests: tuple[TripRequest, ...] | None = None,
    on_progress: Any = None,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    """Generate trips until the budget, the target, or the candidates run out.

    Requests run concurrently because a planning turn is nearly all waiting. The
    budget is reserved before a request is sent rather than charged after it
    returns, so several turns in flight can never overshoot the cap between them.
    """
    assert_sandbox_database(database)
    allowed = budget_module.authorize(corpus_root, requested_budget_inr)
    manifest = load_manifest(corpus_root)
    catalog = catalog_for(corpus_root)
    done = already_produced(corpus_root)
    if requests is None:
        requests = matrix_module.pending(catalog, limit=target if target > 0 else 0)
    trips_dir = corpus_root / TRIPS_DIR
    trips_dir.mkdir(parents=True, exist_ok=True)

    spent = 0.0
    produced: list[Produced] = []
    model = ""
    workers = max(1, workers)
    queue = (request for request in requests if request.slug not in done)
    in_flight: dict[Future[_Attempt], tuple[TripRequest, float]] = {}
    reserved = 0.0
    exhausted = False
    barren = 0
    giving_up = False
    api_unavailable = False
    generated_at = datetime.now(UTC)
    run_id = generated_at.strftime("%Y-%m-%dT%H%M%S.%fZ")
    git_result = subprocess.run(
        ["git", "-C", str(corpus_root.parent), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    generated_by_commit = git_result.stdout.strip() if git_result.returncode == 0 else ""

    def _estimate() -> float:
        return max(1.0, spent / len(produced)) if produced else ASSUMED_COST_INR

    def _barren_share() -> float:
        attempts = len(produced) + barren
        return barren / attempts if attempts else 0.0

    def _record(result: _Attempt) -> None:
        nonlocal spent, model, barren, api_unavailable
        request = result.request
        spent += result.cost_inr
        model = result.model or model
        if result.error:
            barren += 1
            if result.error.startswith("API unavailable:"):
                api_unavailable = True
            if on_progress:
                on_progress(f"  {request.slug}: request failed ({result.error})")
            return
        if result.trip is None:
            barren += 1
            if on_progress:
                on_progress(
                    f"  {request.slug}: no itinerary saved "
                    f"(INR {result.cost_inr:.1f}, {result.seconds:.0f}s)"
                )
            return
        days = [
            day for day in (result.trip.get("day_wise_itinerary") or []) if isinstance(day, dict)
        ]
        entry = Produced(
            slug=request.slug,
            shape=request.shape,
            trip_id=str(result.trip.get("id") or result.trip.get("trip_id") or request.slug),
            days=len(days),
            stops=sum(len(day.get("stops") or []) for day in days),
            spent_inr=round(result.cost_inr, 2),
            seconds=round(result.seconds, 1),
            user_id=result.user_id,
            destination=request.destination,
            emphasis=request.emphasis,
            party=request.party,
            signature=request.signature.key,
            scenario_expectations=request.scenario_expectations or (request.shape,),
            budget_evidence_required=request.budget_evidence_required,
        )
        (trips_dir / f"{request.slug}.json").write_text(
            json.dumps(result.trip, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        produced.append(entry)
        catalog.add(request.signature, request.slug)
        manifest["produced"].append(
            {
                **asdict(entry),
                "at": datetime.now(UTC).isoformat(),
                "generation_run_id": run_id,
                "generated_by_commit": generated_by_commit,
            }
        )
        save_manifest(corpus_root, manifest)
        if on_progress:
            on_progress(
                f"  {request.slug}: {entry.days}d/{entry.stops} stops "
                f"(INR {result.cost_inr:.1f}, {result.seconds:.0f}s)"
            )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            while (
                not exhausted
                and not giving_up
                and not api_unavailable
                and len(in_flight) < workers
            ):
                if target > 0 and len(produced) + len(in_flight) >= target:
                    break
                hold = _estimate()
                if spent + reserved + hold > allowed.budget_inr:
                    break
                request = next(queue, None)
                if request is None:
                    exhausted = True
                    break
                if on_progress:
                    headroom = allowed.budget_inr - spent - reserved
                    on_progress(
                        f"  -> {request.slug} (asking; {len(produced)} produced, "
                        f"INR {headroom:.0f} left)"
                    )
                future = pool.submit(
                    _attempt, request, database=database, api=api, usd_inr=allowed.usd_inr
                )
                in_flight[future] = (request, hold)
                reserved += hold
            if not in_flight:
                break
            completed, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
            for future in completed:
                request, hold = in_flight.pop(future)
                reserved -= hold
                try:
                    result = future.result()
                except Exception as error:  # noqa: BLE001 - one bad turn must not end a long run
                    result = _Attempt(request, error=f"{type(error).__name__}: {error}")
                _record(result)
            attempts = len(produced) + barren
            if (
                not giving_up
                and attempts >= MIN_ATTEMPTS_BEFORE_GIVING_UP
                and _barren_share() > MAX_BARREN_SHARE
            ):
                giving_up = True
                if on_progress:
                    on_progress(
                        f"\n  Stopping: {barren} of {attempts} requests saved no itinerary "
                        f"({_barren_share():.0%}, INR {spent:.0f} spent).\n"
                        "  Something is wrong with planning, not with this run. Check one"
                        " request by hand before spending more."
                    )

    if api_unavailable:
        stopped = "api-unavailable"
    elif giving_up:
        stopped = "barren"
    elif target > 0 and len(produced) >= target:
        stopped = "target"
    elif exhausted:
        stopped = "exhausted"
    else:
        stopped = "budget"

    budget_module.record(
        corpus_root,
        spent_inr_amount=spent,
        trips=len(produced),
        model=model or "unknown",
        stopped_because=stopped,
        usd_inr_rate=allowed.usd_inr,
    )
    # The grounding a run warmed is worth more than the run: it lives in one
    # sandbox database otherwise, and dies with the worktree.
    saved_places = 0
    if produced:
        from tripplanner.validation import place_cache

        try:
            path = place_cache.cache_path(corpus_root)
            merged = place_cache.merge(place_cache.load(path), place_cache.collect(database))
            place_cache.save(path, merged)
            saved_places = len(merged)
        except Exception as error:  # noqa: BLE001 - the trips are already safe
            if on_progress:
                on_progress(f"  could not save place cache: {error}")

    return {
        "produced": [asdict(entry) for entry in produced],
        "spent_inr": round(spent, 2),
        "budget_inr": allowed.budget_inr,
        "stopped_because": stopped,
        "corpus_total": len(load_manifest(corpus_root)["produced"]),
        "places_saved": saved_places,
        "generation_run_id": run_id,
        "generated_by_commit": generated_by_commit,
    }
