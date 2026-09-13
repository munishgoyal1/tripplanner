"""Move ``places_cache`` rows out of the legacy ``_shared`` partition.

Every cached Google place used to live under one logical partition; the app now
stores each under a bucket derived from its id (``tripplanner.place_cache_layout``).
The app already reads the legacy partition as a fallback and re-homes whatever it
touches, so nothing breaks before this runs. What this does is finish the job for
rows nobody has read since the deploy -- with ``CACHE_STABLE_FOREVER=1`` those
never expire, so waiting for a TTL would keep them, and the fallback read that
serves them, forever. Dropping them instead would re-buy every place from Google.

Per legacy row:

1. read the bucketed copy, if the app already re-homed it;
2. merge with ``cache_merge.merge_cache_documents`` -- the same policy every other
   cache writer uses, so the newest metadata, reviews and photos each win on their
   own timestamps -- and create or ETag-replace the bucketed item;
3. read the bucketed item back and compare;
4. delete the legacy row, conditional on its ETag, so a row an older app revision
   rewrote mid-run is left for the next run rather than lost.

Dry run unless ``--apply``. Safe to re-run: a finished migration finds nothing.
Run it after the partitioning change is deployed; an older revision still
writing ``_shared`` would otherwise leave rows behind for a second pass.

    python scripts/migrate_places_cache_partitions.py --account <cosmos-account> \
        --resource-group <rg> --database tripplanner-prod --report report.json [--apply]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tripplanner import place_cache_layout as layout  # noqa: E402
from tripplanner.cache_merge import merge_cache_documents  # noqa: E402

_SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})
#: The pre-sharding monolithic document. The app deletes it on first write; a
#: database the app never wrote to since may still hold it.
_MONOLITHIC_DOC_ID = "cache"


@dataclass
class MigrationReport:
    mode: str
    legacy_rows: int = 0
    created: int = 0
    merged: int = 0
    unchanged: int = 0
    deleted_legacy: int = 0
    skipped_changed: int = 0
    monolithic_documents: int = 0
    request_units: float = 0.0
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "failed" if self.failures else "passed",
            "mode": self.mode,
            "legacy_rows": self.legacy_rows,
            "created": self.created,
            "merged": self.merged,
            "unchanged": self.unchanged,
            "deleted_legacy": self.deleted_legacy,
            "skipped_changed": self.skipped_changed,
            "monolithic_documents": self.monolithic_documents,
            "request_units": round(self.request_units, 3),
            "failures": self.failures,
        }


def _status(error: BaseException) -> int | None:
    return getattr(error, "status_code", None)


def _portable(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in _SYSTEM_FIELDS and key not in {"id", "user_id"}
    }


def _read(container: Any, item_id: str, partition: str, hook) -> dict[str, Any] | None:
    try:
        return dict(container.read_item(item=item_id, partition_key=partition, response_hook=hook))
    except Exception as error:  # noqa: BLE001 - classify the SDK's 404 without importing it
        if _status(error) == 404:
            return None
        raise


def _target_body(legacy: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    body = _portable(legacy)
    if existing is not None:
        body = merge_cache_documents(layout.CONTAINER, _portable(existing), body)
    if legacy.get("ttl") == -1 or (existing or {}).get("ttl") == -1:
        # Either copy being marked stable-forever is a decision already made by
        # a writer honouring CACHE_STABLE_FOREVER; migration must not undo it.
        body["ttl"] = -1
    return body


def migrate_item(
    container: Any, legacy: dict[str, Any], report: MigrationReport, *, apply: bool
) -> None:
    item_id = str(legacy["id"])
    hook = _metered(report)
    if item_id == _MONOLITHIC_DOC_ID:
        report.monolithic_documents += 1
        if apply:
            _delete_legacy(container, legacy, report, hook)
        return

    target_partition = layout.partition(item_id)
    existing = _read(container, item_id, target_partition, hook)
    body = _target_body(legacy, existing)
    payload = {**body, "id": item_id, "user_id": target_partition}

    if existing is not None and _portable(existing) == _portable(payload):
        report.unchanged += 1
    elif existing is not None:
        report.merged += 1
    else:
        report.created += 1
    if not apply:
        return

    if existing is None:
        container.create_item(body=payload, response_hook=hook)
    elif _portable(existing) != _portable(payload):
        from azure.core import MatchConditions

        container.replace_item(
            item=item_id,
            body=payload,
            etag=existing.get("_etag"),
            match_condition=MatchConditions.IfNotModified,
            response_hook=hook,
        )

    written = _read(container, item_id, target_partition, hook)
    if written is None or _portable(written) != _portable(payload):
        raise RuntimeError(f"verification failed for {item_id}")
    _delete_legacy(container, legacy, report, hook)


def _delete_legacy(container: Any, legacy: dict[str, Any], report: MigrationReport, hook) -> None:
    from azure.core import MatchConditions

    try:
        container.delete_item(
            item=str(legacy["id"]),
            partition_key=layout.LEGACY_PARTITION,
            etag=legacy.get("_etag"),
            match_condition=MatchConditions.IfNotModified,
            response_hook=hook,
        )
    except Exception as error:  # noqa: BLE001
        if _status(error) == 412:
            report.skipped_changed += 1
            return
        if _status(error) == 404:
            return
        raise
    report.deleted_legacy += 1


def _metered(report: MigrationReport):
    def hook(headers, _result) -> None:
        try:
            report.request_units += float(headers.get("x-ms-request-charge") or 0.0)
        except (TypeError, ValueError):
            return

    return hook


def migrate(container: Any, *, apply: bool) -> MigrationReport:
    report = MigrationReport(mode="apply" if apply else "dry-run")
    rows = container.query_items(
        query="SELECT * FROM c WHERE c.user_id = @legacy",
        parameters=[{"name": "@legacy", "value": layout.LEGACY_PARTITION}],
        partition_key=layout.LEGACY_PARTITION,
        response_hook=_metered(report),
    )
    for row in rows:
        report.legacy_rows += 1
        try:
            migrate_item(container, dict(row), report, apply=apply)
        except Exception as error:  # noqa: BLE001 - one bad row must not strand the rest
            report.failures.append(
                {"id": str(row.get("id")), "error": f"{type(error).__name__}: {error}"}
            )
    return report


def _container(args: argparse.Namespace) -> Any:
    from azure.cosmos import CosmosClient

    if args.account and args.resource_group:
        sys.path.insert(0, str(ROOT / "scripts"))
        from cosmos_copy import _azure_connection

        connection = _azure_connection(args.resource_group, args.account, args.database)
        endpoint, key = connection.endpoint, connection.key
    elif args.endpoint:
        endpoint, key = args.endpoint, os.environ.get(args.key_env, "")
        if not key:
            raise SystemExit(f"--endpoint needs the account key in ${args.key_env}")
    else:
        raise SystemExit("provide --account with --resource-group, or --endpoint")
    options: dict[str, Any] = {}
    if urlparse(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}:
        options = {"connection_mode": "Gateway", "connection_verify": False}
    client = CosmosClient(endpoint, credential=key, **options)
    return client.get_database_client(args.database).get_container_client(layout.CONTAINER)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--account")
    parser.add_argument("--resource-group")
    parser.add_argument("--endpoint")
    parser.add_argument("--key-env", default="COSMOS_KEY")
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    started = time.time()
    report = migrate(_container(args), apply=args.apply).as_dict()
    report["database"] = args.database
    report["duration_seconds"] = round(time.time() - started, 3)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
