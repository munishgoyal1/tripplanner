"""Acquire and deduplicate trip evaluation inputs from local sources."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from tripplanner.evals.contracts import _NON_SEMANTIC_KEYS as _NON_SEMANTIC_KEYS
from tripplanner.evals.contracts import CLONE as CLONE
from tripplanner.evals.contracts import COHORTS as COHORTS
from tripplanner.evals.contracts import GENERATED_FINAL as GENERATED_FINAL
from tripplanner.evals.contracts import GOLDEN as GOLDEN
from tripplanner.evals.contracts import MUTATED as MUTATED
from tripplanner.evals.contracts import OWNER_CURRENT as OWNER_CURRENT
from tripplanner.evals.contracts import PARTIAL as PARTIAL
from tripplanner.evals.contracts import PROVENANCES as PROVENANCES
from tripplanner.evals.contracts import REAL as REAL
from tripplanner.evals.contracts import REFERENCE as REFERENCE
from tripplanner.evals.contracts import REVISION as REVISION
from tripplanner.evals.contracts import REVISION_COHORT as REVISION_COHORT
from tripplanner.evals.contracts import SYNTHETIC as SYNTHETIC
from tripplanner.evals.contracts import TEMPLATE as TEMPLATE
from tripplanner.evals.contracts import CorpusRecord as CorpusRecord
from tripplanner.evals.contracts import ProvenanceLink as ProvenanceLink
from tripplanner.evals.contracts import _is_plan as _is_plan
from tripplanner.evals.contracts import _semantic_value as _semantic_value
from tripplanner.evals.contracts import is_partial as is_partial
from tripplanner.evals.contracts import semantic_fingerprint as semantic_fingerprint


def from_debug_store(root: Path | None = None, *, revisions: bool = True) -> list[CorpusRecord]:
    """Every archived planning run, and optionally each state it passed through.

    The intermediate states are the point: a plan is usually correct once it is
    finished, and wrong somewhere in the middle.
    """
    from tripplanner import debug_store

    records: list[CorpusRecord] = []
    for path, record in debug_store.iter_records(root):
        places = dict(((record.get("bundle") or {}).get("places")) or {})
        history = [entry for entry in (record.get("revisions") or []) if isinstance(entry, dict)]
        if not history:
            continue
        archive_no = record.get("archive_no")
        trip_id = str(record.get("trip_id") or path.stem)
        last = len(history) - 1
        for index, entry in enumerate(history):
            plan = entry.get("plan")
            if not _is_plan(plan):
                continue
            if index != last and not revisions:
                continue
            suffix = "" if index == last else f"#r{index + 1}"
            records.append(
                CorpusRecord(
                    id=f"{archive_no or '?'}:{trip_id}{suffix}",
                    provenance=REAL if index == last else REVISION,
                    source=str(path),
                    plan=plan,
                    places=places,
                )
            )
    return records


def from_emulator(database: str, *, user_id: str = "") -> list[CorpusRecord]:
    """Trips stored in one sandbox emulator database.

    Refuses anything that is not a sandbox database, reusing the same rule the
    seeding tool applies, so an audit can never read live data.
    """
    from tripplanner.harness.sources.emulator import read_places, read_trips

    places = read_places(database)
    return [
        CorpusRecord(
            id=f"{database}:{trip.get('id') or trip.get('trip_id') or '?'}",
            provenance=REAL,
            source=database,
            plan=trip,
            places=places,
        )
        for trip in read_trips(database, user_id=user_id)
        if _is_plan(trip)
    ]


def from_lane_snapshots(corpus_root: Path) -> list[CorpusRecord]:
    """Trips saved out of a sandbox database before it could be discarded.

    Deduplication drops these again when the lane is still alive, so a snapshot
    costs nothing until the database it came from is gone.
    """
    from tripplanner.harness.sources import lane_trips as lane_trips

    records: list[CorpusRecord] = []
    for database, trips in lane_trips.load(corpus_root):
        records.extend(
            CorpusRecord(
                id=f"{database}:{trip.get('id') or trip.get('trip_id') or index}",
                provenance=REAL,
                source=f"{database} (saved)",
                plan=trip,
            )
            for index, trip in enumerate(trips)
            if _is_plan(trip)
        )
    return records


def from_fixtures(directory: Path) -> list[CorpusRecord]:
    """Pinned known shapes captured by ``sandbox_seed capture``."""
    records: list[CorpusRecord] = []
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        trips = payload.get("trips") if isinstance(payload, dict) else None
        for index, trip in enumerate(trips or []):
            if not _is_plan(trip):
                continue
            records.append(
                CorpusRecord(
                    id=f"{path.stem}:{trip.get('id') or index}",
                    provenance=GOLDEN,
                    source=str(path),
                    plan=trip,
                )
            )
    return records


def from_generated_finals(
    directory: Path, *, places: dict[str, Any] | None = None
) -> list[CorpusRecord]:
    """Committed final plans produced by the validation request matrix."""
    records: list[CorpusRecord] = []
    if not directory.exists():
        return records
    manifest_path = directory.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    produced = manifest.get("produced", []) if isinstance(manifest, dict) else []
    metadata = {
        entry["slug"]: entry for entry in produced
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
    }
    for path in sorted(directory.glob("*.json")):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_plan(plan):
            continue
        entry = metadata.get(path.stem, {})
        records.append(
            CorpusRecord(
                id=f"generated:{path.stem}",
                provenance=SYNTHETIC,
                source=str(path),
                plan=plan,
                places=places or {},
                case_id=f"generated:{path.stem}",
                request=str(entry.get("request") or ""),
                preferences=dict(plan.get("preferences_snapshot") or {}),
                generation={
                    key: entry[key] for key in (
                        "generated_by_commit", "generation_run_id", "at", "model",
                        "scenario_expectations", "budget_evidence_required",
                    ) if key in entry
                },
            )
        )
    return records


def from_json(path: Path) -> CorpusRecord:
    """Read an explicit trip or evaluation envelope without contacting any source."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Evaluation input must be a JSON object")
    wrapped = "plan" in payload
    plan = payload.get("plan") if wrapped else payload
    if not isinstance(plan, dict) or not _is_plan(plan):
        raise ValueError("Evaluation input needs a trip plan with a destination or trip_id")
    context = payload if wrapped else {}
    for key in ("preferences", "places", "generation"):
        if key in context and not isinstance(context[key], dict):
            raise ValueError(f"{key} must be an object")
    steps = context.get("steps", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise ValueError("steps must be an array of objects")
    case_id = str(context.get("case_id") or path.resolve())
    return CorpusRecord(
        id=f"input:{path.resolve()}", provenance=REAL, source=str(path.resolve()), plan=plan,
        places=context.get("places", {}), case_id=case_id,
        request=str(context.get("request") or ""),
        preferences=context.get("preferences", dict(plan.get("preferences_snapshot") or {})),
        final_reply=str(context.get("final_reply") or ""), steps=tuple(steps),
        generation=context.get("generation", {}),
    )


def deduplicate(records: list[CorpusRecord]) -> list[CorpusRecord]:
    """Collapse semantic clones while retaining every persisted occurrence.

    The same trip reaches the corpus from the debug store and from the emulator;
    counting it twice would weight one trip's defects above the rest.
    """
    unique: dict[str, CorpusRecord] = {}
    for record in records:
        # Legacy context-free copies still collapse; distinct requests/producers do not.
        context = {key: value for key, value in record.evaluation_input().items() if key != "plan"}
        fingerprint = record.logical_trip_id + json.dumps(
            {"case_id": record.case_id, **context}, sort_keys=True, ensure_ascii=False,
        )
        previous = unique.get(fingerprint)
        if previous is None:
            unique[fingerprint] = replace(record, provenance_links=record.links)
            continue
        representative = record
        if previous.provenance != REVISION or record.provenance == REVISION:
            representative = previous
        unique[fingerprint] = replace(
            representative,
            places={**previous.places, **record.places},
            provenance_links=(*previous.links, *record.links),
        )
    return list(unique.values())


def counts_by_provenance(records: list[CorpusRecord]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for record in records:
        for link in record.links:
            tally[link.provenance] = tally.get(link.provenance, 0) + 1
    return tally


def counts_by_cohort(records: list[CorpusRecord]) -> dict[str, int]:
    return {
        cohort: sum(cohort in record.cohorts for record in records)
        for cohort in COHORTS
    }


def iter_plans(records: list[CorpusRecord]) -> Iterator[dict[str, Any]]:
    for record in records:
        yield record.plan
