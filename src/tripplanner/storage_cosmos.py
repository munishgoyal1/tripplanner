"""Optional Azure Cosmos DB storage backend.

Used when COSMOS_ENDPOINT and COSMOS_KEY (or COSMOS_CONNECTION_STRING) are
configured. Otherwise the trip planner falls back to local JSON files in
~/.tripplanner/.

Container layout (single database, partition key /user_id on every container):
- ``users``  — one doc per user per kind. doc id is the kind ("preferences",
  "active_trip"). Keeps reads cheap (point reads, single RU).
- ``trips``  — one doc per archived trip. doc id is the unique slug.

Designed for the Cosmos Free Tier (1000 RU/s, 25 GB free per subscription).
"""

from __future__ import annotations

import copy
import logging
import warnings
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from urllib3.exceptions import InsecureRequestWarning

from tripplanner.config import get_settings

log = logging.getLogger(__name__)

_COSMOS_SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}

_client: Any | None = None
_database: Any | None = None
_containers: dict[str, Any] = {}


class WriteConflictError(RuntimeError):
    """The document changed after it was read."""


@dataclass(frozen=True)
class VersionedDocument:
    body: dict[str, Any]
    version: str


def _client_options(endpoint: str, emulator: bool) -> dict[str, Any]:
    if not emulator:
        return {}

    hostname = urlparse(endpoint).hostname
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("COSMOS_EMULATOR=1 requires a loopback COSMOS_ENDPOINT")

    return {"connection_mode": "Gateway", "connection_verify": False}


def _suppress_emulator_tls_warning() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"Unverified HTTPS request is being made to host '(?:localhost|127\.0\.0\.1|::1)'\.",
        category=InsecureRequestWarning,
        module=r"urllib3\.connectionpool",
    )


def is_enabled() -> bool:
    """True when the Cosmos backend is configured. Cheap (no network)."""
    s = get_settings()
    return bool(s.cosmos_endpoint) and bool(
        s.cosmos_key or s.cosmos_connection_string or s.cosmos_use_managed_identity
    )


def _client_singleton():
    global _client, _database
    if _client is not None:
        return _client
    from azure.cosmos import CosmosClient  # imported lazily

    s = get_settings()
    client_options = _client_options(s.cosmos_endpoint, s.cosmos_emulator)
    if s.cosmos_emulator:
        _suppress_emulator_tls_warning()
    if s.cosmos_connection_string:
        _client = CosmosClient.from_connection_string(
            s.cosmos_connection_string, **client_options
        )
    elif s.cosmos_use_managed_identity:
        from azure.identity import DefaultAzureCredential

        _client = CosmosClient(
            s.cosmos_endpoint, credential=DefaultAzureCredential(), **client_options
        )
    else:
        _client = CosmosClient(
            s.cosmos_endpoint, credential=s.cosmos_key, **client_options
        )
    _database = _client.create_database_if_not_exists(id=s.cosmos_database)
    return _client


#: Rebuildable caches and operational usage records expire instead of
#: accumulating forever. Everything else here is the user's own data and must
#: never carry a TTL. Cosmos resets the clock on each write.
#: Policy, and what is still unverified about this number, is in
#: docs/CODEMAP.md under "Cached external data".
_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
_CACHE_CONTAINERS = frozenset({"places_cache", "tool_cache"})
_CONTAINER_TTLS = {
    **{name: _CACHE_TTL_SECONDS for name in _CACHE_CONTAINERS},
    "provider_usage": 90 * 24 * 60 * 60,
}


def _container(name: str):
    if name in _containers:
        return _containers[name]
    _client_singleton()
    from azure.cosmos import PartitionKey  # imported lazily

    ttl = _CONTAINER_TTLS.get(name)
    container = _database.create_container_if_not_exists(
        id=name,
        partition_key=PartitionKey(path="/user_id"),
        default_ttl=ttl,
    )
    if ttl is not None:
        _apply_cache_ttl(container, ttl)
    _containers[name] = container
    return container


def _apply_cache_ttl(container, ttl: int) -> None:
    """Set the expiry on a cache container that predates this policy.

    ``create_container_if_not_exists`` returns an existing container untouched,
    so without this an already-deployed cache would keep every row forever.
    """
    from azure.cosmos import PartitionKey

    try:
        properties = container.read()
        if properties.get("defaultTtl") == ttl:
            return
        _database.replace_container(
            container=container,
            partition_key=PartitionKey(path="/user_id"),
            default_ttl=ttl,
        )
    except Exception as exc:  # noqa: BLE001 - a cache that cannot expire still works
        log.warning("could not set ttl on %s: %s", container.id, exc)


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


def read_doc_versioned(
    container: str, user_id: str, doc_id: str
) -> VersionedDocument | None:
    """Point read retaining an opaque version for a conditional replacement."""
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    try:
        item = _container(container).read_item(item=doc_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return None
    return VersionedDocument(
        body=_strip_system_fields(item),
        version=str(item.get("_etag") or ""),
    )


def upsert_doc(container: str, user_id: str, doc_id: str, body: dict[str, Any]) -> None:
    """Upsert a document under (user_id, doc_id)."""
    payload = copy.deepcopy(body)
    payload["id"] = doc_id
    payload["user_id"] = user_id
    _container(container).upsert_item(body=payload)


def create_doc_if_absent(
    container: str, user_id: str, doc_id: str, body: dict[str, Any]
) -> None:
    """Create a document only if its (user_id, doc_id) identity is unused."""
    from azure.cosmos.exceptions import CosmosHttpResponseError

    payload = copy.deepcopy(body)
    payload["id"] = doc_id
    payload["user_id"] = user_id
    try:
        _container(container).create_item(body=payload)
    except CosmosHttpResponseError as exc:
        if exc.status_code == 409:
            raise WriteConflictError(
                f"{container}/{doc_id} was created before it could be saved"
            ) from exc
        raise


def replace_doc_if_version(
    container: str,
    user_id: str,
    doc_id: str,
    body: dict[str, Any],
    version: str,
) -> None:
    """Replace a document only if its opaque version still matches."""
    from azure.core import MatchConditions
    from azure.cosmos.exceptions import CosmosHttpResponseError

    payload = copy.deepcopy(body)
    payload["id"] = doc_id
    payload["user_id"] = user_id
    try:
        _container(container).replace_item(
            item=doc_id,
            body=payload,
            etag=version,
            match_condition=MatchConditions.IfNotModified,
        )
    except CosmosHttpResponseError as exc:
        if exc.status_code == 412:
            raise WriteConflictError(
                f"{container}/{doc_id} changed before it could be saved"
            ) from exc
        raise


def delete_doc(container: str, user_id: str, doc_id: str) -> None:
    """Delete a document; silent if it doesn't exist."""
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    try:
        _container(container).delete_item(item=doc_id, partition_key=user_id)
    except CosmosResourceNotFoundError:
        return


def delete_doc_if_version(
    container: str, user_id: str, doc_id: str, version: str
) -> None:
    """Delete a document only if its opaque version still matches."""
    from azure.core import MatchConditions
    from azure.cosmos.exceptions import (
        CosmosHttpResponseError,
        CosmosResourceNotFoundError,
    )

    try:
        _container(container).delete_item(
            item=doc_id,
            partition_key=user_id,
            etag=version,
            match_condition=MatchConditions.IfNotModified,
        )
    except CosmosResourceNotFoundError:
        return
    except CosmosHttpResponseError as exc:
        if exc.status_code == 412:
            raise WriteConflictError(
                f"{container}/{doc_id} changed before it could be deleted"
            ) from exc
        raise


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
