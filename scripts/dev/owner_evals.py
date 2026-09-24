"""Build the owner /evals report from offline audit output and judge verdicts.

Never plans a trip and never calls Google: it reads committed corpus trips and
each trip's request from ``corpus/manifest.json`` (reconstructed from the
deterministic generation matrices for trips that predate request capture), and
renders judge packets. Judge verdicts are produced out of band
(by an operator's model session or ``trip_audit.py --judge-profile``) and are
validated here by the same ``evals.judge.validate`` the paid judge uses.

    python scripts/dev/owner_evals.py packets --out <dir> [--slug S ...] [--sample N]
    python scripts/dev/owner_evals.py publish --packets <dir> --judgements <dir> \
        --audit <trip_audit --json output> --findings <findings.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tripplanner.evals import judge, probes, trip_text  # noqa: E402
from tripplanner.harness import corpus as corpus_module  # noqa: E402
from tripplanner.harness.generation import matrix  # noqa: E402
from tripplanner.harness.sources import place_cache  # noqa: E402

CORPUS = ROOT / "corpus"
REPORT = ROOT / "src" / "tripplanner" / "evals" / "owner_report.json"
REPORT_VERSION = 1


def _sample(slugs: list[str], size: int) -> list[str]:
    """Spread a sample across destinations, emphases and parties deterministically."""
    seen: Counter[str] = Counter()
    picked = []
    for slug in sorted(slugs, key=matrix._stable):
        head = slug.split("-")[0]
        if not seen[head]:
            picked.append(slug)
        seen[head] += 1
    return sorted(picked[:size])


def packets(out: Path, slugs: list[str], sample: int) -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text("utf-8"))
    entries = {entry["slug"]: entry for entry in manifest.get("produced", [])}
    places = place_cache.load(place_cache.cache_path(CORPUS))
    records = {
        record.id.removeprefix("generated:"): record
        for record in corpus_module.from_generated_finals(CORPUS / "trips", places={})
    }
    chosen = slugs or _sample(list(records), sample)
    out.mkdir(parents=True, exist_ok=True)
    for slug in chosen:
        record = records[slug]
        entry = entries.get(slug, {})
        # The request comes from the manifest; evidence_for keeps only named places.
        evidence = judge.evidence_for(replace(record, places=places))
        (out / f"{slug}.evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (out / f"{slug}.txt").write_text(trip_text.render(evidence), encoding="utf-8")
        (out / f"{slug}.meta.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    "scenario_expectations": list(entry.get("scenario_expectations") or []),
                    "budget_evidence_required": bool(entry.get("budget_evidence_required")),
                    "request_reconstructed": bool(entry.get("request_reconstructed")),
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    print(f"wrote {len(chosen)} packets to {out}")
    return 0


def _audit_summary(audit: dict[str, Any], group_limit: int) -> dict[str, Any]:
    rules = [
        {
            key: rule.get(key)
            for key in (
                "code",
                "title",
                "statement",
                "severity",
                "hits",
                "trips",
                "evaluated",
            )
        }
        for rule in audit.get("rules", [])
    ]
    groups = sorted(audit.get("groups", []), key=lambda g: -int(g.get("count") or 0))
    return {
        "generated_at": audit.get("generated_at"),
        "corpus": audit.get("corpus", {}),
        "observations": audit.get("observations", []),
        "rules": sorted(rules, key=lambda r: (-int(r.get("trips") or 0), str(r["code"]))),
        "top_groups": [
            {
                "rule": group.get("rule"),
                "symptom": group.get("symptom"),
                "count": group.get("count"),
                "example": group.get("example"),
                "accepted": bool(group.get("accepted_on")),
            }
            for group in groups[:group_limit]
        ],
    }


def publish(args: argparse.Namespace) -> int:
    judged = []
    for path in sorted(args.judgements.glob("*.judgement.json")):
        slug = path.name.removesuffix(".judgement.json")
        evidence = json.loads((args.packets / f"{slug}.evidence.json").read_text("utf-8"))
        payload = json.loads(path.read_text("utf-8"))
        result = judge.validate(payload, evidence)  # raises on any invalid citation
        plan = evidence["plan"]
        judged.append(
            {
                "slug": slug,
                "destination": plan.get("destination"),
                "days": len(plan.get("day_wise_itinerary") or []),
                "request": evidence.get("request"),
                **result,
            }
        )
    dimension_means = {
        key: round(sum(scores) / len(scores), 2) if scores else None
        for key in judge.KEYS
        for scores in [
            [
                item["score"]
                for trip in judged
                for item in trip["assessments"]
                if item["dimension"] == key and item["status"] == "scored"
            ]
        ]
    }
    plans = {
        path.stem: json.loads(path.read_text("utf-8"))
        for path in sorted((CORPUS / "trips").glob("*.json"))
    }
    audit = json.loads(args.audit.read_text("utf-8")) if args.audit else {}
    findings = json.loads(args.findings.read_text("utf-8")) if args.findings else {}
    report = {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "judge": {
            "rubric": judge.rubric(),
            "judge_model": args.judge_model,
            "method": args.judge_method,
            "trips": judged,
            "dimension_means": dimension_means,
        },
        "audit": _audit_summary(audit, args.group_limit) if audit else None,
        "probes": {
            "corpus": "corpus/trips",
            "results": probes.run(plans),
            "place_identity": probes.place_identity(
                place_cache.load(place_cache.cache_path(CORPUS))
            ),
        },
        "findings": findings.get("findings", []),
        "efficiencies": findings.get("efficiencies", []),
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"published {len(judged)} judged trips to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("packets")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--slug", action="append", default=[])
    build.add_argument("--sample", type=int, default=12)
    ship = sub.add_parser("publish")
    ship.add_argument("--packets", type=Path, required=True)
    ship.add_argument("--judgements", type=Path, required=True)
    ship.add_argument("--audit", type=Path)
    ship.add_argument("--findings", type=Path)
    ship.add_argument("--judge-model", default="unrecorded")
    ship.add_argument("--judge-method", default="operator session")
    ship.add_argument("--group-limit", type=int, default=40)
    ship.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    if args.command == "packets":
        return packets(args.out, args.slug, args.sample)
    return publish(args)


if __name__ == "__main__":
    raise SystemExit(main())
