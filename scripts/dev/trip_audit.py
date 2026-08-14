"""Audit every trip the harness can see, and report what is new.

    python scripts/dev/trip_audit.py
    python scripts/dev/trip_audit.py --all --rule I9
    python scripts/dev/trip_audit.py --accept

Reads the debug store, every sandbox emulator database, and the captured
fixtures. Never calls a model or a provider: place facts come from what each
trip was rendered with.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# The audit reads stored facts only. Cutting the shared caches off before the
# app package loads keeps a provider outage from looking like a clean run.
os.environ["TRIPPLANNER_DEBUG_STORE"] = "0"
for _variable in ("COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_CONNECTION_STRING"):
    os.environ[_variable] = ""

from tripplanner.validation import findings as findings_module  # noqa: E402
from tripplanner.validation import runner  # noqa: E402

_BAR = "-" * 78


def _print_report(result: runner.AuditResult, *, show_all: bool, rule: str) -> None:
    mix = ", ".join(f"{name} {count}" for name, count in sorted(result.provenance_mix.items()))
    print(f"Corpus: {result.corpus_size} trip(s) [{mix or 'empty'}]")
    for source in result.sources:
        print(f"  read  {source}")
    for skip in result.skipped:
        print(f"  skip  {skip}")

    groups = result.groups if show_all else result.new
    if rule:
        groups = [item for item in groups if item.rule.lower() == rule.lower()]
    label = "finding" if show_all else "new finding"
    print(_BAR)
    if not groups:
        print(f"No {label}s.")
        return
    print(f"{len(groups)} {label} group(s), {sum(item.count for item in groups)} occurrence(s):")
    for item in groups:
        provenance = ", ".join(f"{k} {v}" for k, v in sorted(item.provenances.items()))
        print()
        print(f"  [{item.rule}] x{item.count}  ({provenance})")
        print(f"    {item.exemplar.message}")
        print(f"    first seen in {item.exemplar.record_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="show every finding, not just new ones")
    parser.add_argument("--rule", default="", help="only this rule code, e.g. I9")
    parser.add_argument("--accept", action="store_true", help="record current findings as known")
    parser.add_argument("--no-debug-store", action="store_true")
    parser.add_argument("--no-revisions", action="store_true", help="final plans only")
    parser.add_argument("--no-fixtures", action="store_true")
    parser.add_argument("--database", action="append", default=None, help="repeatable")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    result = runner.audit(
        REPO_ROOT,
        debug_store=not args.no_debug_store,
        revisions=not args.no_revisions,
        fixtures=not args.no_fixtures,
        databases=args.database,
    )

    if args.as_json:
        print(
            json.dumps(
                {
                    "corpus": result.corpus_size,
                    "provenance": result.provenance_mix,
                    "sources": result.sources,
                    "skipped": result.skipped,
                    "groups": [
                        {
                            "rule": item.rule,
                            "symptom": item.symptom,
                            "count": item.count,
                            "example": item.exemplar.message,
                            "new": item in result.new,
                        }
                        for item in result.groups
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        _print_report(result, show_all=args.all, rule=args.rule)

    path = runner.baseline_path(REPO_ROOT)
    if args.accept:
        baseline = findings_module.accept(result.groups, findings_module.load_baseline(path))
        findings_module.save_baseline(path, baseline)
        print(f"\nAccepted {len(result.groups)} finding group(s) into {path.name}.")
        return 0

    # A run that read nothing reports no findings, which reads exactly like a
    # clean run. Say so instead.
    if not result.corpus_size:
        print("\nCorpus is empty: nothing was checked.", file=sys.stderr)
        return 2

    stale = findings_module.stale_keys(result.groups, findings_module.load_baseline(path))
    if stale and not args.as_json:
        print(f"\n{len(stale)} accepted finding(s) no longer occur; --accept to prune.")
    return 1 if result.new else 0


if __name__ == "__main__":
    raise SystemExit(main())
