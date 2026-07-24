from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from azure.cosmos import CosmosClient

DEFAULT_CONTAINERS = (
    "users",
    "trips",
    "places_cache",
    "shared_trips",
    "tool_cache",
    "audit_events",
)
SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}
AUDIT_DEFAULT_TTL_SECONDS = 7_776_000


@dataclass(frozen=True)
class CosmosConnection:
    endpoint: str
    key: str
    database: str


def _iter_all_items(container: Any) -> Iterable[dict[str, Any]]:
    return container.query_items(
        query="SELECT * FROM c", enable_cross_partition_query=True
    )


def _portable_item(
    item: dict[str, Any], container_name: str = "", *, now: int | None = None
) -> dict[str, Any]:
    portable = {key: value for key, value in item.items() if key not in SYSTEM_FIELDS}
    if container_name == "audit_events" and "_ts" in item:
        source_ttl = int(item.get("ttl", AUDIT_DEFAULT_TTL_SECONDS))
        if source_ttl == -1:
            portable["ttl"] = -1
        else:
            expires_at = int(item["_ts"]) + source_ttl
            portable["ttl"] = max(
                1, expires_at - (now if now is not None else int(time.time()))
            )
    return portable


def _item_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item["user_id"]), str(item["id"])


def _verification_item(
    item: dict[str, Any], container_name: str
) -> tuple[dict[str, Any], int | str | None]:
    portable = {key: value for key, value in item.items() if key not in SYSTEM_FIELDS}
    expires_at = None
    if container_name == "audit_events":
        ttl = int(portable.pop("ttl", AUDIT_DEFAULT_TTL_SECONDS))
        if ttl == -1:
            expires_at = "permanent"
        elif "_ts" in item:
            expires_at = int(item["_ts"]) + ttl
    return portable, expires_at


def _items_by_key(
    container: Any, container_name: str
) -> dict[tuple[str, str], tuple[dict[str, Any], int | str | None]]:
    return {
        _item_key(item): _verification_item(item, container_name)
        for item in _iter_all_items(container)
    }


def _equivalent_values(source: Any, target: Any) -> bool:
    if isinstance(source, bool) or isinstance(target, bool):
        return source is target
    if isinstance(source, (int, float)) and isinstance(target, (int, float)):
        return math.isclose(source, target, rel_tol=1e-15, abs_tol=1e-12)
    if isinstance(source, dict) and isinstance(target, dict):
        return source.keys() == target.keys() and all(
            _equivalent_values(source[key], target[key]) for key in source
        )
    if isinstance(source, list) and isinstance(target, list):
        return len(source) == len(target) and all(
            _equivalent_values(source_value, target_value)
            for source_value, target_value in zip(source, target, strict=True)
        )
    return source == target


def copy_container(
    src_container: Any, dst_container: Any, container_name: str, *, dry_run: bool = False
) -> int:
    copied = 0
    for item in _iter_all_items(src_container):
        if not dry_run:
            dst_container.upsert_item(_portable_item(item, container_name))
        copied += 1
    action = "would copy" if dry_run else "copied"
    print(f"Container {container_name}: {action} {copied} items")
    return copied


def verify_container(src_container: Any, dst_container: Any, container_name: str) -> int:
    if container_name == "audit_events" and hasattr(dst_container, "read"):
        default_ttl = dst_container.read().get("defaultTtl")
        if default_ttl != AUDIT_DEFAULT_TTL_SECONDS:
            raise RuntimeError(
                "Container audit_events verification failed: "
                f"defaultTtl={default_ttl}, expected={AUDIT_DEFAULT_TTL_SECONDS}"
            )
    source = _items_by_key(src_container, container_name)
    target = _items_by_key(dst_container, container_name)
    missing = sorted(source.keys() - target.keys())
    extra = sorted(target.keys() - source.keys())
    mismatched = []
    for key in source.keys() & target.keys():
        source_body, source_expiry = source[key]
        target_body, target_expiry = target[key]
        if isinstance(source_expiry, int) and isinstance(target_expiry, int):
            expiry_changed = abs(source_expiry - target_expiry) > 5
        else:
            expiry_changed = source_expiry != target_expiry
        if not _equivalent_values(source_body, target_body) or expiry_changed:
            mismatched.append(key)
    mismatched.sort()

    if missing or extra or mismatched:
        raise RuntimeError(
            f"Container {container_name} verification failed: "
            f"missing={len(missing)}, extra={len(extra)}, mismatched={len(mismatched)}"
        )

    print(f"Container {container_name}: verified {len(source)} items")
    return len(source)


def _client(connection: CosmosConnection) -> CosmosClient:
    hostname = urlparse(connection.endpoint).hostname
    options: dict[str, Any] = {}
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        options = {"connection_mode": "Gateway", "connection_verify": False}
    return CosmosClient(connection.endpoint, credential=connection.key, **options)


def copy_cosmos(
    source: CosmosConnection,
    target: CosmosConnection,
    containers: list[str],
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> int:
    if source == target:
        raise ValueError("Source and target Cosmos coordinates must be different.")

    src_database = _client(source).get_database_client(source.database)
    dst_database = _client(target).get_database_client(target.database)

    total = 0
    for name in containers:
        src_container = src_database.get_container_client(name)
        dst_container = dst_database.get_container_client(name)
        if not verify_only:
            total += copy_container(
                src_container, dst_container, name, dry_run=dry_run
            )
        if not dry_run:
            verify_container(src_container, dst_container, name)

    return total


def _az_output(*arguments: str) -> str:
    azure_cli = shutil.which("az")
    if not azure_cli:
        raise RuntimeError("Azure CLI executable not found on PATH.")
    result = subprocess.run(
        [azure_cli, *arguments, "--only-show-errors", "-o", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _azure_connection(resource_group: str, account: str, database: str) -> CosmosConnection:
    endpoint = _az_output(
        "cosmosdb",
        "show",
        "-g",
        resource_group,
        "-n",
        account,
        "--query",
        "documentEndpoint",
    )
    key = _az_output(
        "cosmosdb",
        "keys",
        "list",
        "-g",
        resource_group,
        "-n",
        account,
        "--query",
        "primaryMasterKey",
    )
    return CosmosConnection(endpoint=endpoint, key=key, database=database)


def _connection_from_args(args: argparse.Namespace, prefix: str) -> CosmosConnection:
    account = getattr(args, f"{prefix}_account")
    resource_group = getattr(args, f"{prefix}_resource_group")
    database = getattr(args, f"{prefix}_db")
    endpoint = getattr(args, f"{prefix}_endpoint")
    key = getattr(args, f"{prefix}_key")

    if account and resource_group:
        return _azure_connection(resource_group, account, database)
    if endpoint and key:
        return CosmosConnection(endpoint=endpoint, key=key, database=database)
    raise ValueError(
        f"{prefix}: provide --{prefix}-account with --{prefix}-resource-group, "
        f"or --{prefix}-endpoint with --{prefix}-key"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy and verify tripplanner Cosmos data between databases."
    )
    for prefix in ("src", "dst"):
        parser.add_argument(f"--{prefix}-account")
        parser.add_argument(f"--{prefix}-resource-group")
        parser.add_argument(f"--{prefix}-endpoint")
        parser.add_argument(f"--{prefix}-key")
        parser.add_argument(f"--{prefix}-db", required=True)
    parser.add_argument("--containers", nargs="+", default=list(DEFAULT_CONTAINERS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = _connection_from_args(args, "src")
    target = _connection_from_args(args, "dst")
    total = copy_cosmos(
        source,
        target,
        containers=args.containers,
        dry_run=args.dry_run,
        verify_only=args.verify_only,
    )
    summary = {
        "copied": 0 if args.verify_only or args.dry_run else total,
        "inspected": total if args.dry_run else 0,
        "containers": args.containers,
        "verified": not args.dry_run,
    }
    if args.json_output:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"Done. Copied items: {summary['copied']}; verified: {summary['verified']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
