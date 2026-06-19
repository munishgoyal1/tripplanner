from __future__ import annotations

import argparse
from typing import Iterable

from azure.cosmos import CosmosClient

DEFAULT_CONTAINERS = ("users", "trips", "audit_events")


def _iter_all_items(container) -> Iterable[dict]:
    query = "SELECT * FROM c"
    return container.query_items(query=query, enable_cross_partition_query=True)


def copy_container(src_container, dst_container, container_name: str) -> int:
    copied = 0
    for item in _iter_all_items(src_container):
        dst_container.upsert_item(item)
        copied += 1
    print(f"Container {container_name}: copied {copied} items")
    return copied


def copy_cosmos(
    src_endpoint: str,
    src_key: str,
    src_db: str,
    dst_endpoint: str,
    dst_key: str,
    dst_db: str,
    containers: list[str],
) -> int:
    src_client = CosmosClient(src_endpoint, credential=src_key)
    dst_client = CosmosClient(dst_endpoint, credential=dst_key)

    src_database = src_client.get_database_client(src_db)
    dst_database = dst_client.get_database_client(dst_db)

    total = 0
    for name in containers:
        src_container = src_database.get_container_client(name)
        dst_container = dst_database.get_container_client(name)
        total += copy_container(src_container, dst_container, name)

    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy tripplanner Cosmos data between environments (upsert-based)."
    )
    parser.add_argument("--src-endpoint", required=True)
    parser.add_argument("--src-key", required=True)
    parser.add_argument("--src-db", default="tripplanner")
    parser.add_argument("--dst-endpoint", required=True)
    parser.add_argument("--dst-key", required=True)
    parser.add_argument("--dst-db", default="tripplanner")
    parser.add_argument(
        "--containers",
        nargs="+",
        default=list(DEFAULT_CONTAINERS),
        help="Container names to copy (default: users trips audit_events)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    total = copy_cosmos(
        src_endpoint=args.src_endpoint,
        src_key=args.src_key,
        src_db=args.src_db,
        dst_endpoint=args.dst_endpoint,
        dst_key=args.dst_key,
        dst_db=args.dst_db,
        containers=args.containers,
    )
    print(f"Done. Total copied items: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
