"""Merge eligible cache entries between the local emulator and production Cosmos.

This utility is intentionally narrower than ``cosmos_copy.py``: it reads only
the shared Places partition and global tool-cache partition, never deletes, and
preserves the time at which provider evidence was originally observed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, PartitionKey, exceptions

from tripplanner import tools_cache
from tripplanner.cache_merge import merge_cache_documents
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
CHECKPOINT_VERSION = 1
DEFAULT_WATERMARK_OVERLAP_SECONDS = 300


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


@dataclass
class ActivityMetrics:
    request_units: float = 0.0
    requests: int = 0
    payload_bytes: int = 0

    def response_hook(self, headers: Mapping[str, str], _result: Any) -> None:
        self.requests += 1
        self.request_units += _number(headers.get("x-ms-request-charge"))

    def add_payload(self, body: Any) -> None:
        self.payload_bytes += len(
            json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )

    def report(self) -> dict[str, int | float]:
        return {
            "requests": self.requests,
            "request_units": round(self.request_units, 3),
            "payload_bytes": self.payload_bytes,
        }


@dataclass(frozen=True)
class Snapshot:
    records: dict[str, CacheRecord]
    observed_watermark: float
    query_since: float
    full_scan: bool
    metrics: ActivityMetrics


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _portable(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key not in SYSTEM_FIELDS}


def _checkpoint_scope(args: argparse.Namespace) -> dict[str, str]:
    return {
        "local_database": args.local_database,
        "local_policy_sha256": _file_digest(Path(args.local_config)),
        "production_database": PRODUCTION_DATABASE,
        "production_endpoint": args.prod_endpoint.rstrip("/").casefold(),
        "production_policy_sha256": _file_digest(Path(args.prod_config)),
    }


def _file_digest(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError:
        return "unreadable"
    return hashlib.sha256(content).hexdigest()


def _empty_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "version": CHECKPOINT_VERSION,
        "scope": _checkpoint_scope(args),
        "sources": {"local": {}, "production": {}},
    }


def _load_checkpoint(path: Path, args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return _empty_checkpoint(args), "missing"
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        if checkpoint.get("version") != CHECKPOINT_VERSION:
            return _empty_checkpoint(args), "unsupported_version"
        if checkpoint.get("scope") != _checkpoint_scope(args):
            return _empty_checkpoint(args), "scope_mismatch"
        sources = checkpoint.get("sources")
        if not isinstance(sources, dict):
            return _empty_checkpoint(args), "invalid_sources"
        for source_name in ("local", "production"):
            watermarks = sources.get(source_name)
            if not isinstance(watermarks, dict):
                return _empty_checkpoint(args), "invalid_sources"
            for watermark in watermarks.values():
                if _number(watermark) <= 0:
                    return _empty_checkpoint(args), "invalid_watermark"
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return _empty_checkpoint(args), "unreadable"
    return checkpoint, "loaded"


def _save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _watermark(checkpoint: dict[str, Any], source: str, container: str) -> float:
    return _number(checkpoint["sources"][source].get(container))


def merge_place_documents(left: CacheRecord, right: CacheRecord) -> CacheRecord:
    body = merge_cache_documents(PLACES_CONTAINER, left.body, right.body)
    return CacheRecord(body=_portable(body), source_ts=max(left.source_ts, right.source_ts))


def _tool_cached_at(record: CacheRecord) -> float:
    return _number(record.body.get("cached_at")) or record.source_ts


def merge_records(container: str, left: CacheRecord, right: CacheRecord) -> CacheRecord:
    if container == PLACES_CONTAINER:
        return merge_place_documents(left, right)
    left_body = dict(left.body)
    left_body["cached_at"] = _tool_cached_at(left)
    right_body = dict(right.body)
    right_body["cached_at"] = _tool_cached_at(right)
    body = _portable(merge_cache_documents(container, left_body, right_body))
    newest = right if body["cached_at"] == _tool_cached_at(right) else left
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


def _snapshot(database: Any, container_name: str) -> Snapshot:
    partition = ALLOWED_PARTITIONS[container_name]
    container = database.get_container_client(container_name)
    metrics = ActivityMetrics()
    rows = container.query_items(
        query="SELECT * FROM c WHERE c.user_id = @partition",
        parameters=[{"name": "@partition", "value": partition}],
        partition_key=partition,
        response_hook=metrics.response_hook,
    )
    records: dict[str, CacheRecord] = {}
    observed_watermark = 0.0
    for row in rows:
        metrics.add_payload(row)
        observed_watermark = max(observed_watermark, _number(row.get("_ts")))
        records[str(row["id"])] = CacheRecord(
            body=_portable(dict(row)),
            etag=str(row.get("_etag", "")),
            source_ts=_number(row.get("_ts")),
        )
    return Snapshot(records, observed_watermark, 0.0, True, metrics)


def _read_record(
    database: Any,
    container_name: str,
    item_id: str,
    metrics: ActivityMetrics,
) -> CacheRecord | None:
    container = database.get_container_client(container_name)
    try:
        row = container.read_item(
            item=item_id,
            partition_key=ALLOWED_PARTITIONS[container_name],
            response_hook=metrics.response_hook,
        )
    except exceptions.CosmosResourceNotFoundError:
        return None
    metrics.add_payload(row)
    return CacheRecord(
        body=_portable(dict(row)),
        etag=str(row.get("_etag", "")),
        source_ts=_number(row.get("_ts")),
    )


def _changed_snapshot(
    source_database: Any,
    target_database: Any,
    container_name: str,
    watermark: float,
    overlap_seconds: int,
) -> tuple[
    Snapshot,
    dict[str, CacheRecord],
    ActivityMetrics,
    ActivityMetrics,
]:
    partition = ALLOWED_PARTITIONS[container_name]
    query_since = max(0.0, watermark - max(0, overlap_seconds))
    query_metrics = ActivityMetrics()
    source_read_metrics = ActivityMetrics()
    target_read_metrics = ActivityMetrics()
    rows = source_database.get_container_client(container_name).query_items(
        query=(
            "SELECT c.id, c._ts FROM c "
            "WHERE c.user_id = @partition AND c._ts >= @since"
        ),
        parameters=[
            {"name": "@partition", "value": partition},
            {"name": "@since", "value": query_since},
        ],
        partition_key=partition,
        response_hook=query_metrics.response_hook,
    )
    changed_ids: list[str] = []
    observed_watermark = watermark
    for row in rows:
        query_metrics.add_payload(row)
        changed_ids.append(str(row["id"]))
        observed_watermark = max(observed_watermark, _number(row.get("_ts")))

    source_records: dict[str, CacheRecord] = {}
    target_records: dict[str, CacheRecord] = {}
    for item_id in dict.fromkeys(changed_ids):
        source_record = _read_record(
            source_database, container_name, item_id, source_read_metrics
        )
        if source_record is None:
            continue
        source_records[item_id] = source_record
        target_record = _read_record(
            target_database, container_name, item_id, target_read_metrics
        )
        if target_record is not None:
            target_records[item_id] = target_record
    snapshot = Snapshot(
        source_records,
        observed_watermark,
        query_since,
        False,
        query_metrics,
    )
    return snapshot, target_records, source_read_metrics, target_read_metrics


def _combined_metrics(*values: ActivityMetrics) -> ActivityMetrics:
    return ActivityMetrics(
        request_units=sum(value.request_units for value in values),
        requests=sum(value.requests for value in values),
        payload_bytes=sum(value.payload_bytes for value in values),
    )


def _write(
    container: Any,
    planned: PlannedWrite,
    metrics: ActivityMetrics | None = None,
) -> tuple[str, ActivityMetrics]:
    body = {**planned.body, "id": planned.item_id, "user_id": planned.partition}
    metrics = metrics or ActivityMetrics()
    metrics.add_payload(body)
    if planned.etag:
        container.replace_item(
            item=planned.item_id,
            body=body,
            etag=planned.etag,
            match_condition=MatchConditions.IfNotModified,
            response_hook=metrics.response_hook,
        )
        return "replaced", metrics
    else:
        container.create_item(body=body, response_hook=metrics.response_hook)
        return "inserted", metrics


def _verify_write(
    container: Any,
    planned: PlannedWrite,
    metrics: ActivityMetrics | None = None,
) -> ActivityMetrics:
    metrics = metrics or ActivityMetrics()
    actual = container.read_item(
        item=planned.item_id,
        partition_key=planned.partition,
        response_hook=metrics.response_hook,
    )
    metrics.add_payload(actual)
    expected = {**planned.body, "id": planned.item_id, "user_id": planned.partition}
    if not _equivalent(expected, dict(actual)):
        raise RuntimeError(
            f"Verification failed for {planned.container}/{planned.partition}/{planned.item_id}"
        )
    return metrics


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
    report: dict[str, Any] = {
        "status": "passed",
        "mode": "apply" if args.apply else "dry-run",
        "direction": args.direction,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "local_database": args.local_database,
        "production_database": PRODUCTION_DATABASE,
        "containers": {},
    }
    checkpoint_path = Path(args.checkpoint)
    checkpoint, checkpoint_state = _load_checkpoint(checkpoint_path, args)
    report["checkpoint"] = {
        "path": str(checkpoint_path),
        "state": checkpoint_state,
        "overlap_seconds": args.watermark_overlap_seconds,
        "advanced": False,
    }
    total_written = 0
    total_conflicts = 0
    checkpoint_updates: list[tuple[str, str, float]] = []
    all_metrics: list[ActivityMetrics] = []
    try:
        local_policy = CachePolicy.from_env_file(Path(args.local_config))
        prod_policy = CachePolicy.from_env_file(Path(args.prod_config))
        local_db = _local_database(_local_client(), args.local_database)
        prod_db = _production_client(args.prod_endpoint).get_database_client(PRODUCTION_DATABASE)
        databases = {"local": local_db, "production": prod_db}
        containers = [PLACES_CONTAINER]
        if local_policy.warm_everything or prod_policy.warm_everything:
            containers.append(TOOLS_CONTAINER)

        for container_name in containers:
            direction_specs = []
            if args.direction in {"pull", "both", "status"} and (
                container_name != TOOLS_CONTAINER or local_policy.warm_everything
            ):
                direction_specs.append(
                    ("production_to_local", "production", "local", local_policy)
                )
            if args.direction in {"push", "both", "status"} and (
                container_name != TOOLS_CONTAINER or prod_policy.warm_everything
            ):
                direction_specs.append(
                    ("local_to_production", "local", "production", prod_policy)
                )

            full_snapshots: dict[str, Snapshot] = {}
            plans: list[tuple[Any, ...]] = []
            container_report: dict[str, Any] = {}
            for label, source_name, target_name, policy in direction_specs:
                watermark = _watermark(checkpoint, source_name, container_name)
                full_scan = args.full_scan or watermark <= 0
                if full_scan:
                    for environment in (source_name, target_name):
                        if environment not in full_snapshots:
                            full_snapshots[environment] = _snapshot(
                                databases[environment], container_name
                            )
                            all_metrics.append(full_snapshots[environment].metrics)
                    source_snapshot = full_snapshots[source_name]
                    target_records = full_snapshots[target_name].records
                    source_read_metrics = ActivityMetrics()
                    target_read_metrics = full_snapshots[target_name].metrics
                else:
                    (
                        source_snapshot,
                        target_records,
                        source_read_metrics,
                        target_read_metrics,
                    ) = _changed_snapshot(
                        databases[source_name],
                        databases[target_name],
                        container_name,
                        watermark,
                        args.watermark_overlap_seconds,
                    )
                if not full_scan:
                    all_metrics.extend(
                        [
                            source_snapshot.metrics,
                            source_read_metrics,
                            target_read_metrics,
                        ]
                    )
                writes, stale = plan_direction(
                    container_name,
                    source_snapshot.records,
                    target_records,
                    policy,
                    now=now,
                )
                direction_report: dict[str, Any] = {
                    "scan": {
                        "mode": "full" if source_snapshot.full_scan else "incremental",
                        "watermark_before": watermark,
                        "query_since": source_snapshot.query_since,
                        "watermark_observed": source_snapshot.observed_watermark,
                        "candidates": len(source_snapshot.records),
                    },
                    "reads": {
                        "metadata_query": source_snapshot.metrics.report(),
                        "source_documents": source_read_metrics.report(),
                        "target_documents": target_read_metrics.report(),
                    },
                    "planned": len(writes),
                    "unchanged": max(0, len(source_snapshot.records) - len(writes) - stale),
                    "written": 0,
                    "inserted": 0,
                    "replaced": 0,
                    "verified": 0,
                    "skipped_stale": stale,
                    "conflicts": 0,
                    "write_metrics": ActivityMetrics().report(),
                    "verification_metrics": ActivityMetrics().report(),
                    "delta_activity": [
                        {
                            "id": planned.item_id,
                            "action": "replace" if planned.etag else "insert",
                            "status": "planned",
                        }
                        for planned in writes
                    ],
                }
                container_report[label] = direction_report
                plans.append(
                    (
                        label,
                        source_name,
                        target_name,
                        source_snapshot,
                        writes,
                        direction_report,
                    )
                )

            report["containers"][container_name] = container_report
            for (
                label,
                source_name,
                target_name,
                source_snapshot,
                writes,
                direction_report,
            ) in plans:
                write_metrics = ActivityMetrics()
                verification_metrics = ActivityMetrics()
                all_metrics.extend([write_metrics, verification_metrics])
                if args.apply:
                    target_container = databases[target_name].get_container_client(
                        container_name
                    )
                    for index, planned in enumerate(writes):
                        activity = direction_report["delta_activity"][index]
                        try:
                            action, _ = _write(
                                target_container, planned, write_metrics
                            )
                            direction_report["written"] += 1
                            direction_report[action] += 1
                            activity["status"] = "written"
                            _verify_write(
                                target_container,
                                planned,
                                verification_metrics,
                            )
                            direction_report["verified"] += 1
                            activity["status"] = "verified"
                        except Exception as error:  # noqa: BLE001 - preserve partial report
                            if getattr(error, "status_code", None) in {409, 412}:
                                direction_report["conflicts"] += 1
                                activity["status"] = "conflict"
                                continue
                            activity["status"] = "failed"
                            activity["error"] = type(error).__name__
                            raise
                        finally:
                            direction_report["write_metrics"] = write_metrics.report()
                            direction_report[
                                "verification_metrics"
                            ] = verification_metrics.report()
                direction_report["write_metrics"] = write_metrics.report()
                direction_report["verification_metrics"] = verification_metrics.report()
                total_written += direction_report["written"]
                total_conflicts += direction_report["conflicts"]
                checkpoint_updates.append(
                    (
                        source_name,
                        container_name,
                        source_snapshot.observed_watermark,
                    )
                )
        if total_conflicts:
            report["status"] = "partial"
            report["checkpoint"]["reason"] = "conflicts_detected"
        elif args.apply:
            for source_name, container_name, observed in checkpoint_updates:
                if observed > 0:
                    checkpoint["sources"][source_name][container_name] = observed
            _save_checkpoint(checkpoint_path, checkpoint)
            report["checkpoint"]["advanced"] = True
            report["checkpoint"]["reason"] = "all_writes_verified"
        else:
            report["checkpoint"]["reason"] = "dry_run"
    except Exception as error:  # noqa: BLE001 - retain the detailed partial-run report
        report["status"] = "failed"
        report["error"] = str(error)
        report["checkpoint"]["reason"] = "run_failed"
    direction_reports = [
        direction
        for container in report["containers"].values()
        for direction in container.values()
    ]
    report["written"] = sum(direction["written"] for direction in direction_reports)
    report["conflicts"] = sum(direction["conflicts"] for direction in direction_reports)
    report["activity"] = _combined_metrics(*all_metrics).report()
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
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument(
        "--watermark-overlap-seconds",
        type=int,
        default=DEFAULT_WATERMARK_OVERLAP_SECONDS,
    )
    parser.add_argument("--full-scan", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if args.watermark_overlap_seconds < 0:
        parser.error("--watermark-overlap-seconds must be non-negative")

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
