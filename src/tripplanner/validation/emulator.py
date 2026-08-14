"""Read-only access to a sandbox Cosmos DB Emulator database.

The audit must never be able to reach live data, so the database-name rule from
``scripts/dev/sandbox_seed.py`` is repeated here rather than trusted to a caller.
"""

from __future__ import annotations

import warnings
from typing import Any

EMULATOR_ENDPOINT = "https://localhost:8081"
EMULATOR_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)
SANDBOX_PREFIX = "tripplanner-sbx-"
LIVE_DATABASE_NAMES = frozenset({"tripplanner-canary", "tripplanner-prod"})
_SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


class EmulatorUnreachableError(RuntimeError):
    """The emulator is not running, or the database does not exist."""


def assert_sandbox_database(name: str) -> str:
    lowered = (name or "").strip().lower()
    if lowered in LIVE_DATABASE_NAMES:
        raise ValueError(f"refusing to read live database '{name}'")
    if not lowered.startswith(SANDBOX_PREFIX):
        raise ValueError(f"database must start with '{SANDBOX_PREFIX}', got '{name}'")
    return name.strip()


def _client() -> Any:
    from azure.cosmos import CosmosClient
    from urllib3.exceptions import InsecureRequestWarning

    warnings.filterwarnings(
        "ignore", category=InsecureRequestWarning, module=r"urllib3\.connectionpool"
    )
    return CosmosClient(
        EMULATOR_ENDPOINT,
        credential=EMULATOR_KEY,
        connection_mode="Gateway",
        connection_verify=False,
    )


def _strip(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in _SYSTEM_FIELDS}


def list_sandbox_databases() -> list[str]:
    try:
        return sorted(
            str(entry["id"])
            for entry in _client().list_databases()
            if str(entry["id"]).startswith(SANDBOX_PREFIX)
        )
    except Exception as error:  # noqa: BLE001 - absence of an emulator is not a failure
        raise EmulatorUnreachableError(str(error)) from error


def read_trips(database: str, *, user_id: str = "") -> list[dict[str, Any]]:
    name = assert_sandbox_database(database)
    query = "SELECT * FROM c"
    parameters: list[dict[str, Any]] = []
    if user_id:
        query += " WHERE c.user_id=@u"
        parameters = [{"name": "@u", "value": user_id}]
    try:
        container = _client().get_database_client(name).get_container_client("trips")
        return [
            _strip(dict(item))
            for item in container.query_items(
                query=query, parameters=parameters, enable_cross_partition_query=True
            )
        ]
    except Exception as error:  # noqa: BLE001
        raise EmulatorUnreachableError(str(error)) from error


def read_places(database: str) -> dict[str, Any]:
    """The cached place entries, so geography checks run without a provider."""
    name = assert_sandbox_database(database)
    try:
        container = _client().get_database_client(name).get_container_client("places_cache")
        rows = container.query_items(
            query="SELECT c.key, c.entry FROM c", enable_cross_partition_query=True
        )
        return {str(row["key"]): row.get("entry") or {} for row in rows}
    except Exception:  # noqa: BLE001 - a missing cache degrades checks, never fails them
        return {}
