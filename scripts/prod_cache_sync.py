"""Merge eligible cache entries between the local emulator and production Cosmos.

This utility is intentionally narrower than ``cosmos_copy.py``: it reads only
the shared Places partition and global tool-cache partition, never deletes, and
preserves the time at which provider evidence was originally observed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, PartitionKey

from tripplanner import tools_cache
from tripplanner.validation.emulator import EMULATOR_ENDPOINT, EMULATOR_KEY

SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})
PLACES_CONTAINER = "places_cache"
PLACES_PARTITION = "_shared"
TOOLS_CONTAINER = "tool_cache"
TOOLS_PARTITION = "_global_"
ALLOWED_PARTITIONS = {
    PLACES_CONTAINER: PLACES_PARTITION,
    TOOLS_CONTAINER: TOOLS_PARTITION,
}
PRODUCTION_DATABASE = "tripplanner-prod"
LOCAL_DATABASE = "tripplanner-cache"


@dataclass(frozen=True)
class CachePolicy:
    values: dict[str, str]

    @classmethod
    def from_env_file(cls, path: Path) -> CachePolicy:
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            values[name.strip()] = value.strip()
        return cls(values)

    def enabled(self, name: str) -> bool:
        return self.values.get(name, "0").casefold() in {"1", "true", "yes", "on"}

    def seconds(self, name: str, default: int) -> int:
        return max(1, round(float(self.values.get(name, default)) * self.ttl_scale))

    @property
    def ttl_scale(self) -> float:
        return max(0.01, float(self.values.get("CACHE_TTL_SCALE", "1")))

    @property
    def warm_everything(self) -> bool:
        return self.enabled("CACHE_WARM_EVERYTHING")

    def place_ttl(self, entry: dict[str, Any]) -> int:
        if self.enabled("CACHE_STABLE_FOREVER"):
            return -1
        has_fact = any(not key.startswith("__") for key in entry)
        setting = (
            "GOOGLE_PLACES_METADATA_CACHE_TTL_SEC"
            if has_fact
            else "GOOGLE_PLACES_MISS_CACHE_TTL_SEC"
        )
        return self.seconds(setting, 7 * 24 * 60 * 60 if has_fact else 60)

    def reviews_ttl(self) -> int:
        if self.enabled("CACHE_STABLE_FOREVER"):
            return -1
        return self.seconds("GOOGLE_PLACES_REVIEWS_CACHE_TTL_SEC", 6 * 60 * 60)

    def photos_ttl(self) -> int:
        if self.enabled("CACHE_STABLE_FOREVER"):
            return -1
        return self.seconds("GOOGLE_PLACES_PHOTO_URL_CACHE_TTL_SEC", 50 * 60)

    def tool_ttl(self, tool_name: str) -> int:
        volatile = tool_name in tools_cache._VOLATILE_TOOLS
        forever_flag = "CACHE_VOLATILE_FOREVER" if volatile else "CACHE_STABLE_FOREVER"
        if self.enabled(forever_flag):
            return -1
        policy = tools_cache._resolve_policy(tool_name)
        default = policy.ttl_seconds if policy else tools_cache._DEFAULT_TTL_SECONDS
        setting = tools_cache._GOOGLE_TTL_SETTINGS.get(tool_name, "")
        return (
            self.seconds(setting.upper(), default)
            if setting
            else max(1, round(default * self.ttl_scale))
        )


@dataclass(frozen=True)
class CacheRecord:
    body: dict[str, Any]
    etag: str = ""
    source_ts: float = 0.0


@dataclass(frozen=True)
class PlannedWrite:
    container: str
    partition: str
    item_id: str
    body: dict[str, Any]
    etag: str = ""


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _portable(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key not in SYSTEM_FIELDS}


def _place_group(entry: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: entry[field] for field in fields if field in entry}


def merge_place_documents(left: CacheRecord, right: CacheRecord) -> CacheRecord:
    left_entry = left.body.get("entry") if isinstance(left.body.get("entry"), dict) else {}
    right_entry = right.body.get("entry") if isinstance(right.body.get("entry"), dict) else {}
    if _number(right_entry.get("__at__")) >= _number(left_entry.get("__at__")):
        newest = right
        newest_entry, older_entry = right_entry, left_entry
    else:
        newest = left
        newest_entry, older_entry = left_entry, right_entry

    merged_entry = dict(newest_entry)
    groups = (
        (("reviews", "__reviews_at__"), "__reviews_at__"),
        (("photo_urls", "__photos_at__"), "__photos_at__"),
    )
    for fields, timestamp in groups:
        if _number(older_entry.get(timestamp)) > _number(newest_entry.get(timestamp)):
            for field in fields:
                merged_entry.pop(field, None)
            merged_entry.update(_place_group(older_entry, fields))

    body = _portable(newest.body)
    body["entry"] = merged_entry
    return CacheRecord(body=body, source_ts=max(left.source_ts, right.source_ts))


def _tool_cached_at(record: CacheRecord) -> float:
    return _number(record.body.get("cached_at")) or record.source_ts


def merge_records(container: str, left: CacheRecord, right: CacheRecord) -> CacheRecord:
    if container == PLACES_CONTAINER:
        return merge_place_documents(left, right)
    newest = right if _tool_cached_at(right) >= _tool_cached_at(left) else left
    body = _portable(newest.body)
    body["cached_at"] = _tool_cached_at(newest)
    return CacheRecord(body=body, source_ts=newest.source_ts)


def _tool_name(item_id: str) -> str:
    return item_id.rsplit("-", 1)[0]


def prepare_for_destination(
    container: str,
    record: CacheRecord,
    policy: CachePolicy,
    *,
    now: float,
) -> dict[str, Any] | None:
    body = _portable(record.body)
    body["user_id"] = ALLOWED_PARTITIONS[container]
    if container == PLACES_CONTAINER:
        entry = body.get("entry") if isinstance(body.get("entry"), dict) else {}
        observed_at = _number(entry.get("__at__"))
        ttl = policy.place_ttl(entry)
        if not observed_at or (ttl != -1 and observed_at + ttl <= now):
            return None
        entry = dict(entry)
        reviews_at = _number(entry.get("__reviews_at__"))
        reviews_ttl = policy.reviews_ttl()
        if reviews_at and reviews_ttl != -1 and reviews_at + reviews_ttl <= now:
            entry.pop("reviews", None)
            entry.pop("__reviews_at__", None)
        photos_at = _number(entry.get("__photos_at__"))
        photos_ttl = policy.photos_ttl()
        if photos_at and photos_ttl != -1 and photos_at + photos_ttl <= now:
            entry.pop("photo_urls", None)
            entry.pop("__photos_at__", None)
        body["entry"] = entry
        if ttl == -1:
            body["ttl"] = -1
        else:
            body.pop("ttl", None)
        return body

    cached_at = _tool_cached_at(record)
    if not cached_at:
        return None
    ttl = policy.tool_ttl(_tool_name(str(body.get("id", ""))))
    expires_at = -1 if ttl == -1 else cached_at + ttl
    if expires_at != -1 and expires_at <= now:
        return None
    body["cached_at"] = cached_at
    body["expires_at"] = expires_at
    if ttl == -1:
        body["ttl"] = -1
    else:
        body.pop("ttl", None)
    return body


def _equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _portable(left) == _portable(right)


def plan_direction(
    container: str,
    source: dict[str, CacheRecord],
    target: dict[str, CacheRecord],
    policy: CachePolicy,
    *,
    now: float,
) -> tuple[list[PlannedWrite], int]:
    writes: list[PlannedWrite] = []
    stale = 0
    partition = ALLOWED_PARTITIONS[container]
    for item_id, source_record in source.items():
        target_record = target.get(item_id)
        merged = (
            merge_records(container, target_record, source_record)
            if target_record
            else source_record
        )
        prepared = prepare_for_destination(container, merged, policy, now=now)
        if prepared is None:
            stale += 1
            continue
        if target_record and _equivalent(prepared, target_record.body):
            continue
        writes.append(
            PlannedWrite(
                container=container,
                partition=partition,
                item_id=item_id,
                body=prepared,
                etag=target_record.etag if target_record else "",
            )
        )
    return writes, stale


def _snapshot(database: Any, container_name: str) -> dict[str, CacheRecord]:
    partition = ALLOWED_PARTITIONS[container_name]
    container = database.get_container_client(container_name)
    rows = container.query_items(
        query="SELECT * FROM c WHERE c.user_id = @partition",
        parameters=[{"name": "@partition", "value": partition}],
        partition_key=partition,
    )
    return {
        str(row["id"]): CacheRecord(
            body=_portable(dict(row)),
            etag=str(row.get("_etag", "")),
            source_ts=_number(row.get("_ts")),
        )
        for row in rows
    }


def _write(container: Any, planned: PlannedWrite) -> None:
    body = {**planned.body, "id": planned.item_id, "user_id": planned.partition}
    if planned.etag:
        container.replace_item(
            item=planned.item_id,
            body=body,
            etag=planned.etag,
            match_condition=MatchConditions.IfNotModified,
        )
    else:
        container.create_item(body=body)


def _verify_write(container: Any, planned: PlannedWrite) -> None:
    actual = container.read_item(item=planned.item_id, partition_key=planned.partition)
    expected = {**planned.body, "id": planned.item_id, "user_id": planned.partition}
    if not _equivalent(expected, dict(actual)):
        raise RuntimeError(
            f"Verification failed for {planned.container}/{planned.partition}/{planned.item_id}"
        )


def _local_client() -> CosmosClient:
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    return CosmosClient(
        EMULATOR_ENDPOINT,
        credential=EMULATOR_KEY,
        connection_mode="Gateway",
        connection_verify=False,
    )


def _production_client(endpoint: str) -> CosmosClient:
    key = os.environ.get("TRIPPLANNER_PROD_COSMOS_KEY", "")
    if not key:
        raise RuntimeError("TRIPPLANNER_PROD_COSMOS_KEY was not supplied by the guarded launcher")
    return CosmosClient(endpoint, credential=key)


def _local_database(client: CosmosClient, name: str) -> Any:
    database = client.create_database_if_not_exists(name)
    for container, partition in ALLOWED_PARTITIONS.items():
        database.create_container_if_not_exists(
            id=container,
            partition_key=PartitionKey(path="/user_id"),
        )
    return database


def synchronize(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    now = started
    local_policy = CachePolicy.from_env_file(Path(args.local_config))
    prod_policy = CachePolicy.from_env_file(Path(args.prod_config))
    local_db = _local_database(_local_client(), args.local_database)
    prod_db = _production_client(args.prod_endpoint).get_database_client(PRODUCTION_DATABASE)
    containers = [PLACES_CONTAINER]
    if local_policy.warm_everything or prod_policy.warm_everything:
        containers.append(TOOLS_CONTAINER)

    report: dict[str, Any] = {
        "status": "passed",
        "mode": "apply" if args.apply else "dry-run",
        "direction": args.direction,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "local_database": args.local_database,
        "production_database": PRODUCTION_DATABASE,
        "containers": {},
    }
    total_written = 0
    total_conflicts = 0
    for container_name in containers:
        local = _snapshot(local_db, container_name)
        prod = _snapshot(prod_db, container_name)
        container_report: dict[str, Any] = {
            "local_read": len(local),
            "production_read": len(prod),
        }
        directions = []
        if args.direction in {"pull", "both", "status"} and (
            container_name != TOOLS_CONTAINER or local_policy.warm_everything
        ):
            directions.append(("production_to_local", prod, local, local_policy, local_db))
        if args.direction in {"push", "both", "status"} and (
            container_name != TOOLS_CONTAINER or prod_policy.warm_everything
        ):
            directions.append(("local_to_production", local, prod, prod_policy, prod_db))
        for label, source, target, policy, destination in directions:
            writes, stale = plan_direction(
                container_name, source, target, policy, now=now
            )
            applied = 0
            verified = 0
            conflicts = 0
            if args.apply:
                target_container = destination.get_container_client(container_name)
                for planned in writes:
                    try:
                        _write(target_container, planned)
                        applied += 1
                        _verify_write(target_container, planned)
                        verified += 1
                    except Exception as error:  # noqa: BLE001 - report per-item optimistic conflicts
                        if getattr(error, "status_code", None) in {409, 412}:
                            conflicts += 1
                            continue
                        raise
            container_report[label] = {
                "planned": len(writes),
                "written": applied,
                "verified": verified,
                "skipped_stale": stale,
                "conflicts": conflicts,
            }
            total_written += applied
            total_conflicts += conflicts
        report["containers"][container_name] = container_report
    report["written"] = total_written
    report["conflicts"] = total_conflicts
    report["duration_seconds"] = round(time.time() - started, 3)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", choices=("status", "pull", "push", "both"), default="status")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prod-endpoint", required=True)
    parser.add_argument("--local-database", default=LOCAL_DATABASE)
    parser.add_argument("--local-config", default="config/environments/local.env")
    parser.add_argument("--prod-config", default="config/environments/prod.env")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    try:
        report = synchronize(args)
    except Exception as error:  # noqa: BLE001 - operator report must survive any failed stage
        report = {
            "status": "failed",
            "direction": args.direction,
            "mode": "apply" if args.apply else "dry-run",
            "error": str(error),
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Report: {report_path}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
