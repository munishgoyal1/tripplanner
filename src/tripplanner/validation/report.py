"""The audit, in a shape something other than a terminal can read.

The printed report answers "what is wrong" and deliberately loses everything
needed to go and look: it keeps one exemplar message per group and no record
id, because a person reading a terminal cannot click anything anyway.

This module keeps the losses out. Every finding carries the record it came from
and, where that record still exists in an emulator database, the identity and
trip id needed to open it in the product UI. Rules that fired zero times are
included on purpose -- a rule nobody has seen fire is a fact about the harness,
not an absence.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tripplanner.validation.corpus import COHORTS, CorpusRecord
from tripplanner.validation.findings import Group, group, new_groups, stale_keys
from tripplanner.validation.observations import observe
from tripplanner.validation.quality import empty_ratings
from tripplanner.validation.quality import report as quality_report
from tripplanner.validation.registry import registry
from tripplanner.validation.runner import AuditResult

REPORT_VERSION = 4
REPORT_FILE = "audit-report.json"
REPORTS_DIR = Path("audit") / "reports"
LATEST_FILE = Path("audit") / "latest.json"
INDEX_FILE = Path("audit") / "index.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git_state(repo_root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""

    return {
        "sha": git("rev-parse", "HEAD"),
        "short_sha": git("rev-parse", "--short=8", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
    }


def _summary_markdown(payload: dict[str, Any], report_path: Path) -> str:
    comparison = payload["comparison"]
    lines = [
        f"# Trip Audit - {payload['generated_at']}",
        "",
        f"- Commit: `{payload['code']['short_sha']}`"
        + (" (dirty worktree)" if payload["code"]["dirty"] else ""),
        f"- Corpus: {payload['corpus']['executive_size']} current logical trips "
        f"({payload['corpus']['raw_size']} raw records)",
        f"- Findings: {len(payload['groups'])} groups across "
        f"{sum(item['trips'] for item in payload['rules'])} affected rule-trip pairs",
        f"- Comparison: {comparison['status']} - {comparison['reason']}",
        f"- Detailed report: `{report_path.name}`",
        "",
        "## Movement",
        "",
        f"- New groups: {len(comparison['new_groups'])}",
        f"- Resolved groups: {len(comparison['resolved_groups'])}",
        f"- Improved rules: {len(comparison['improved_rules'])}",
        f"- Worsened rules: {len(comparison['worsened_rules'])}",
        "",
        "## Highest-impact rules",
        "",
    ]
    failed = sorted(payload["rules"], key=lambda item: (-item["trips"], item["code"]))
    for item in failed[:10]:
        rate = 100 * item["trips"] / item["evaluated"] if item["evaluated"] else 0
        lines.append(
            f"- `{item['code']}`: {item['trips']}/{item['evaluated']} evaluated trips "
            f"failed ({rate:.1f}%) - {item['title']}"
        )
    return "\n".join(lines) + "\n"


def _index_entry(payload: dict[str, Any], report_path: Path) -> dict[str, Any]:
    return {
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "sha": payload["code"]["sha"],
        "short_sha": payload["code"]["short_sha"],
        "dirty": payload["code"]["dirty"],
        "report": str(report_path),
        "corpus_fingerprint": payload["corpus"]["fingerprint"],
        "rule_fingerprint": payload["rule_fingerprint"],
        "executive_size": payload["corpus"]["executive_size"],
        "groups": len(payload["groups"]),
        "comparison_status": payload["comparison"]["status"],
        "new_groups": len(payload["comparison"]["new_groups"]),
        "resolved_groups": len(payload["comparison"]["resolved_groups"]),
    }


def generation_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    """Summarize which code revisions produced reusable generated trips."""
    produced = [item for item in manifest.get("produced", []) if isinstance(item, dict)]
    commits: dict[str, int] = {}
    runs: dict[str, int] = {}
    unattributed = 0
    for item in produced:
        commit = str(item.get("generated_by_commit") or "")
        run_id = str(item.get("generation_run_id") or "")
        if commit:
            commits[commit] = commits.get(commit, 0) + 1
        else:
            unattributed += 1
        if run_id:
            runs[run_id] = runs.get(run_id, 0) + 1
    return {
        "trips": len(produced),
        "by_commit": commits,
        "by_run": runs,
        "unattributed_pre_provenance": unattributed,
    }


def save_report(
    repo_root: Path,
    payload: dict[str, Any],
    *,
    code_root: Path | None = None,
) -> Path:
    """Save the inspector snapshot and an immutable, dated audit report."""
    generated_at = datetime.fromisoformat(str(payload["generated_at"]))
    code = _git_state(code_root or repo_root)
    payload["code"] = code
    generated_for_commit = int(
        (payload.get("generation") or {}).get("by_commit", {}).get(code["sha"], 0)
    )
    payload["evidence"]["fresh_generation"] = {
        "status": "complete" if generated_for_commit else "not_run",
        "trips_for_audited_commit": generated_for_commit,
    }
    run_name = f"{generated_at.strftime('%Y-%m-%dT%H%M%S.%fZ')}-{code['short_sha'] or 'unknown'}"
    payload["run_id"] = run_name
    run_directory = repo_root / REPORTS_DIR / generated_at.strftime("%Y/%m") / run_name
    history_path = run_directory / "report.json"
    _write_json(history_path, payload)
    _write_json(repo_root / LATEST_FILE, payload)
    summary_path = run_directory / "summary.md"
    summary_path.write_text(_summary_markdown(payload, history_path), encoding="utf-8")
    index_path = repo_root / INDEX_FILE
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {"version": 1, "runs": []}
    runs = [item for item in index.get("runs", []) if item.get("run_id") != run_name]
    runs.append(_index_entry(payload, history_path.relative_to(repo_root)))
    ordered = sorted(runs, key=lambda item: item["generated_at"])
    _write_json(index_path, {"version": 1, "runs": ordered})
    return history_path


def _record_entry(record: CorpusRecord, finding_counts: dict[str, int]) -> dict[str, Any]:
    plan = record.plan
    itinerary = plan.get("day_wise_itinerary")
    # Debug-store revisions are historical states that were never in a database,
    # so they can be reported but not opened.
    user_id = str(plan.get("user_id") or "")
    trip_id = str(plan.get("trip_id") or "")
    return {
        "id": record.id,
        "logical_trip_id": record.logical_trip_id,
        "provenance": record.provenance,
        "cohorts": record.cohorts,
        "source": record.source,
        "destination": record.destination,
        "days": len(itinerary) if isinstance(itinerary, list) else 0,
        "departure_date": str(plan.get("departure_date") or ""),
        "return_date": str(plan.get("return_date") or ""),
        "user_id": user_id,
        "trip_id": trip_id,
        "openable": bool(user_id and trip_id),
        "findings": finding_counts.get(record.id, 0),
        "provenance_links": [
            {
                "id": link.id,
                "provenance": link.provenance,
                "source": link.source,
                "user_id": link.user_id,
                "trip_id": link.trip_id,
            }
            for link in record.links
        ],
    }


def _group_entry(item: Group, new_keys: set[str], accepted: dict[str, Any]) -> dict[str, Any]:
    known = accepted.get(item.key)
    return {
        "key": item.key,
        "rule": item.rule,
        "symptom": item.symptom,
        "count": item.count,
        "new": item.key in new_keys,
        "accepted_on": (known or {}).get("accepted_on", ""),
        "provenances": item.provenances,
        "example": item.exemplar.message,
        "findings": [
            {
                "record_id": finding.record_id,
                "day": finding.day,
                "provenance": finding.provenance,
                "message": finding.message,
            }
            for finding in item.findings
        ],
    }


def _previous_rule_counts(previous: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Hits and affected trips per rule, as the last audit recorded them."""
    out: dict[str, dict[str, int]] = {}
    for entry in previous.get("rules") or []:
        if isinstance(entry, dict) and entry.get("code"):
            out[str(entry["code"])] = {
                "hits": int(entry.get("hits") or 0),
                "trips": int(entry.get("trips") or 0),
            }
    return out


def build_report(
    result: AuditResult,
    baseline: dict[str, Any],
    previous: dict[str, Any] | None = None,
    quality_ratings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything the inspector needs, resolved and self-contained."""
    accepted = dict(baseline.get("accepted") or {})
    executive_records = [record for record in result.records if record.executive]
    executive_ids = {record.id for record in executive_records}
    executive_findings = [
        finding for finding in result.findings if finding.record_id in executive_ids
    ]
    executive_groups = group(executive_findings)
    new_keys = {item.key for item in new_groups(executive_groups, baseline)}

    finding_counts: dict[str, int] = {}
    for finding in result.findings:
        finding_counts[finding.record_id] = finding_counts.get(finding.record_id, 0) + 1

    def _hits(findings: list[Any]) -> dict[str, int]:
        tally: dict[str, int] = {}
        for finding in findings:
            tally[finding.rule] = tally.get(finding.rule, 0) + 1
        return tally

    def _affected(findings: list[Any]) -> dict[str, set[str]]:
        affected: dict[str, set[str]] = {}
        for finding in findings:
            affected.setdefault(finding.rule, set()).add(finding.record_id)
        return affected

    hits = _hits(executive_findings)
    affected = _affected(executive_findings)
    raw_hits = _hits(result.findings)
    raw_affected = _affected(result.findings)

    was = _previous_rule_counts(previous or {})
    rules = registry()

    def _denominators(rule: Any, records: list[CorpusRecord]) -> dict[str, int]:
        eligible = [record for record in records if record.executive]
        evaluated = [
            record for record in eligible if not rule.requires_places or bool(record.places)
        ]
        evaluated_ids = {record.id for record in evaluated}
        return {
            "eligible": len(eligible),
            "evaluated": len(evaluated),
            "failed": len(affected.get(rule.code, set()).intersection(evaluated_ids)),
            "unverified": len(eligible) - len(evaluated),
        }

    corpus_fingerprint = hashlib.sha256(
        "\n".join(sorted(record.logical_trip_id for record in executive_records)).encode()
    ).hexdigest()[:16]
    rule_fingerprint = hashlib.sha256(
        "\n".join(
            f"{rule.code}|{rule.severity}|{rule.statement}|{rule.evaluated_in}"
            for rule in rules
        ).encode()
    ).hexdigest()[:16]
    previous_corpus = str((previous or {}).get("corpus", {}).get("fingerprint") or "")
    previous_rules = str((previous or {}).get("rule_fingerprint") or "")
    comparable = bool(
        previous_corpus
        and previous_rules
        and previous_corpus == corpus_fingerprint
        and previous_rules == rule_fingerprint
    )
    previous_groups = {str(item.get("key")) for item in (previous or {}).get("groups", [])}
    current_groups = {item.key for item in executive_groups}
    previous_by_rule = {
        str(item.get("code")): item for item in (previous or {}).get("rules", [])
    }
    current_trip_counts = {rule.code: len(affected.get(rule.code, ())) for rule in rules}
    improved = sorted(
        code
        for code, count in current_trip_counts.items()
        if comparable and count < int(previous_by_rule.get(code, {}).get("trips") or 0)
    )
    worsened = sorted(
        code
        for code, count in current_trip_counts.items()
        if comparable and count > int(previous_by_rule.get(code, {}).get("trips") or 0)
    )

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "compared_with": str((previous or {}).get("generated_at") or ""),
        "evidence": {
            "deterministic_rules": "complete",
            "historical_corpus_replay": "complete",
            "fresh_generation": {"status": "not_run", "trips_for_audited_commit": 0},
        },
        "rule_fingerprint": rule_fingerprint,
        "comparison": {
            "status": "comparable" if comparable else "not_comparable",
            "reason": (
                "same logical corpus and rule contract"
                if comparable
                else (
                    "the previous report used a different corpus/rule contract "
                    "or lacks identity metadata"
                )
            ),
            "new_groups": sorted(current_groups - previous_groups) if comparable else [],
            "resolved_groups": sorted(previous_groups - current_groups) if comparable else [],
            "persistent_groups": (
                sorted(current_groups.intersection(previous_groups)) if comparable else []
            ),
            "improved_rules": improved,
            "worsened_rules": worsened,
        },
        "corpus": {
            "size": result.corpus_size,
            "raw_size": result.raw_corpus_size,
            "executive_size": len(executive_records),
            "fingerprint": corpus_fingerprint,
            "provenance": result.provenance_mix,
            "cohorts": result.cohort_mix,
            "sources": result.sources,
            "skipped": result.skipped,
        },
        "rules": [
            {
                "code": rule.code,
                "title": rule.title,
                "statement": rule.statement,
                "severity": rule.severity,
                "evaluated_in": rule.evaluated_in,
                **_denominators(rule, executive_records),
                "hits": hits.get(rule.code, 0),
                "trips": len(affected.get(rule.code, ())),
                "raw_hits": raw_hits.get(rule.code, 0),
                "raw_trips": len(raw_affected.get(rule.code, ())),
                "by_cohort": {
                    cohort: _denominators(
                        rule,
                        [record for record in result.records if cohort in record.cohorts],
                    )
                    for cohort in COHORTS
                },
                "was_hits": was.get(rule.code, {}).get("hits", 0),
                "was_trips": was.get(rule.code, {}).get("trips", 0),
                "first_seen": rule.code not in was,
            }
            for rule in rules
        ],
        "groups": [_group_entry(item, new_keys, accepted) for item in executive_groups],
        "retired": stale_keys(executive_groups, baseline),
        "observations": [
            {"label": item.label, "value": item.value, "detail": item.detail}
            for item in observe(executive_records)
        ],
        "quality": quality_report(executive_records, quality_ratings or empty_ratings()),
        "records": [_record_entry(record, finding_counts) for record in result.records],
    }
