"""The grounding a corpus was planned against, kept where a sandbox cannot take it.

Trip plans are only half of what a corpus run produces. The other half is the
Places data behind them -- coordinates, opening hours, ratings, photo references
-- which is what makes a stored trip renderable and checkable offline. That half
lived only in one sandbox's emulator database, so it died with the worktree and
every other lane re-fetched the same places from Google at real cost.

This module moves it into the repository alongside the trips, and back into any
sandbox on demand. The file is the durable copy; a database is a warm cache of
it.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from tripplanner.validation.emulator import (
    EmulatorUnreachableError,
    _client,
    assert_sandbox_database,
    read_places,
)

CACHE_FILE = "places.json"
CACHE_VERSION = 1
_CONTAINER = "places_cache"
_PARTITION = "_shared"  # places are global, not per-user
#: Signed photo URLs expire within the hour and are re-derived from photo_refs.
_VOLATILE_FIELDS = frozenset({"photo_urls", "__photos_at__"})
#: Google returns ten photo references per place and the app renders at most
#: three, but each reference is ~500 characters -- four fifths of an unfiltered
#: export. Mirrors places_cache._MAX_PHOTOS_PER_PLACE; a test keeps them equal.
_MAX_PHOTO_REFS = 3


def _doc_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _worth_keeping(entry: Any) -> bool:
    """A lookup that failed is not grounding, and re-trying it is cheap."""
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("lat") or entry.get("lng") or entry.get("location"))


def _portable(entry: dict[str, Any]) -> dict[str, Any]:
    trimmed = {k: v for k, v in entry.items() if k not in _VOLATILE_FIELDS}
    refs = trimmed.get("photo_refs")
    if isinstance(refs, list) and len(refs) > _MAX_PHOTO_REFS:
        trimmed["photo_refs"] = refs[:_MAX_PHOTO_REFS]
    return trimmed


def cache_path(corpus_root: Path) -> Path:
    return corpus_root / CACHE_FILE


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    places = payload.get("places") if isinstance(payload, dict) else None
    return places if isinstance(places, dict) else {}


def save(path: Path, places: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(places),
        # Sorted so a re-export of unchanged data produces no diff.
        "places": dict(sorted(places.items())),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def collect(database: str) -> dict[str, Any]:
    """Everything worth keeping from one sandbox database's place cache."""
    return {
        key: _portable(entry)
        for key, entry in read_places(database).items()
        if _worth_keeping(entry)
    }


def merge(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Union, preferring whichever copy of a place was fetched more recently."""
    merged = dict(existing)
    for key, entry in incoming.items():
        current = merged.get(key)
        if not isinstance(current, dict):
            merged[key] = entry
            continue
        if float(entry.get("__at__") or 0) >= float(current.get("__at__") or 0):
            merged[key] = entry
    return merged


def restore(database: str, places: dict[str, Any]) -> int:
    """Seed a sandbox database's place cache from the saved file.

    Writes through the emulator client rather than ``storage_cosmos``, which
    would target whatever COSMOS_DATABASE happens to be set to and quietly
    ignore the database that was just checked.

    Timestamps are refreshed on the way in. A month-old export would otherwise
    import as already expired, and the point of restoring is to plan and render
    without calling a provider at all.
    """
    name = assert_sandbox_database(database)
    now = time.time()
    written = 0
    try:
        from azure.cosmos import PartitionKey

        # A sandbox recreated after a discard has no containers yet, which is
        # exactly when restoring matters most.
        container = _client().get_database_client(name).create_container_if_not_exists(
            id=_CONTAINER, partition_key=PartitionKey(path="/user_id")
        )
        for key, entry in places.items():
            if not _worth_keeping(entry):
                continue
            container.upsert_item(
                {
                    "id": _doc_id(key),
                    "user_id": _PARTITION,
                    "key": key,
                    "entry": {**_portable(entry), "__at__": now},
                }
            )
            written += 1
    except Exception as error:  # noqa: BLE001
        raise EmulatorUnreachableError(f"{name}: {error}") from error
    return written
