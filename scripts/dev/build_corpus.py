"""Generate corpus trips with the real planner, inside a budget.

    python scripts/dev/build_corpus.py --dry-run
    python scripts/dev/build_corpus.py --budget 1000 --target 25

Spends money. It refuses to run without headroom under the cumulative cap,
measures each request's real cost from the app's own usage ledger, and stops at
whichever of the target or the budget comes first. Re-running tops the corpus up
and never pays for a request that already produced a trip.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tripplanner.validation import budget as budget_module  # noqa: E402
from tripplanner.validation import generate, runner  # noqa: E402
from tripplanner.validation.matrix import REQUESTS  # noqa: E402

DEFAULT_DATABASE = "tripplanner-sbx-2-auto-validation"
DEFAULT_API = "http://127.0.0.1:8110"
_BAR = "-" * 78


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=None, help="INR for this run")
    parser.add_argument("--target", type=int, default=len(REQUESTS), help="trips to add")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--dry-run", action="store_true", help="plan the run, spend nothing")
    args = parser.parse_args(argv)

    corpus_root = runner.corpus_root(REPO_ROOT)
    try:
        allowed = budget_module.authorize(corpus_root, args.budget)
    except budget_module.BudgetExhaustedError as error:
        print(f"Refusing to run: {error}", file=sys.stderr)
        return 2

    done = generate.already_produced(corpus_root)
    pending = [request for request in REQUESTS if request.slug not in done][: args.target]

    print(f"Corpus at {corpus_root}")
    print(f"  already produced   {len(done)} trip(s)")
    print(f"  spent so far       INR {allowed.spent_inr:.0f} of INR {allowed.cap_inr:.0f}")
    print(f"  this run may spend INR {allowed.budget_inr:.0f}  (USD {allowed.budget_usd:.2f})")
    print(f"  requests queued    {len(pending)}")
    print(_BAR)
    for request in pending:
        print(f"  {request.slug:26s} {request.shape}")
    if args.dry_run:
        print(_BAR)
        print("Dry run: nothing was requested and nothing was spent.")
        return 0
    if not pending:
        print("Nothing left to generate; the matrix is exhausted.")
        return 0

    print(_BAR)
    result = generate.build(
        corpus_root,
        database=args.database,
        api=args.api,
        target=args.target,
        requested_budget_inr=args.budget,
        on_progress=print,
    )
    print(_BAR)
    print(
        f"Produced {len(result['produced'])} trip(s) for INR {result['spent_inr']:.0f}; "
        f"stopped on {result['stopped_because']}."
    )
    print(f"Corpus now holds {result['corpus_total']} generated trip(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
