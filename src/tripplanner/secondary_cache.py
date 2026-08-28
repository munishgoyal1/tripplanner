"""Optional best-effort secondary durable cache backed by Cosmos DB."""

from __future__ import annotations

import copy
import logging
import threading
import time
import warnings
from queue import Queue
from typing import Any
from urllib.parse import urlparse

from urllib3.exceptions import InsecureRequestWarning

from tripplanner.cache_merge import merge_cache_documents
from tripplanner.config import get_settings

log = logging.getLogger(__name__)

_ALLOWED_PARTITIONS = {"places_cache": "_shared", "tool_cache": "_global_"}
_SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}
_FAILURE_COOLDOWN_SECONDS = 30.0
_MAX_WRITE_ATTEMPTS = 3

_client: Any | None = None
_database: Any | None = None
_containers: dict[str, Any] = {}
_lock = threading.Lock()
_disabled_until = 0.0
_write_queue: Queue[tuple[str, str, dict[str, Any]]] = Queue()
_writer: threading.Thread | None = None


def _shared_emulator_key() -> str:
    settings = get_settings()
    if (
        settings.secondary_durable_cache_emulator
        and settings.cosmos_emulator
        and settings.secondary_durable_cache_endpoint == settings.cosmos_endpoint
    ):
        return settings.cosmos_key
    return ""


def is_enabled() -> bool:
    """Return whether a complete secondary-cache connection is configured."""
    settings = get_settings()
    has_endpoint = bool(
        settings.secondary_durable_cache_endpoint
        or settings.secondary_durable_cache_connection_string
    )
    has_credential = bool(
        settings.secondary_durable_cache_key
        or settings.secondary_durable_cache_connection_string
        or settings.secondary_durable_cache_use_managed_identity
        or _shared_emulator_key()
    )
    return settings.secondary_durable_cache_enabled and has_endpoint and has_credential


def _client_options(endpoint: str, emulator: bool) -> dict[str, Any]:
    if not emulator:
        return {}
    if urlparse(endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "SECONDARY_DURABLE_CACHE_EMULATOR=1 requires a loopback endpoint"
        )
    warnings.filterwarnings(
        "ignore",
        message=(
            r"Unverified HTTPS request is being made to host "
            r"'(?:localhost|127\.0\.0\.1|::1)'\."
        ),
        category=InsecureRequestWarning,
        module=r"urllib3\.connectionpool",
    )
    return {"connection_mode": "Gateway", "connection_verify": False}


def _client_singleton() -> Any:
    global _client, _database
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        from azure.cosmos import CosmosClient

        settings = get_settings()
        endpoint = settings.secondary_durable_cache_endpoint
        connection_string = settings.secondary_durable_cache_connection_string
        key = settings.secondary_durable_cache_key or _shared_emulator_key()
        use_managed_identity = settings.secondary_durable_cache_use_managed_identity
        options = _client_options(endpoint, settings.secondary_durable_cache_emulator)
        if connection_string:
            client = CosmosClient.from_connection_string(connection_string, **options)
        elif use_managed_identity:
            from azure.identity import DefaultAzureCredential

            client = CosmosClient(endpoint, credential=DefaultAzureCredential(), **options)
        else:
            client = CosmosClient(endpoint, credential=key, **options)
        database = client.create_database_if_not_exists(
            id=settings.secondary_durable_cache_database
        )
        _client = client
        _database = database
    return _client


def _container(name: str) -> Any:
    if name not in _ALLOWED_PARTITIONS:
        raise ValueError(f"unsupported shared cache container: {name}")
    if name in _containers:
        return _containers[name]
    _client_singleton()
    from azure.cosmos import PartitionKey

    container = _database.create_container_if_not_exists(
        id=name,
        partition_key=PartitionKey(path="/user_id"),
        default_ttl=30 * 24 * 60 * 60,
    )
    _containers[name] = container
    return container


def _clean(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in _SYSTEM_FIELDS and key not in {"id", "user_id"}
    }


def _available() -> bool:
    return is_enabled() and time.monotonic() >= _disabled_until


def _record_failure(operation: str, exc: Exception) -> None:
    global _disabled_until
    _disabled_until = time.monotonic() + _FAILURE_COOLDOWN_SECONDS
    log.warning("secondary durable cache %s failed: %s", operation, exc)


def read_doc(container: str, doc_id: str) -> dict[str, Any] | None:
    """Best-effort point read from an allowed global cache partition."""
    if not _available():
        return None
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    try:
        item = _container(container).read_item(
            item=doc_id,
            partition_key=_ALLOWED_PARTITIONS[container],
        )
    except CosmosResourceNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 - secondary cache must fail open
        _record_failure("read", exc)
        return None
    return _clean(item)


def merge_write(container: str, doc_id: str, body: dict[str, Any]) -> bool:
    """Best-effort ETag-protected merge into an allowed global partition."""
    if not _available():
        return False
    try:
        target = _container(container)
        partition = _ALLOWED_PARTITIONS[container]
        for _attempt in range(_MAX_WRITE_ATTEMPTS):
            try:
                current = target.read_item(item=doc_id, partition_key=partition)
            except Exception as exc:  # noqa: BLE001 - classify SDK 404 without importing early
                if getattr(exc, "status_code", None) != 404:
                    raise
                payload = copy.deepcopy(body)
                payload.update({"id": doc_id, "user_id": partition})
                try:
                    target.create_item(body=payload)
                    return True
                except Exception as create_exc:  # noqa: BLE001
                    if getattr(create_exc, "status_code", None) != 409:
                        raise
                    continue

            merged = merge_cache_documents(container, _clean(current), body)
            payload = copy.deepcopy(merged)
            payload.update({"id": doc_id, "user_id": partition})
            from azure.core import MatchConditions

            try:
                target.replace_item(
                    item=doc_id,
                    body=payload,
                    etag=current.get("_etag"),
                    match_condition=MatchConditions.IfNotModified,
                )
                return True
            except Exception as replace_exc:  # noqa: BLE001
                if getattr(replace_exc, "status_code", None) != 412:
                    raise
        raise RuntimeError(f"concurrent updates did not settle for {container}/{doc_id}")
    except Exception as exc:  # noqa: BLE001 - secondary cache must fail open
        _record_failure("write", exc)
        return False


def _writer_loop() -> None:
    while True:
        container, doc_id, body = _write_queue.get()
        try:
            merge_write(container, doc_id, body)
        finally:
            _write_queue.task_done()


def schedule_merge_write(container: str, doc_id: str, body: dict[str, Any]) -> None:
    """Queue a best-effort merge without delaying the caller."""
    global _writer
    if not is_enabled():
        return
    with _lock:
        if _writer is None:
            _writer = threading.Thread(
                target=_writer_loop,
                name="secondary-cache-writer",
                daemon=True,
            )
            _writer.start()
    _write_queue.put((container, doc_id, copy.deepcopy(body)))


def reset_client_for_tests() -> None:
    """Drop cached clients and circuit-breaker state."""
    global _client, _database, _containers, _disabled_until
    _client = None
    _database = None
    _containers = {}
    _disabled_until = 0.0
