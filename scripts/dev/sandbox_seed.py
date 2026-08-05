"""Seed, drop, and capture data for local trip-planner sandboxes.

A sandbox runs against an isolated Cosmos DB Emulator database named
``tripplanner-sbx-<slug>``. This helper copies representative user content
(trips + users + shared trips) from the everyday local database into that
sandbox database so a fresh sandbox opens with realistic data, and it can drop
the sandbox database again on teardown.

It only ever talks to the loopback Cosmos DB Emulator and refuses to touch the
live canary or production databases. It is intentionally self-contained (no
imports from the app package) so it can run from any worktree.

Examples::

    python scripts/dev/sandbox_seed.py seed --database tripplanner-sbx-feat-x --if-empty
    python scripts/dev/sandbox_seed.py seed --database tripplanner-sbx-feat-x --source fixtures
    python scripts/dev/sandbox_seed.py capture --trip-id maui-7d --label S1-single-destination
    python scripts/dev/sandbox_seed.py drop --database tripplanner-sbx-feat-x
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

EMULATOR_ENDPOINT = "https://localhost:8081"
EMULATOR_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)

DEFAULT_SOURCE_DATABASE = "tripplanner-local"
# A sandbox is seeded with the owner's own account data twice: once under the
# real signed-in identity and once under a stable guest identity, so both
# signed-in and guest testing open with real trips.
DEFAULT_SEED_OWNER = "google-101851654028336975901"
SANDBOX_GUEST_USER = "web-00000000-0000-4000-8000-000000000001"
SANDBOX_PREFIX = "tripplanner-sbx-"
LIVE_DATABASE_NAMES = {"tripplanner-canary", "tripplanner-prod"}

# User content copied into a sandbox. Caches (places_cache, tool_cache) and
# audit_events are intentionally excluded — the app rebuilds caches on demand and
# a sandbox does not need production audit history.
CONTENT_CONTAINERS = ("users", "trips", "shared_trips")
PARTITION_KEY_PATH = "/user_id"
SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "sandbox-seed"


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def _assert_sandbox_database(name: str) -> str:
    lowered = name.strip().lower()
    if lowered in LIVE_DATABASE_NAMES:
        _fail(f"refusing to operate on live database '{name}'")
    if not lowered.startswith(SANDBOX_PREFIX):
        _fail(f"sandbox database must start with '{SANDBOX_PREFIX}', got '{name}'")
    return name.strip()


def _client(endpoint: str, key: str):
    from urllib.parse import urlparse

    from azure.cosmos import CosmosClient
    from urllib3.exceptions import InsecureRequestWarning

    hostname = urlparse(endpoint).hostname
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        _fail("sandbox seeding only supports the loopback Cosmos DB Emulator")
    warnings.filterwarnings(
        "ignore",
        category=InsecureRequestWarning,
        module=r"urllib3\.connectionpool",
    )
    return CosmosClient(
        endpoint, credential=key, connection_mode="Gateway", connection_verify=False
    )


def _strip_system_fields(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in SYSTEM_FIELDS}


def _ensure_containers(database) -> None:
    from azure.cosmos import PartitionKey

    for name in CONTENT_CONTAINERS:
        database.create_container_if_not_exists(
            id=name, partition_key=PartitionKey(path=PARTITION_KEY_PATH)
        )


def _read_all(database, container: str) -> list[dict[str, Any]]:
    from azure.cosmos import exceptions

    try:
        items = database.get_container_client(container).query_items(
            query="SELECT * FROM c", enable_cross_partition_query=True
        )
        return [_strip_system_fields(dict(item)) for item in items]
    except exceptions.CosmosResourceNotFoundError:
        return []


def _upsert_all(database, container: str, docs: Iterable[dict[str, Any]]) -> int:
    client = database.get_container_client(container)
    count = 0
    for doc in docs:
        client.upsert_item(body=doc)
        count += 1
    return count


def _trip_count(database) -> int:
    from azure.cosmos import exceptions

    try:
        rows = database.get_container_client("trips").query_items(
            query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
        )
        return int(next(iter(rows), 0))
    except exceptions.CosmosResourceNotFoundError:
        return 0


def _read_owner(database, container: str, owner: str) -> list[dict[str, Any]]:
    from azure.cosmos import exceptions

    try:
        items = database.get_container_client(container).query_items(
            query="SELECT * FROM c WHERE c.user_id=@u",
            parameters=[{"name": "@u", "value": owner}],
            enable_cross_partition_query=True,
        )
        return [_strip_system_fields(dict(item)) for item in items]
    except exceptions.CosmosResourceNotFoundError:
        return []


def _seed_from_local(client, target: str, source_db: str, owner: str, as_user: str) -> None:
    source = client.get_database_client(source_db)
    database = client.create_database_if_not_exists(id=target)
    _ensure_containers(database)
    total = 0
    for container in CONTENT_CONTAINERS:
        originals = _read_owner(source, container, owner)
        docs = list(originals)
        if as_user and as_user != owner:
            docs += [{**doc, "user_id": as_user} for doc in originals]
        written = _upsert_all(database, container, docs)
        total += written
        print(f"  {container}: copied {written} docs")
    print(f"Seeded {target}: {owner} + {as_user} ({total} docs).")


def _seed_from_fixtures(client, target: str, fixtures_dir: Path) -> None:
    files = sorted(fixtures_dir.glob("*.json"))
    if not files:
        print(f"No fixtures found in {fixtures_dir}; sandbox will start empty.")
        return
    database = client.create_database_if_not_exists(id=target)
    _ensure_containers(database)
    total = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for container in CONTENT_CONTAINERS:
            docs = payload.get(container, [])
            written = _upsert_all(database, container, docs)
            total += written
        print(f"  {path.name}: applied")
    print(f"Seeded {target} from {len(files)} fixture file(s) ({total} docs).")


def cmd_seed(args: argparse.Namespace) -> int:
    target = _assert_sandbox_database(args.database)
    client = _client(args.endpoint, args.key)
    if args.if_empty:
        try:
            existing = client.get_database_client(target)
            if _trip_count(existing) > 0:
                print(f"{target} already has trips; skipping seed (--if-empty).")
                return 0
        except Exception:
            pass
    if args.source == "fixtures":
        _seed_from_fixtures(client, target, args.fixtures_dir)
    else:
        _seed_from_local(client, target, args.source_database, args.owner, args.as_user)
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    from azure.cosmos import exceptions

    target = _assert_sandbox_database(args.database)
    client = _client(args.endpoint, args.key)
    try:
        client.delete_database(target)
        print(f"Dropped sandbox database {target}.")
    except exceptions.CosmosResourceNotFoundError:
        print(f"Sandbox database {target} did not exist; nothing to drop.")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    from azure.cosmos import exceptions

    client = _client(args.endpoint, args.key)
    source = client.get_database_client(args.source_database)
    try:
        trips = list(
            source.get_container_client("trips").query_items(
                query="SELECT * FROM c WHERE c.id=@id",
                parameters=[{"name": "@id", "value": args.trip_id}],
                enable_cross_partition_query=True,
            )
        )
    except exceptions.CosmosResourceNotFoundError:
        trips = []
    if not trips:
        _fail(f"trip '{args.trip_id}' not found in {args.source_database}")
    user_ids = {t.get("user_id") for t in trips if t.get("user_id")}
    users: list[dict[str, Any]] = []
    for user_id in user_ids:
        users.extend(
            source.get_container_client("users").query_items(
                query="SELECT * FROM c WHERE c.user_id=@u",
                parameters=[{"name": "@u", "value": user_id}],
                enable_cross_partition_query=True,
            )
        )
    payload = {
        "label": args.label,
        "trips": [_strip_system_fields(dict(t)) for t in trips],
        "users": [_strip_system_fields(dict(u)) for u in users],
    }
    args.fixtures_dir.mkdir(parents=True, exist_ok=True)
    out = args.fixtures_dir / f"{args.label}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Captured trip '{args.trip_id}' -> {out}")
    return 0


def cmd_list_source(args: argparse.Namespace) -> int:
    client = _client(args.endpoint, args.key)
    source = client.get_database_client(args.source_database)
    trips = _read_all(source, "trips")
    print(f"{args.source_database}: {len(trips)} trip(s)")
    for trip in trips:
        print(f"  {trip.get('id', '<no-id>')}  (user_id={trip.get('user_id', '?')})")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--endpoint", default=EMULATOR_ENDPOINT)
    parser.add_argument("--key", default=EMULATOR_KEY)
    parser.add_argument("--source-database", default=DEFAULT_SOURCE_DATABASE)
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Seed a sandbox database from local data or fixtures.")
    seed.add_argument("--database", required=True)
    seed.add_argument("--source", choices=["local", "fixtures"], default="local")
    seed.add_argument("--if-empty", action="store_true")
    seed.add_argument("--owner", default=DEFAULT_SEED_OWNER)
    seed.add_argument("--as-user", default=SANDBOX_GUEST_USER)
    _add_common(seed)
    seed.set_defaults(func=cmd_seed)

    drop = sub.add_parser("drop", help="Delete a sandbox database.")
    drop.add_argument("--database", required=True)
    _add_common(drop)
    drop.set_defaults(func=cmd_drop)

    capture = sub.add_parser("capture", help="Export a real trip into a reusable fixture.")
    capture.add_argument("--trip-id", required=True)
    capture.add_argument("--label", required=True)
    _add_common(capture)
    capture.set_defaults(func=cmd_capture)

    listing = sub.add_parser("list-source", help="List trips available in the source database.")
    _add_common(listing)
    listing.set_defaults(func=cmd_list_source)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
