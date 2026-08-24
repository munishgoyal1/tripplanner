"""One corpus of trips to validate, however each one was produced.

A trip is a trip: the checks must not care whether it came from the owner's own
planning, from a generated run, or from a mutation. Every record therefore
carries its provenance and nothing else distinguishes it, so a finding can be
attributed without the checks ever branching on where it came from.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

REAL = "real"
REVISION = "revision"
SYNTHETIC = "synthetic"
TEMPLATE = "template"
GOLDEN = "golden"
REFERENCE = "reference"
MUTATED = "mutated"

PROVENANCES = (REAL, REVISION, SYNTHETIC, TEMPLATE, GOLDEN, REFERENCE, MUTATED)

GENERATED_FINAL = "generated-final"
OWNER_CURRENT = "owner-current"
REVISION_COHORT = "revision"
PARTIAL = "partial"
CLONE = "clone"
COHORTS = (GENERATED_FINAL, OWNER_CURRENT, REVISION_COHORT, PARTIAL, CLONE)

_NON_SEMANTIC_KEYS = frozenset(
    {
        "_attachments",
        "_etag",
        "_rid",
        "_self",
        "_ts",
        "account_id",
        "created_at",
        "id",
        "revision",
        "trip_id",
        "updated_at",
        "user_id",
    }
)


@dataclass(frozen=True)
class ProvenanceLink:
    """One persisted occurrence of a semantic logical trip."""

    id: str
    provenance: str
    source: str
    user_id: str = ""
    trip_id: str = ""


@dataclass(frozen=True)
class CorpusRecord:
    """One trip plan plus enough context to render and attribute it."""

    id: str
    provenance: str
    source: str
    plan: dict[str, Any]
    #: Cached ``name|city`` place entries, so a record can be checked offline.
    places: dict[str, Any] = field(default_factory=dict)
    provenance_links: tuple[ProvenanceLink, ...] = ()

    @property
    def destination(self) -> str:
        return str(self.plan.get("destination") or "")

    @property
    def logical_trip_id(self) -> str:
        return semantic_fingerprint(self.plan)

    @property
    def links(self) -> tuple[ProvenanceLink, ...]:
        if self.provenance_links:
            return self.provenance_links
        return (
            ProvenanceLink(
                id=self.id,
                provenance=self.provenance,
                source=self.source,
                user_id=str(self.plan.get("user_id") or ""),
                trip_id=str(self.plan.get("trip_id") or self.plan.get("id") or ""),
            ),
        )

    @property
    def cohorts(self) -> tuple[str, ...]:
        links = self.links
        has_final = any(link.provenance != REVISION for link in links)
        cohorts: list[str] = []
        if not has_final:
            cohorts.append(REVISION_COHORT)
        if is_partial(self.plan):
            cohorts.append(PARTIAL)
        elif has_final:
            generated = self.provenance == SYNTHETIC or any(
                link.user_id.startswith("corpus-") for link in links
            )
            cohorts.append(GENERATED_FINAL if generated else OWNER_CURRENT)
        if len(links) > 1:
            cohorts.append(CLONE)
        return tuple(cohorts)

    @property
    def executive(self) -> bool:
        return (
            REVISION_COHORT not in self.cohorts
            and PARTIAL not in self.cohorts
            and bool({GENERATED_FINAL, OWNER_CURRENT}.intersection(self.cohorts))
        )


def _is_plan(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("destination") or value.get("trip_id"))


def _semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_value(item)
            for key, item in sorted(value.items())
            if key not in _NON_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    return value


def semantic_fingerprint(plan: dict[str, Any]) -> str:
    """Stable plan identity without account, lane, or persistence metadata."""
    encoded = json.dumps(
        _semantic_value(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def is_partial(plan: dict[str, Any]) -> bool:
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list) or not itinerary:
        return True
    days = [day for day in itinerary if isinstance(day, dict)]
    return not days or any(not isinstance(day.get("stops"), list) for day in days)


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
    from tripplanner.validation.emulator import read_places, read_trips

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
    from tripplanner.validation import lane_trips

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
    for path in sorted(directory.glob("*.json")):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_plan(plan):
            continue
        records.append(
            CorpusRecord(
                id=f"generated:{path.stem}",
                provenance=SYNTHETIC,
                source=str(path),
                plan=plan,
                places=places or {},
            )
        )
    return records


def deduplicate(records: list[CorpusRecord]) -> list[CorpusRecord]:
    """Collapse semantic clones while retaining every persisted occurrence.

    The same trip reaches the corpus from the debug store and from the emulator;
    counting it twice would weight one trip's defects above the rest.
    """
    unique: dict[str, CorpusRecord] = {}
    for record in records:
        fingerprint = record.logical_trip_id
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
