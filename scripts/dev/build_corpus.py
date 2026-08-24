"""Generate corpus trips with the real planner, inside a budget.

    python scripts/dev/build_corpus.py --dry-run
    python scripts/dev/build_corpus.py --budget 1000 --workers 2

Spends money. It refuses to run without headroom under the cumulative cap,
measures each request's real cost from the app's own usage ledger, and stops at
whichever of the budget or the target comes first. Requests are composed from
what the corpus does not already cover and run several at a time, so re-running
tops it up with new shapes and never pays twice for the same one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tripplanner.validation import budget as budget_module  # noqa: E402
from tripplanner.validation import (  # noqa: E402
    generate,
    india_heuristic_matrix,
    india_outbound_matrix,
    matrix,
    runner,
)
from tripplanner.validation.catalog import Catalog  # noqa: E402

DEFAULT_DATABASE = "tripplanner-sbx-2-auto-validation"
DEFAULT_API = "http://127.0.0.1:8110"
_BAR = "-" * 78
_PREVIEW = 12


def _log(message: str) -> None:
    """A run lasts hours through a pipe, so nothing may wait in a buffer."""
    print(message, flush=True)


def _selected_scope(market: str | None, country: str | None) -> tuple[str, str]:
    if market and country:
        raise ValueError("use --market or --country, not both")
    if market:
        return "market", market
    if country:
        return "country", country
    return "matrix", "global"


def _alternate_requests(
    first: tuple[matrix.TripRequest, ...],
    second: tuple[matrix.TripRequest, ...],
    *,
    limit: int,
) -> tuple[matrix.TripRequest, ...]:
    combined: list[matrix.TripRequest] = []
    depth = 0
    while depth < max(len(first), len(second)) and (limit <= 0 or len(combined) < limit):
        for requests in (first, second):
            if depth < len(requests):
                combined.append(requests[depth])
                if limit > 0 and len(combined) >= limit:
                    break
        depth += 1
    return tuple(combined)


def _requests_for_scope(
    scope: tuple[str, str], catalog: Catalog, *, limit: int
) -> tuple[matrix.TripRequest, ...]:
    kind, value = scope
    if kind == "country" and value == "india":
        return india_heuristic_matrix.candidates(catalog, limit=limit)
    if kind == "market" and value == "india":
        domestic = india_heuristic_matrix.candidates(catalog, limit=0)
        outbound = india_outbound_matrix.candidates(catalog, limit=0)
        return _alternate_requests(domestic, outbound, limit=limit)
    return matrix.pending(catalog, limit=limit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=None, help="INR for this run")
    parser.add_argument(
        "--target", type=int, default=0, help="trips to add; 0 means as many as the budget allows"
    )
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--api", default=DEFAULT_API)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--market",
        choices=("india",),
        default=None,
        help="traveler market to cover; india includes domestic and outbound trips",
    )
    scope.add_argument(
        "--country",
        choices=("india",),
        default=None,
        help="destination country to cover; india includes domestic trips within India",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=generate.DEFAULT_WORKERS,
        help="planning turns in flight at once; the API admits 4 by default",
    )
    parser.add_argument("--dry-run", action="store_true", help="plan the run, spend nothing")
    args = parser.parse_args(argv)
    try:
        selected_scope = _selected_scope(args.market, args.country)
    except ValueError as error:
        parser.error(str(error))

    corpus_root = runner.corpus_root(REPO_ROOT)
    try:
        allowed = budget_module.authorize(corpus_root, args.budget)
    except budget_module.BudgetExhaustedError as error:
        print(f"Refusing to run: {error}", file=sys.stderr)
        return 2

    catalog = generate.catalog_for(corpus_root)
    summary = catalog.summary()
    limit = args.target if args.target > 0 else 0
    queued = _requests_for_scope(selected_scope, catalog, limit=limit)

    print(f"Corpus at {corpus_root}")
    print(f"  request scope      {selected_scope[0]}:{selected_scope[1]}")
    print(f"  already produced   {summary['trips']} trip(s)")
    print(f"  destinations       {summary['destinations']} covered")
    print(f"  spent so far       INR {allowed.spent_inr:.0f} of INR {allowed.cap_inr:.0f}")
    print(f"  this run may spend INR {allowed.budget_inr:.0f}  (USD {allowed.budget_usd:.2f})")
    print(f"  candidates ready   {len(queued)}")
    print(f"  in flight at once  {max(1, args.workers)}")
    print(_BAR)
    for request in queued[:_PREVIEW]:
        print(f"  {request.slug:34s} {request.shape}")
    if len(queued) > _PREVIEW:
        print(f"  ... and {len(queued) - _PREVIEW} more, asked for while the budget lasts")
    if args.dry_run:
        print(_BAR)
        print("Dry run: nothing was requested and nothing was spent.")
        return 0
    if not queued:
        print("Nothing left to generate; every candidate is already in the corpus.")
        return 0

    health_error = generate.api_health_error(args.api)
    if health_error:
        print(
            f"Refusing to run: planner API is unavailable at {args.api} ({health_error}).\n"
            "Start sandbox 2, wait for its backend to report ready, then retry.",
            file=sys.stderr,
        )
        return 3

    print(_BAR)
    result = generate.build(
        corpus_root,
        database=args.database,
        api=args.api,
        target=args.target,
        requested_budget_inr=args.budget,
        requests=queued,
        on_progress=_log,
        workers=args.workers,
    )
    print(_BAR)
    print(
        f"Produced {len(result['produced'])} trip(s) for INR {result['spent_inr']:.0f}; "
        f"stopped on {result['stopped_because']}."
    )
    print(f"Corpus now holds {result['corpus_total']} generated trip(s).")
    print(
        f"Generation evidence: run {result['generation_run_id']} at "
        f"{result['generated_by_commit'][:12] or 'unknown commit'}."
    )
    if result["stopped_because"] == "api-unavailable":
        print(
            f"Planner API at {args.api} became unavailable; start sandbox 2 and retry.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
