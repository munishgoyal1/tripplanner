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

from datetime import UTC, datetime
from typing import Any

from tripplanner.validation.corpus import CorpusRecord
from tripplanner.validation.findings import Group, stale_keys
from tripplanner.validation.observations import observe
from tripplanner.validation.registry import registry
from tripplanner.validation.runner import AuditResult

REPORT_VERSION = 1
REPORT_FILE = "audit-report.json"


def _record_entry(record: CorpusRecord, finding_counts: dict[str, int]) -> dict[str, Any]:
    plan = record.plan
    itinerary = plan.get("day_wise_itinerary")
    # Debug-store revisions are historical states that were never in a database,
    # so they can be reported but not opened.
    user_id = str(plan.get("user_id") or "")
    trip_id = str(plan.get("trip_id") or "")
    return {
        "id": record.id,
        "provenance": record.provenance,
        "source": record.source,
        "destination": record.destination,
        "days": len(itinerary) if isinstance(itinerary, list) else 0,
        "departure_date": str(plan.get("departure_date") or ""),
        "return_date": str(plan.get("return_date") or ""),
        "user_id": user_id,
        "trip_id": trip_id,
        "openable": bool(user_id and trip_id),
        "findings": finding_counts.get(record.id, 0),
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


def build_report(result: AuditResult, baseline: dict[str, Any]) -> dict[str, Any]:
    """Everything the inspector needs, resolved and self-contained."""
    accepted = dict(baseline.get("accepted") or {})
    new_keys = {item.key for item in result.new}

    finding_counts: dict[str, int] = {}
    for finding in result.findings:
        finding_counts[finding.record_id] = finding_counts.get(finding.record_id, 0) + 1

    hits: dict[str, int] = {}
    for item in result.groups:
        hits[item.rule] = hits.get(item.rule, 0) + item.count

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus": {
            "size": result.corpus_size,
            "provenance": result.provenance_mix,
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
                "hits": hits.get(rule.code, 0),
            }
            for rule in registry()
        ],
        "groups": [_group_entry(item, new_keys, accepted) for item in result.groups],
        "retired": stale_keys(result.groups, baseline),
        "observations": [
            {"label": item.label, "value": item.value, "detail": item.detail}
            for item in observe(result.records)
        ],
        "records": [_record_entry(record, finding_counts) for record in result.records],
    }
