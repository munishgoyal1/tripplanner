"""Trips from a lane's emulator database, kept where the lane cannot take them.

Discarding a sandbox drops its database, and roughly a third of what the audit
reads lives only there. The debug store already survives, because it is
committed; trips that only ever existed in an emulator did not.

One file per database, so two lanes never write the same file and a discarded
lane's evidence stays readable under the name it was collected from.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from tripplanner.validation.emulator import assert_sandbox_database, read_trips

SNAPSHOT_DIR = "lane-trips"
SNAPSHOT_VERSION = 1
#: Docs that are not trips; the audit only wants plans.
_REQUIRED_ANY = ("destination", "trip_id")


def snapshot_dir(corpus_root: Path) -> Path:
    return corpus_root / SNAPSHOT_DIR


def snapshot_path(corpus_root: Path, database: str) -> Path:
    safe = re.sub(r"[^a-z0-9.-]+", "-", database.strip().lower())
    return snapshot_dir(corpus_root) / f"{safe}.json"


def _is_plan(document: Any) -> bool:
    return isinstance(document, dict) and any(document.get(key) for key in _REQUIRED_ANY)


def save(corpus_root: Path, database: str) -> int:
    """Write every trip in one sandbox database to its own snapshot file."""
    name = assert_sandbox_database(database)
    trips = [document for document in read_trips(name) if _is_plan(document)]
    path = snapshot_path(corpus_root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "database": name,
        "count": len(trips),
        # Ordered so re-saving unchanged trips produces no diff.
        "trips": sorted(trips, key=lambda trip: str(trip.get("id") or trip.get("trip_id") or "")),
    }
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = None
    if isinstance(existing, dict):
        existing = {key: value for key, value in existing.items() if key != "saved_at"}
    if existing == payload:
        return len(trips)
    payload = {
        "version": payload["version"],
        "database": payload["database"],
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": payload["count"],
        "trips": payload["trips"],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(trips)


def load(corpus_root: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    """Every saved lane snapshot, as (database, trips)."""
    directory = snapshot_dir(corpus_root)
    if not directory.exists():
        return []
    found: list[tuple[str, list[dict[str, Any]]]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        trips = payload.get("trips") if isinstance(payload, dict) else None
        if isinstance(trips, list):
            found.append((str(payload.get("database") or path.stem), trips))
    return found
