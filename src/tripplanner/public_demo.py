"""Validated regional artifacts for the unauthenticated public demo."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from tripplanner import storage_cosmos

CONTAINER = "public_demo_runs"
PARTITION = "_public"
MANIFEST_ID = "active-v1"
SCHEMA_VERSION = 1
_ACTIVE_CACHE_TTL_SECONDS = 60 * 60
_active_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _bundle_path() -> Path:
    packaged = Path(str(files("tripplanner").joinpath("public_demo_runs.json")))
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "frontend/src/publicEntry/publicDemoRuns.json"


def load_bundle() -> dict[str, Any]:
    bundle = json.loads(_bundle_path().read_text(encoding="utf-8"))
    validate_bundle(bundle)
    return bundle


def artifact_key(region: str, currency: str) -> str:
    return f"{region.strip().upper()}:{currency.strip().upper()}"


def _all_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _all_text(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_text(item)]
    return []


def validate_artifact(artifact: dict[str, Any], known_entities: set[str]) -> None:
    required = {
        "schema_version", "artifact_version", "generated_at", "region", "currency",
        "market", "trip", "decisions",
    }
    if required - artifact.keys() or artifact["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported or incomplete public-demo artifact")
    market = artifact["market"]
    trip = artifact["trip"]
    currency = artifact["currency"]
    cities = set(market["cities"])
    entities = set(market["entities"])
    if (
        market["origin"] not in cities
        or market["destination"] not in cities
        or not cities.issubset(entities)
    ):
        raise ValueError("public-demo route is outside its market")
    if (
        not 4 <= len(trip["days"]) <= 6
        or len(trip["receipts"]) < 6
        or not trip["hotels"]
        or not trip["compares"]
        or len(trip["lines"]) < 2
        or not artifact["decisions"]
    ):
        raise ValueError("public-demo stage payload is incomplete")
    markers = {hotel["marker"] for hotel in trip["hotels"]}
    for hotel in trip["hotels"]:
        if hotel["city"] not in cities or hotel["name"] not in entities:
            raise ValueError("public-demo hotel is outside its market")
    day_numbers = [day["day"] for day in trip["days"]]
    if day_numbers != sorted(day_numbers) or len(day_numbers) != len(set(day_numbers)):
        raise ValueError("public-demo days must be unique and ordered")
    receipt_days = {receipt["day"] for receipt in trip["receipts"] if "day" in receipt}
    if receipt_days != set(day_numbers):
        raise ValueError("public-demo receipts must mark every completed day")
    for day in trip["days"]:
        if day["city"] not in cities or day["hotel"] not in markers or len(day["stops"]) < 2:
            raise ValueError("public-demo day is incompatible with its market or hotels")
        hotel_stops = [stop for stop in day["stops"] if stop["kind"] == "hotel"]
        if any(stop.get("marker") not in markers for stop in hotel_stops):
            raise ValueError("public-demo stop references an unknown hotel")
        named_stops = [
            stop for stop in day["stops"] if stop["kind"] in {"hotel", "attraction", "meal"}
        ]
        if any(stop["name"] not in entities for stop in named_stops):
            raise ValueError("public-demo stop is missing from its market entities")
        for leg in day["legs"]:
            endpoints = [part.strip() for part in leg["label"].split("→")]
            if len(endpoints) == 2 and any(endpoint not in cities for endpoint in endpoints):
                raise ValueError("public-demo route endpoint is outside its market")
    compare_ids = {compare["id"] for compare in trip["compares"]}
    if any(not decision["id"].startswith(tuple(compare_ids)) for decision in artifact["decisions"]):
        raise ValueError("public-demo decision is detached from its trip")
    text = "\n".join(_all_text({"trip": trip, "decisions": artifact["decisions"]}))
    foreign_entities = {
        entity for entity in known_entities - entities
        if not any(entity in local_entity for local_entity in entities)
    }
    if any(entity in text for entity in foreign_entities):
        raise ValueError("public-demo artifact contains an entity from another market")
    money_fields = [line for line in text.splitlines() if any(char.isdigit() for char in line)]
    supported_currencies = ("INR", "USD", "CAD", "GBP", "EUR", "JPY", "CNY", "AUD", "AED", "BRL")
    currency_codes = {
        code for code in supported_currencies if any(code in line for line in money_fields)
    }
    if currency_codes - {currency}:
        raise ValueError("public-demo artifact mixes currencies")


def validate_bundle(bundle: dict[str, Any]) -> None:
    artifacts = bundle.get("artifacts")
    if bundle.get("schema_version") != SCHEMA_VERSION or not isinstance(artifacts, list):
        raise ValueError("unsupported public-demo bundle")
    if len(artifacts) != 10:
        raise ValueError("public-demo bundle must contain ten regional artifacts")
    entities = {entity for artifact in artifacts for entity in artifact["market"]["entities"]}
    keys: set[str] = set()
    for artifact in artifacts:
        validate_artifact(artifact, entities)
        key = artifact_key(artifact["region"], artifact["currency"])
        if key in keys:
            raise ValueError(f"duplicate public-demo mapping: {key}")
        keys.add(key)


def bundled_artifact(region: str, currency: str) -> dict[str, Any]:
    bundle = load_bundle()
    normalized_region = region.strip().upper()
    normalized_currency = currency.strip().upper()
    for artifact in bundle["artifacts"]:
        aliases = {alias.upper() for alias in artifact["market"]["aliases"]}
        if normalized_region in aliases:
            return copy.deepcopy(artifact)
    for artifact in bundle["artifacts"]:
        if normalized_currency == artifact["currency"]:
            return copy.deepcopy(artifact)
    return copy.deepcopy(next(item for item in bundle["artifacts"] if item["currency"] == "EUR"))


def clear_active_cache() -> None:
    _active_cache.clear()


def active_artifact(region: str, currency: str) -> dict[str, Any]:
    fallback = bundled_artifact(region, currency)
    key = artifact_key(fallback["region"], fallback["currency"])
    cached = _active_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _ACTIVE_CACHE_TTL_SECONDS:
        return copy.deepcopy(cached[1])
    if not storage_cosmos.is_enabled():
        return fallback
    try:
        manifest = storage_cosmos.read_doc(CONTAINER, PARTITION, MANIFEST_ID)
        doc_id = (manifest or {}).get("artifacts", {}).get(
            key
        )
        artifact = storage_cosmos.read_doc(CONTAINER, PARTITION, doc_id) if doc_id else None
        known_entities = {
            entity for item in load_bundle()["artifacts"] for entity in item["market"]["entities"]
        }
        validate_artifact(artifact, known_entities)
        _active_cache[key] = (now, copy.deepcopy(artifact))
        return copy.deepcopy(artifact)
    except Exception:
        return fallback


def artifact_etag(artifact: dict[str, Any]) -> str:
    payload = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    return f'"{hashlib.sha256(payload).hexdigest()}"'


def refresh(now: datetime | None = None) -> dict[str, Any]:
    bundle = load_bundle()
    refreshed_at = (now or datetime.now(UTC)).replace(microsecond=0)
    stamp = refreshed_at.strftime("%Y%m%dT%H%M%SZ")
    documents: dict[str, str] = {}
    refreshed: list[dict[str, Any]] = []
    for source in bundle["artifacts"]:
        artifact = copy.deepcopy(source)
        artifact["generated_at"] = refreshed_at.isoformat().replace("+00:00", "Z")
        artifact["artifact_version"] = f"{stamp}-{artifact['region']}-{artifact['currency']}"
        refreshed.append(artifact)
    validate_bundle({"schema_version": SCHEMA_VERSION, "artifacts": refreshed})
    for artifact in refreshed:
        key = artifact_key(artifact["region"], artifact["currency"])
        doc_id = f"artifact:{artifact['artifact_version']}"
        storage_cosmos.create_doc_if_absent(CONTAINER, PARTITION, doc_id, artifact)
        documents[key] = doc_id
    manifest_body = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": refreshed[0]["generated_at"],
        "artifacts": documents,
    }
    current = storage_cosmos.read_doc_versioned(CONTAINER, PARTITION, MANIFEST_ID)
    if current:
        storage_cosmos.replace_doc_if_version(
            CONTAINER, PARTITION, MANIFEST_ID, manifest_body, current.version
        )
    else:
        storage_cosmos.create_doc_if_absent(CONTAINER, PARTITION, MANIFEST_ID, manifest_body)
    return manifest_body


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh curated public-demo artifacts")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        load_bundle()
        return
    if not storage_cosmos.is_enabled():
        raise SystemExit("Cosmos configuration is required for public-demo refresh")
    refresh()


if __name__ == "__main__":
    main()
