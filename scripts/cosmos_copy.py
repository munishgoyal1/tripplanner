from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from azure.cosmos import CosmosClient

DEFAULT_CONTAINERS = (
    "users",
    "trips",
    "documents",
    "places_cache",
    "shared_trips",
    "tool_cache",
    "audit_events",
    "provider_usage",
)
SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}
AUDIT_DEFAULT_TTL_SECONDS = 7_776_000
EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS = {
    "audit_events": 7_776_000,
    "provider_usage": 7_776_000,
}
LIVE_DATABASE_NAMES = {"tripplanner-canary", "tripplanner-prod"}
BACKUP_FORMAT_VERSION = 1


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
    if container_name in EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS and "_ts" in item:
        source_ttl = int(
            item.get("ttl", EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS[container_name])
        )
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
    if container_name in EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS:
        ttl = int(
            portable.pop("ttl", EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS[container_name])
        )
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
    if container_name in EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS and hasattr(
        dst_container, "read"
    ):
        default_ttl = dst_container.read().get("defaultTtl")
        expected_ttl = EXPIRING_CONTAINER_DEFAULT_TTL_SECONDS[container_name]
        if default_ttl != expected_ttl:
            raise RuntimeError(
                f"Container {container_name} verification failed: "
                f"defaultTtl={default_ttl}, expected={expected_ttl}"
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
        elif source_expiry is None or target_expiry is None:
            expiry_changed = False
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

    existing_source = {
        container["id"] for container in src_database.list_containers()
    }
    missing_source = [name for name in containers if name not in existing_source]
    if missing_source:
        raise RuntimeError(
            f"Copy aborted because source database is missing containers: {missing_source}"
        )

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


def _database_container_names(database: Any) -> set[str]:
    return {str(container["id"]) for container in database.list_containers()}


def _same_coordinates(source: CosmosConnection, target: CosmosConnection) -> bool:
    return (
        source.endpoint.rstrip("/").casefold() == target.endpoint.rstrip("/").casefold()
        and source.database.casefold() == target.database.casefold()
    )


def _require_recovery_target(
    source: CosmosConnection,
    target: CosmosConnection,
    source_database: Any,
    target_database: Any,
    containers: list[str],
) -> None:
    if _same_coordinates(source, target):
        raise ValueError("Source and target Cosmos coordinates must be different.")
    if set(containers) != set(DEFAULT_CONTAINERS) or len(containers) != len(
        DEFAULT_CONTAINERS
    ):
        raise ValueError(
            "Recovery drill requires exactly the eight default application containers."
        )
    if target.database.casefold() in LIVE_DATABASE_NAMES:
        raise ValueError(
            "Recovery drill target must not be a live canary or production database."
        )
    if not any(marker in target.database.casefold() for marker in ("recovery", "restore", "drill")):
        raise ValueError(
            "Recovery drill target database name must contain recovery, restore, or drill."
        )

    source_names = _database_container_names(source_database)
    target_names = _database_container_names(target_database)
    missing_source = sorted(set(containers) - source_names)
    missing_target = sorted(set(containers) - target_names)
    if missing_source or missing_target:
        raise RuntimeError(
            "Recovery drill requires every configured container: "
            f"missing_source={missing_source}, missing_target={missing_target}"
        )

    nonempty = []
    for name in containers:
        target_container = target_database.get_container_client(name)
        if next(iter(_iter_all_items(target_container)), None) is not None:
            nonempty.append(name)
    if nonempty:
        raise RuntimeError(
            "Recovery drill target must be empty before restore: "
            f"nonempty_containers={sorted(nonempty)}"
        )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _backup_file_name(container_name: str) -> str:
    return f"{container_name}.jsonl"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_backup(
    source: CosmosConnection,
    backup_dir: Path,
    containers: list[str],
) -> dict[str, Any]:
    """Export a portable backup artifact without storing source credentials."""
    if set(containers) != set(DEFAULT_CONTAINERS) or len(containers) != len(
        DEFAULT_CONTAINERS
    ):
        raise ValueError(
            "Backup export requires exactly the eight default application containers."
        )
    if backup_dir.exists() and any(backup_dir.iterdir()):
        raise ValueError("Backup directory must be empty or absent.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    source_database = _client(source).get_database_client(source.database)
    missing = sorted(set(containers) - _database_container_names(source_database))
    if missing:
        raise RuntimeError(f"Backup source is missing required containers: {missing}")

    exported_at = datetime.now(UTC)
    container_manifest: dict[str, dict[str, Any]] = {}
    for name in containers:
        path = backup_dir / _backup_file_name(name)
        count = 0
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for item in _iter_all_items(source_database.get_container_client(name)):
                portable = _portable_item(item, name)
                stream.write(
                    json.dumps(portable, sort_keys=True, separators=(",", ":")) + "\n"
                )
                count += 1
        container_manifest[name] = {
            "file": path.name,
            "items": count,
            "sha256": _sha256(path),
        }

    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "exported_at": exported_at.isoformat(),
        "source": {
            "host": urlparse(source.endpoint).hostname,
            "database": source.database,
        },
        "containers": container_manifest,
        "total_items": sum(entry["items"] for entry in container_manifest.values()),
    }
    _write_report(backup_dir / "manifest.json", manifest)
    return manifest


def _load_backup(backup_dir: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Backup manifest.json is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise RuntimeError("Unsupported backup format version.")
    entries = manifest.get("containers") or {}
    if set(entries) != set(DEFAULT_CONTAINERS):
        raise RuntimeError("Backup manifest does not contain all application containers.")

    items: dict[str, list[dict[str, Any]]] = {}
    for name in DEFAULT_CONTAINERS:
        entry = entries[name]
        expected_file = _backup_file_name(name)
        if entry.get("file") != expected_file:
            raise RuntimeError(f"Backup file reference validation failed for {name}.")
        path = backup_dir / expected_file
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            raise RuntimeError(f"Backup checksum verification failed for {name}.")
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(rows) != entry.get("items"):
            raise RuntimeError(f"Backup item count verification failed for {name}.")
        if any("id" not in row or "user_id" not in row for row in rows):
            raise RuntimeError(f"Backup identity validation failed for {name}.")
        items[name] = rows
    return manifest, items


def restore_backup(
    backup_dir: Path,
    target: CosmosConnection,
) -> dict[str, Any]:
    """Restore a verified artifact into an empty, isolated target database."""
    started = datetime.now(UTC)
    manifest, backup_items = _load_backup(backup_dir)
    target_database = _client(target).get_database_client(target.database)
    source_coordinates = manifest.get("source") or {}
    source = CosmosConnection(
        endpoint=f"https://{source_coordinates.get('host') or 'unknown'}",
        key="",
        database=str(source_coordinates.get("database") or ""),
    )
    source_database = BackupArtifactDatabase(backup_items)
    _require_recovery_target(
        source,
        target,
        source_database,
        target_database,
        list(DEFAULT_CONTAINERS),
    )

    counts: dict[str, int] = {}
    for name, rows in backup_items.items():
        target_container = target_database.get_container_client(name)
        for row in rows:
            target_container.upsert_item(row)
        counts[name] = verify_container(
            source_database.get_container_client(name), target_container, name
        )

    completed = datetime.now(UTC)
    return {
        "status": "passed",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "duration_seconds": round((completed - started).total_seconds(), 3),
        "backup_exported_at": manifest["exported_at"],
        "target": {
            "host": urlparse(target.endpoint).hostname,
            "database": target.database,
        },
        "containers": counts,
        "restored_items": sum(counts.values()),
        "verification": "checksum_and_exact_content",
    }


class BackupArtifactContainer:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    def query_items(self, **_: Any) -> list[dict[str, Any]]:
        return self._items


class BackupArtifactDatabase:
    def __init__(self, containers: dict[str, list[dict[str, Any]]]) -> None:
        self._containers = containers

    def list_containers(self) -> list[dict[str, str]]:
        return [{"id": name} for name in self._containers]

    def get_container_client(self, name: str) -> BackupArtifactContainer:
        return BackupArtifactContainer(self._containers[name])


def run_backup_recovery_drill(
    source: CosmosConnection,
    target: CosmosConnection,
    backup_dir: Path,
) -> dict[str, Any]:
    """Export an offline artifact, restore it in isolation, and combine evidence."""
    manifest = export_backup(source, backup_dir, list(DEFAULT_CONTAINERS))
    restore = restore_backup(backup_dir, target)
    return {
        "status": "passed",
        "backup": {
            "exported_at": manifest["exported_at"],
            "source": manifest["source"],
            "containers": {
                name: entry["items"] for name, entry in manifest["containers"].items()
            },
            "total_items": manifest["total_items"],
            "manifest": str(backup_dir / "manifest.json"),
        },
        "restore": restore,
    }


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


def _azure_connection(
    resource_group: str,
    account: str,
    database: str,
    subscription: str | None = None,
) -> CosmosConnection:
    subscription_args = ("--subscription", subscription) if subscription else ()
    endpoint = _az_output(
        "cosmosdb",
        "show",
        "-g",
        resource_group,
        "-n",
        account,
        "--query",
        "documentEndpoint",
        *subscription_args,
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
        *subscription_args,
    )
    return CosmosConnection(endpoint=endpoint, key=key, database=database)


def _connection_from_args(args: argparse.Namespace, prefix: str) -> CosmosConnection:
    account = getattr(args, f"{prefix}_account")
    resource_group = getattr(args, f"{prefix}_resource_group")
    database = getattr(args, f"{prefix}_db")
    endpoint = getattr(args, f"{prefix}_endpoint")
    key = getattr(args, f"{prefix}_key")
    subscription = getattr(args, f"{prefix}_subscription")

    if account and resource_group:
        return _azure_connection(resource_group, account, database, subscription)
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
        parser.add_argument(f"--{prefix}-subscription")
        parser.add_argument(f"--{prefix}-endpoint")
        parser.add_argument(f"--{prefix}-key")
        parser.add_argument(f"--{prefix}-db", required=prefix == "src")
    parser.add_argument("--containers", nargs="+", default=list(DEFAULT_CONTAINERS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recovery-drill", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = _connection_from_args(args, "src")
    if args.export_only:
        if args.dry_run or args.verify_only or args.recovery_drill:
            raise ValueError(
                "--export-only cannot be combined with dry-run, verify-only, or recovery-drill."
            )
        if not args.backup_dir:
            raise ValueError("--export-only requires --backup-dir.")
        if args.containers != list(DEFAULT_CONTAINERS):
            raise ValueError("--export-only does not permit a partial container list.")
        manifest = export_backup(source, args.backup_dir, list(DEFAULT_CONTAINERS))
        if args.report_path:
            _write_report(args.report_path, manifest)
        print(
            json.dumps(manifest, sort_keys=True)
            if args.json_output
            else json.dumps(manifest, indent=2)
        )
        return 0
    if not args.dst_db:
        raise ValueError("--dst-db is required unless --export-only is used.")
    target = _connection_from_args(args, "dst")
    if args.recovery_drill:
        if args.dry_run or args.verify_only:
            raise ValueError("--recovery-drill cannot be combined with dry-run or verify-only.")
        if not args.backup_dir:
            raise ValueError("--recovery-drill requires --backup-dir.")
        if args.containers != list(DEFAULT_CONTAINERS):
            raise ValueError("--recovery-drill does not permit a partial container list.")
        report = run_backup_recovery_drill(source, target, args.backup_dir)
        if args.report_path:
            _write_report(args.report_path, report)
        output = (
            json.dumps(report, sort_keys=True)
            if args.json_output
            else json.dumps(report, indent=2)
        )
        print(output)
        return 0
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
