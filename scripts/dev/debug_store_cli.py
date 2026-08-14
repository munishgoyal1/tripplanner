"""Inspect, maintain, restore, and tear down the local debug trip store.

    python scripts/dev/debug_store_cli.py show "maui" --days 30
    python scripts/dev/debug_store_cli.py maintain
    python scripts/dev/debug_store_cli.py restore --sandbox 2 --days 7
    python scripts/dev/debug_store_cli.py clear --confirm CLEAR_DEBUG_STORE
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tripplanner import debug_store  # noqa: E402

LOCAL_DATABASE = "tripplanner-local"
SANDBOX_PREFIX = "tripplanner-sbx-"
LIVE_DATABASES = {"tripplanner-canary", "tripplanner-prod"}
EMULATOR_ENDPOINT = "https://localhost:8081"
EMULATOR_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)
TRIPS_CONTAINER = "trips"
USERS_CONTAINER = "users"
PLACES_CONTAINER = "places_cache"
PLACES_PARTITION = "_shared"
PREFERENCES_DOC_ID = "preferences"
CHAT_OPERATIONS_DOC_ID = "chat_operations"


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _within_days(record: dict[str, Any], days: int | None) -> bool:
    if days is None:
        return True
    seen = _parse_iso(str(record.get("last_seen_at") or ""))
    if seen is None:
        return False
    return seen >= datetime.now(UTC) - timedelta(days=days)


def _haystack(record: dict[str, Any]) -> str:
    descriptor = record.get("descriptor") or {}
    parts = [
        str(record.get("archive_no") or ""),
        str(record.get("trip_id") or ""),
        str(descriptor.get("destination") or ""),
        str(descriptor.get("auto_summary") or ""),
        str(descriptor.get("label") or ""),
        str(descriptor.get("month_year") or ""),
        " ".join(str(note) for note in descriptor.get("notes") or []),
        " ".join(str(word) for word in descriptor.get("keywords") or []),
    ]
    return " ".join(parts).lower()


def _matches(record: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    # A bare number is an archive reference, never a substring to hunt for.
    if needle.isdigit():
        return int(needle) == int(record.get("archive_no") or 0)
    return all(token in _haystack(record) for token in needle.split())


def _select(query: str, days: int | None) -> list[tuple[Path, dict[str, Any]]]:
    found = [
        (path, record)
        for path, record in debug_store.iter_records()
        if _matches(record, query) and _within_days(record, days)
    ]
    found.sort(key=lambda item: str(item[1].get("last_seen_at") or ""), reverse=True)
    return found


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    selected = _select(args.query, args.days)
    if args.json:
        print(json.dumps([record for _, record in selected], indent=2, default=str))
        return 0
    if not selected:
        print("No archived trips matched.")
        return 0
    print(f"{len(selected)} archived trip(s):\n")
    for _, record in selected:
        descriptor = record.get("descriptor") or {}
        label = str(descriptor.get("label") or "")
        revisions = len(record.get("revisions") or [])
        print(f"  #{int(record.get('archive_no') or 0):04d}  {descriptor.get('auto_summary', '')}")
        print(
            f"          trip={record.get('trip_id')}  run={record.get('created_date')}  "
            f"revisions={revisions}  last_seen={record.get('last_seen_at')}"
        )
        if label:
            print(f"          label={label}")
    return 0


# ---------------------------------------------------------------------------
# maintain
# ---------------------------------------------------------------------------


def cmd_maintain(args: argparse.Namespace) -> int:
    root = debug_store.users_root()
    if not root.exists():
        print("Debug store is empty; nothing to maintain.")
        return 0

    unreadable = [
        path
        for path in sorted(root.glob("*/*.json"))
        if debug_store.load_record(path) is None
    ]
    records = debug_store.iter_records()

    renumbered = 0
    seen_numbers: set[int] = set()
    highest = max((int(r.get("archive_no") or 0) for _, r in records), default=0)
    for path, record in records:
        number = int(record.get("archive_no") or 0)
        if number in seen_numbers or number <= 0:
            highest += 1
            record["archive_no"] = highest
            target = path.with_name(
                debug_store.file_name(
                    highest, str(record.get("trip_id") or ""), str(record.get("created_date") or "")
                )
            )
            debug_store.atomic_write_json(target, record, indent=2)
            if target != path:
                path.unlink(missing_ok=True)
            renumbered += 1
            seen_numbers.add(highest)
        else:
            seen_numbers.add(number)

    refreshed = 0
    trimmed = 0
    stale: list[int] = []
    for path, record in debug_store.iter_records():
        revisions = list(record.get("revisions") or [])
        if not revisions:
            continue
        changed = False
        if len(revisions) > debug_store.MAX_REVISIONS:
            record["revisions"] = revisions[-debug_store.MAX_REVISIONS :]
            trimmed += 1
            changed = True
        plan = revisions[-1].get("plan") or {}
        descriptor = record.get("descriptor") or {}
        rebuilt = {
            **debug_store.describe(plan),
            "label": str(descriptor.get("label") or ""),
            "notes": list(descriptor.get("notes") or []),
        }
        if rebuilt != descriptor:
            record["descriptor"] = rebuilt
            refreshed += 1
            changed = True
        if int(record.get("schema_version") or 0) != debug_store.SCHEMA_VERSION:
            stale.append(int(record.get("archive_no") or 0))
        if changed:
            debug_store.atomic_write_json(path, record, indent=2)

    if args.prune_stale and stale:
        for path, record in debug_store.iter_records():
            if int(record.get("archive_no") or 0) in set(stale):
                path.unlink(missing_ok=True)
        print(f"Pruned {len(stale)} stale record(s).")

    total = len(debug_store.iter_records())
    print(f"Debug store: {total} archived trip(s) at {debug_store.store_root()}")
    print(f"  descriptors refreshed : {refreshed}")
    print(f"  numbers reassigned    : {renumbered}")
    print(f"  revision lists trimmed: {trimmed}")
    print(f"  unreadable files      : {len(unreadable)}")
    if stale and not args.prune_stale:
        print(f"  stale schema records  : {len(stale)} (re-run with --prune-stale to delete)")
    return 0


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def _worktrees_dir() -> Path:
    root = debug_store.repo_root()
    if root.parent.name == "tripplanner.worktrees":
        return root.parent
    return root.parent / "tripplanner.worktrees"


def _database_for_sandbox(number: int) -> str:
    if number <= 0:
        return LOCAL_DATABASE
    registry = _worktrees_dir() / "sandboxes.json"
    if not registry.exists():
        raise SystemExit(_fail(f"no sandbox registry at {registry}"))
    entries = json.loads(registry.read_text(encoding="utf-8"))
    for entry in entries:
        if int(entry.get("slot", -1)) + 1 == number:
            return str(entry["database"])
    known = ", ".join(f"#{int(e.get('slot', 0)) + 1} {e.get('slug')}" for e in entries)
    raise SystemExit(_fail(f"sandbox #{number} is not registered. Known: {known}"))


def _assert_restorable(database: str) -> str:
    name = database.strip()
    if name.lower() in LIVE_DATABASES:
        raise SystemExit(_fail(f"refusing to write to live database '{name}'"))
    if name != LOCAL_DATABASE and not name.startswith(SANDBOX_PREFIX):
        raise SystemExit(_fail(f"'{name}' is neither the local nor a sandbox database"))
    return name


def _emulator_database(name: str):
    import warnings
    from urllib.parse import urlparse

    from azure.cosmos import CosmosClient, PartitionKey
    from urllib3.exceptions import InsecureRequestWarning

    if urlparse(EMULATOR_ENDPOINT).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit(_fail("restore only targets the loopback Cosmos DB Emulator"))
    warnings.filterwarnings(
        "ignore", category=InsecureRequestWarning, module=r"urllib3\.connectionpool"
    )
    client = CosmosClient(
        EMULATOR_ENDPOINT, credential=EMULATOR_KEY, connection_mode="Gateway",
        connection_verify=False,
    )
    database = client.create_database_if_not_exists(id=name)
    for container in (TRIPS_CONTAINER, USERS_CONTAINER, PLACES_CONTAINER):
        database.create_container_if_not_exists(
            id=container, partition_key=PartitionKey(path="/user_id")
        )
    return database


def _restore_bundle(database, record: dict[str, Any], user_id: str) -> dict[str, int]:
    """Rehydrate chat, preferences, and cached places for one archived trip."""
    from tripplanner.web.places_cache import _doc_id  # noqa: PLC2701 - shared id scheme

    bundle = record.get("bundle") or {}
    written = {"chat": 0, "preferences": 0, "places": 0}
    users = database.get_container_client(USERS_CONTAINER)

    chat = bundle.get("chat") or {}
    for bucket, body in (chat.get("buckets") or {}).items():
        if isinstance(body, dict) and body:
            users.upsert_item(body={**body, "id": f"chat_{bucket}", "user_id": user_id})
            written["chat"] += 1
    operations = chat.get("operations") or {}
    if operations:
        users.upsert_item(
            body={**operations, "id": CHAT_OPERATIONS_DOC_ID, "user_id": user_id}
        )

    preferences = bundle.get("preferences")
    if isinstance(preferences, dict) and preferences:
        users.upsert_item(
            body={**preferences, "id": PREFERENCES_DOC_ID, "user_id": user_id}
        )
        written["preferences"] += 1

    places = bundle.get("places") or {}
    if places:
        container = database.get_container_client(PLACES_CONTAINER)
        for key, entry in places.items():
            container.upsert_item(
                body={
                    "key": key,
                    "entry": entry,
                    "id": _doc_id(key),
                    "user_id": PLACES_PARTITION,
                }
            )
            written["places"] += 1
    return written


def cmd_restore(args: argparse.Namespace) -> int:
    days = None if args.all else args.days
    selected = _select(args.trip, days)
    if not selected:
        print("Nothing matched; no trips restored.")
        return 0
    database_name = _assert_restorable(args.database or _database_for_sandbox(args.sandbox))
    database = _emulator_database(database_name)
    container = database.get_container_client(TRIPS_CONTAINER)
    written = 0
    totals = {"chat": 0, "preferences": 0, "places": 0}
    for _, record in selected:
        revisions = record.get("revisions") or []
        if not revisions:
            continue
        plan = dict(revisions[-1].get("plan") or {})
        trip_id = str(record.get("trip_id") or "")
        user_id = str(args.as_user or record.get("user_id") or "")
        if not trip_id or not user_id:
            continue
        container.upsert_item(body={**plan, "id": trip_id, "user_id": user_id})
        written += 1
        if not args.no_bundle:
            for key, count in _restore_bundle(database, record, user_id).items():
                totals[key] += count
        print(f"  restored #{int(record.get('archive_no') or 0):04d} {trip_id}")
    print(f"Restored {written} trip(s) into {database_name}.")
    if not args.no_bundle:
        print(
            f"  bundle: {totals['chat']} chat bucket(s), "
            f"{totals['preferences']} preference doc(s), {totals['places']} cached place(s)"
        )
    return 0


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def cmd_clear(args: argparse.Namespace) -> int:
    root = debug_store.store_root()
    if args.confirm != "CLEAR_DEBUG_STORE":
        return _fail("pass --confirm CLEAR_DEBUG_STORE to tear the store down")
    if not root.exists():
        print("Debug store is already empty.")
        return 0
    count = len(debug_store.iter_records())
    shutil.rmtree(root)
    print(f"Removed {count} archived trip(s) and deleted {root}.")
    print("Numbering restarts at 1 on the next capture.")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="List or search archived trips.")
    show.add_argument("query", nargs="?", default="")
    show.add_argument("--days", type=int, default=None)
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    maintain = sub.add_parser("maintain", help="Repair, renumber, and report on the store.")
    maintain.add_argument("--prune-stale", action="store_true")
    maintain.set_defaults(func=cmd_maintain)

    restore = sub.add_parser("restore", help="Restore archived trips into an emulator.")
    restore.add_argument("sandbox", nargs="?", type=int, default=0, help="0 = primary master")
    restore.add_argument("days", nargs="?", type=int, default=7)
    restore.add_argument("--all", action="store_true")
    restore.add_argument("--trip", default="")
    restore.add_argument("--as-user", default="")
    restore.add_argument("--database", default="", help="Target database instead of a sandbox slot")
    restore.add_argument("--no-bundle", action="store_true", help="Trip documents only")
    restore.set_defaults(func=cmd_restore)

    clear = sub.add_parser("clear", help="Delete the whole store.")
    clear.add_argument("--confirm", default="")
    clear.set_defaults(func=cmd_clear)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
