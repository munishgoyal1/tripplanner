"""Run the Trip Quality Audit and report what is new.

    python scripts/dev/trip_audit.py
    python scripts/dev/trip_audit.py --all --rule I9
    python scripts/dev/trip_audit.py --accept

Reads the Trip Flight Recorder, Trip Quality Corpus, sandbox emulator databases,
and captured fixtures. Never calls a model or a provider: place facts come from
what each trip was rendered with.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = Path(os.environ.get("TRIPPLANNER_AUDIT_REPORT_ROOT") or REPO_ROOT).resolve()
sys.path.insert(0, str(REPO_ROOT / "src"))

# The audit reads stored facts only. Cutting the shared caches off before the
# app package loads keeps a provider outage from looking like a clean run.
os.environ["TRIPPLANNER_DEBUG_STORE"] = "0"
for _variable in ("COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_CONNECTION_STRING"):
    os.environ[_variable] = ""

from tripplanner.evals import findings as findings_module  # noqa: E402
from tripplanner.evals import human as quality_module  # noqa: E402
from tripplanner.evals import observations as observations_module  # noqa: E402
from tripplanner.evals import registry as registry_module  # noqa: E402
from tripplanner.harness import audit as runner  # noqa: E402
from tripplanner.harness import baseline as baseline_module  # noqa: E402
from tripplanner.harness import corpus as corpus_module  # noqa: E402
from tripplanner.harness import lifecycle  # noqa: E402
from tripplanner.harness.generation import generate as generate_module  # noqa: E402

_BAR = "-" * 78


def _print_rules() -> None:
    print(f"{'code':<6} {'severity':<8} rule")
    print(_BAR)
    for rule in registry_module.registry():
        print(f"{rule.code:<6} {rule.severity:<8} {rule.statement}")


def _print_observations(result: runner.AuditResult) -> None:
    print(_BAR)
    print("What these trips actually look like:")
    for item in observations_module.observe(result.records):
        detail = f"  ({item.detail})" if item.detail else ""
        print(f"  {item.label:<34} {item.value}{detail}")


def _print_report(result: runner.AuditResult, *, show_all: bool, rule: str) -> None:
    mix = ", ".join(f"{name} {count}" for name, count in sorted(result.provenance_mix.items()))
    print(f"Corpus: {result.corpus_size} trip(s) [{mix or 'empty'}]")
    for source in result.sources:
        print(f"  read  {source}")
    for skip in result.skipped:
        print(f"  skip  {skip}")
    if result.evaluation:
        summary = result.evaluation
        print(
            f"Evaluations: {summary['executed']} executed, {summary['reused']} reused, "
            f"{summary['errors']} errors, {summary['insufficient_evidence']} incomplete; "
            f"{len(summary['excluded'])} artifacts excluded ({summary['selection']})."
        )

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


def _issue_group(item: findings_module.Group, result: runner.AuditResult) -> dict[str, object]:
    """Project one finding into the owner-facing evidence needed for triage."""
    exemplar = item.exemplar
    rule = registry_module.rule_for(item.rule)
    record = next(
        (candidate for candidate in result.records if candidate.id == exemplar.record_id),
        None,
    )
    plan = record.plan if record else {}
    user_id = str(plan.get("user_id") or "")
    trip_id = str(plan.get("trip_id") or "")
    return {
        "rule": item.rule,
        "title": rule.title if rule else item.rule,
        "statement": rule.statement if rule else "",
        "severity": rule.severity if rule else "",
        "evaluated_in": rule.evaluated_in if rule else "",
        "symptom": item.symptom,
        "count": item.count,
        "example": exemplar.message,
        "new": item in result.new,
        "representative": {
            "record_id": exemplar.record_id,
            "day": exemplar.day,
            "provenance": exemplar.provenance,
            "destination": record.destination if record else "",
            "departure_date": str(plan.get("departure_date") or ""),
            "return_date": str(plan.get("return_date") or ""),
            "user_id": user_id,
            "trip_id": trip_id,
            "openable": bool(user_id and trip_id),
        },
    }


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="show every finding, not just new ones")
    parser.add_argument("--rule", default="", help="only this rule code, e.g. I9")
    parser.add_argument("--accept", action="store_true", help="record current findings as known")
    parser.add_argument("--no-debug-store", action="store_true")
    parser.add_argument("--no-revisions", action="store_true", help="final plans only")
    parser.add_argument("--no-fixtures", action="store_true")
    parser.add_argument("--no-render", action="store_true", help="skip view-model checks")
    parser.add_argument("--no-mutate", action="store_true", help="skip metamorphic checks")
    parser.add_argument("--database", action="append", default=None, help="repeatable")
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--rules", action="store_true", help="list every rule and exit")
    parser.add_argument("--observe", action="store_true", help="describe the corpus too")
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        help="only these local trip/envelope JSON files",
    )
    parser.add_argument("--selection", choices=lifecycle.SELECTIONS, default="active")
    parser.add_argument(
        "--force",
        action="store_true",
        help="execute selected evals despite cached results",
    )
    parser.add_argument(
        "--evaluator",
        action="append",
        choices=("plan", "human", "render", "metamorphic"),
    )
    parser.add_argument("--state-root", type=Path, default=REPORT_ROOT / "audit" / "state")
    parser.add_argument("--set-state", choices=lifecycle.STATES)
    parser.add_argument("--artifact", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--superseded-by", default="")
    parser.add_argument("--verify-fix", metavar="FINDING_KEY")
    parser.add_argument("--before-result", default="")
    parser.add_argument("--after-result", default="")
    parser.add_argument("--verification-kind", choices=("replay", "regenerated"))
    parser.add_argument("--fix-commit", default="")
    parser.add_argument("--issue", default="")
    args = parser.parse_args(argv)
    if args.evaluator and (args.no_render or args.no_mutate):
        parser.error("Use --evaluator or --no-render/--no-mutate, not both")
    if args.set_state and args.verify_fix:
        parser.error("Choose a lifecycle edit or fix verification, not both")

    if args.rules:
        _print_rules()
        return 0

    if args.set_state:
        lifecycle.set_state(
            runner.corpus_root(REPO_ROOT) / "evaluation-lifecycle.json",
            args.artifact,
            args.set_state,
            args.reason,
            args.superseded_by,
        )
        print(f"Artifact {args.artifact} marked {args.set_state}.")
        return 0
    if args.verify_fix:
        receipt = lifecycle.verify_fix(
            args.state_root,
            args.verify_fix,
            args.before_result,
            args.after_result,
            args.verification_kind,
            args.fix_commit,
            args.issue,
        )
        print(json.dumps(receipt, indent=2))
        return 0

    result = runner.audit(
        REPO_ROOT,
        debug_store=not args.no_debug_store,
        revisions=not args.no_revisions,
        fixtures=not args.no_fixtures,
        render=not args.no_render,
        mutate=not args.no_mutate,
        databases=args.database,
        records=[corpus_module.from_json(path) for path in args.input] if args.input else None,
        state_root=args.state_root,
        selection=args.selection,
        force=args.force,
        evaluators=tuple(dict.fromkeys(args.evaluator)) if args.evaluator else None,
    )

    if args.as_json:
        print(
            json.dumps(
                {
                    "corpus": result.corpus_size,
                    "provenance": result.provenance_mix,
                    "sources": result.sources,
                    "skipped": result.skipped,
                    "groups": [_issue_group(item, result) for item in result.groups],
                    "evaluation": result.evaluation,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        _print_report(result, show_all=args.all, rule=args.rule)
        if args.observe:
            _print_observations(result)

    path = runner.baseline_path(REPO_ROOT)
    from tripplanner.harness import audit_report as report_module

    destination = REPORT_ROOT / report_module.LATEST_FILE
    # Read before writing: the report it replaces is what "since last time"
    # is measured against.
    try:
        previous = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = {}
    payload = report_module.build_report(
        result,
        baseline_module.load_baseline(path),
        previous,
        quality_ratings=quality_module.load(runner.corpus_root(REPO_ROOT)),
    )
    payload["generation"] = report_module.generation_evidence(
        generate_module.load_manifest(runner.corpus_root(REPO_ROOT))
    )
    report_path = report_module.save_report(REPORT_ROOT, payload, code_root=REPO_ROOT)
    if not args.as_json:
        print(
            f"\nWrote {report_path.relative_to(REPORT_ROOT)}: "
            f"{len(payload['groups'])} group(s), {len(payload['records'])} record(s)."
        )

    if args.accept:
        if result.evaluation.get("errors"):
            print("Cannot accept an audit with evaluator errors.", file=sys.stderr)
            return 2
        baseline = baseline_module.accept(result.groups, baseline_module.load_baseline(path))
        baseline_module.save_baseline(path, baseline)
        print(f"\nAccepted {len(result.groups)} finding group(s) into {path.name}.")
        return 0

    # A run that read nothing reports no findings, which reads exactly like a
    # clean run. Say so instead.
    if not result.corpus_size and not result.evaluation.get("excluded"):
        print("\nCorpus is empty: nothing was checked.", file=sys.stderr)
        return 2

    if result.evaluation.get("errors"):
        return 2
    stale = payload["retired"]
    if stale and not args.as_json:
        print(f"\n{len(stale)} accepted finding(s) were absent from this complete audit.")
    return 1 if result.new else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except (ValueError, OSError) as error:
        print(f"Audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
