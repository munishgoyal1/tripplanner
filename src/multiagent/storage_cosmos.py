"""Optional Azure Cosmos DB storage backend.

Used when COSMOS_ENDPOINT and COSMOS_KEY (or COSMOS_CONNECTION_STRING) are
configured. Otherwise the trip planner falls back to local JSON files in
~/.multiagent/.

Container layout (single database, partition key /user_id on every container):
- ``users``  — one doc per user per kind. doc id is the kind ("preferences",
  "active_trip"). Keeps reads cheap (point reads, single RU).
- ``trips``  — one doc per archived trip. doc id is the unique slug.

Designed for the Cosmos Free Tier (1000 RU/s, 25 GB free per subscription).
"""

from __future__ import annotations

import copy
from typing import Any

from multiagent.config import get_settings

_COSMOS_SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}

_client: Any | None = None
_database: Any | None = None
_containers: dict[str, Any] = {}


def is_enabled() -> bool:
    """True when the Cosmos backend is configured. Cheap (no network)."""
    s = get_settings()
    return bool(s.cosmos_endpoint) and bool(
        s.cosmos_key or s.cosmos_connection_string
    )


def _client_singleton():
    global _client, _database
    if _client is not None:
        return _client
    from azure.cosmos import CosmosClient  # imported lazily

    s = get_settings()
    if s.cosmos_connection_string:
        _client = CosmosClient.from_connection_string(s.cosmos_connection_string)
    else:
        _client = CosmosClient(s.cosmos_endpoint, credential=s.cosmos_key)
    _database = _client.create_database_if_not_exists(id=s.cosmos_database)
    return _client


def _container(name: str):
    if name in _containers:
        return _containers[name]
    _client_singleton()
    from azure.cosmos import PartitionKey  # imported lazily

    container = _database.create_container_if_not_exists(
        id=name,
        partition_key=PartitionKey(path="/user_id"),
    )
    _containers[name] = container
    return container


def _strip_system_fields(doc: dict[str, Any]) -> dict[str, Any]:
    """Drop Cosmos metadata so callers see clean app-level shape."""
    clean = {k: v for k, v in doc.items() if k not in _COSMOS_SYSTEM_FIELDS and k != "id"}
    clean.pop("user_id", None)
    return clean


def read_doc(container: str, user_id: str, doc_id: str) -> dict[str, Any] | None:
    """Point read. Returns app-level payload or ``None`` if not found."""
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    try:
        item = _container(container).read_item(item=doc_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None
    return _strip_system_fields(item)


def upsert_doc(container: str, user_id: str, doc_id: str, body: dict[str, Any]) -> None:
    """Upsert a document under (user_id, doc_id)."""
    payload = copy.deepcopy(body)
    payload["id"] = doc_id
    payload["user_id"] = user_id
    _container(container).upsert_item(body=payload)


def delete_doc(container: str, user_id: str, doc_id: str) -> None:
    """Delete a document; silent if it doesn't exist."""
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    try:
        _container(container).delete_item(item=doc_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return


def query_docs(container: str, user_id: str) -> list[dict[str, Any]]:
    """Return every doc in ``container`` belonging to ``user_id``."""
    items = _container(container).query_items(
        query="SELECT * FROM c WHERE c.user_id = @uid",
        parameters=[{"name": "@uid", "value": user_id}],
        partition_key=user_id,
    )
    return [_strip_system_fields(i) for i in items]


def delete_docs(container: str, user_id: str, id_prefix: str | None = None) -> int:
    """Delete documents for one user, optionally filtering by id prefix.

    Returns the number of delete attempts performed.
    """
    if id_prefix:
        query = "SELECT c.id FROM c WHERE c.user_id = @uid AND STARTSWITH(c.id, @prefix)"
        params = [
            {"name": "@uid", "value": user_id},
            {"name": "@prefix", "value": id_prefix},
        ]
    else:
        query = "SELECT c.id FROM c WHERE c.user_id = @uid"
        params = [{"name": "@uid", "value": user_id}]

    items = _container(container).query_items(
        query=query,
        parameters=params,
        partition_key=user_id,
    )

    deleted = 0
    for row in items:
        doc_id = row.get("id")
        if not doc_id:
            continue
        delete_doc(container, user_id, str(doc_id))
        deleted += 1
    return deleted


def reset_client_for_tests() -> None:
    """Test hook: drop cached client so tests can re-init with patched settings."""
    global _client, _database, _containers
    _client = None
    _database = None
    _containers = {}
