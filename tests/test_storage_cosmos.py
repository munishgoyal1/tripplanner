from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError

from tripplanner import storage_cosmos
from tripplanner.config import Settings
from tripplanner.storage_cosmos import _client_options


def test_provider_usage_indexes_every_path_its_query_filters_and_nothing_else() -> None:
    """Indexing every nested entry was most of a ~150 KB usage write's RU."""
    import inspect
    import re
    from pathlib import Path

    from tripplanner import provider_usage

    policy = storage_cosmos._CONTAINER_INDEXING["provider_usage"]
    included, excluded = storage_cosmos._indexed_paths(policy)
    queried = set(re.findall(r"\bc\.(\w+)", inspect.getsource(provider_usage._read)))

    assert queried, "provider_usage._read no longer queries a field; revisit the policy"
    assert {f"/{field}/?" for field in queried} <= included
    assert excluded == {"/*"}
    bicep = (Path(__file__).resolve().parents[1] / "infra/modules/cosmos-data.bicep").read_text(
        "utf-8"
    )
    usage_block = bicep[bicep.index("name: 'provider_usage'") :]
    usage_block = usage_block[: usage_block.index("}]")]
    for path in included | excluded:
        assert f"path: '{path}'" in usage_block, f"bicep provider_usage policy lacks {path}"


class _SettingsDatabase:
    def __init__(self) -> None:
        self.replaced: list[dict] = []

    def replace_container(self, **kwargs) -> None:
        self.replaced.append(kwargs)


class _SettingsContainer:
    id = "provider_usage"

    def __init__(self, properties: dict) -> None:
        self.properties = properties

    def read(self) -> dict:
        return self.properties


def test_existing_container_gets_indexing_and_ttl_in_one_replace(monkeypatch) -> None:
    """A replace that omitted indexingPolicy would reset the container to index everything."""
    database = _SettingsDatabase()
    monkeypatch.setattr(storage_cosmos, "_database", database)
    policy = storage_cosmos._CONTAINER_INDEXING["provider_usage"]
    default_policy = {"includedPaths": [{"path": "/*"}], "excludedPaths": [{"path": '/"_etag"/?'}]}

    storage_cosmos._apply_container_settings(
        _SettingsContainer({"defaultTtl": 7776000, "indexingPolicy": default_policy}),
        7776000,
        policy,
    )

    assert len(database.replaced) == 1
    assert database.replaced[0]["indexing_policy"] == policy
    assert database.replaced[0]["default_ttl"] == 7776000


def test_container_already_matching_is_not_replaced(monkeypatch) -> None:
    database = _SettingsDatabase()
    monkeypatch.setattr(storage_cosmos, "_database", database)
    policy = storage_cosmos._CONTAINER_INDEXING["provider_usage"]
    as_cosmos_returns_it = {
        **policy,
        "excludedPaths": [*policy["excludedPaths"], {"path": '/"_etag"/?'}],
    }

    storage_cosmos._apply_container_settings(
        _SettingsContainer({"defaultTtl": 7776000, "indexingPolicy": as_cosmos_returns_it}),
        7776000,
        policy,
    )

    assert database.replaced == []


def test_ttl_update_keeps_a_containers_existing_indexing_policy(monkeypatch) -> None:
    database = _SettingsDatabase()
    monkeypatch.setattr(storage_cosmos, "_database", database)
    existing = {"includedPaths": [{"path": "/*"}], "excludedPaths": []}

    storage_cosmos._apply_container_settings(
        _SettingsContainer({"defaultTtl": None, "indexingPolicy": existing}), 2592000, None
    )

    assert database.replaced[0]["default_ttl"] == 2592000
    assert database.replaced[0]["indexing_policy"] == existing


def test_cosmos_dev_backend_defaults_to_emulator(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_DEV_BACKEND", raising=False)

    assert Settings().cosmos_dev_backend == "emulator"


def test_cosmos_dev_backend_allows_explicit_azure(monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_DEV_BACKEND", "azure")

    assert Settings().cosmos_dev_backend == "azure"


def test_emulator_uses_gateway_and_relaxes_tls_for_loopback() -> None:
    assert _client_options("https://localhost:8081", emulator=True) == {
        "connection_mode": "Gateway",
        "connection_verify": False,
    }


def test_emulator_flag_rejects_hosted_endpoint() -> None:
    with pytest.raises(ValueError, match="requires a loopback"):
        _client_options("https://tripplanner.documents.azure.com", emulator=True)


def test_hosted_client_keeps_sdk_security_defaults() -> None:
    assert _client_options("https://tripplanner.documents.azure.com", emulator=False) == {}


def test_emulator_tls_warning_filter_is_limited_to_loopback_urllib3(monkeypatch) -> None:
    captured = {}

    def capture_filter(action, **kwargs):
        captured["action"] = action
        captured.update(kwargs)

    monkeypatch.setattr(storage_cosmos.warnings, "filterwarnings", capture_filter)

    storage_cosmos._suppress_emulator_tls_warning()

    assert captured == {
        "action": "ignore",
        "message": (
            r"Unverified HTTPS request is being made to host "
            r"'(?:localhost|127\.0\.0\.1|::1)'\."
        ),
        "category": storage_cosmos.InsecureRequestWarning,
        "module": r"urllib3\.connectionpool",
    }


def test_versioned_read_keeps_etag_out_of_application_body(monkeypatch) -> None:
    class FakeContainer:
        # ``**_kwargs`` mirrors the real SDK, which takes azure-core options
        # such as response_hook -- storage_cosmos passes one to capture the RU
        # charge, and a double that rejects it fails on a signature the service
        # accepts rather than on behaviour.
        def read_item(self, *, item, partition_key, **_kwargs):
            assert (item, partition_key) == ("active_trip", "user-1")
            return {
                "id": item,
                "user_id": partition_key,
                "destination": "Goa",
                "_etag": '"version-7"',
                "_ts": 123,
            }

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    result = storage_cosmos.read_doc_versioned("users", "user-1", "active_trip")

    assert result is not None
    assert result.body == {"destination": "Goa"}
    assert result.version == '"version-7"'


def test_conditional_replace_uses_version_and_copies_body(monkeypatch) -> None:
    captured = {}

    class FakeContainer:
        def replace_item(self, **kwargs):
            captured.update(kwargs)

    body = {"destination": "Goa"}
    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    storage_cosmos.replace_doc_if_version(
        "users", "user-1", "active_trip", body, '"version-7"'
    )

    assert body == {"destination": "Goa"}
    assert captured["etag"] == '"version-7"'
    assert captured["body"] == {
        "destination": "Goa",
        "id": "active_trip",
        "user_id": "user-1",
    }


def test_conditional_create_copies_body(monkeypatch) -> None:
    captured = {}

    class FakeContainer:
        def create_item(self, **kwargs):
            captured.update(kwargs)

    body = {"destination": "Goa"}
    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    storage_cosmos.create_doc_if_absent("users", "user-1", "active_trip", body)

    assert body == {"destination": "Goa"}
    assert captured["body"] == {
        "destination": "Goa",
        "id": "active_trip",
        "user_id": "user-1",
    }


def test_conditional_create_maps_existing_document(monkeypatch) -> None:
    class FakeContainer:
        def create_item(self, **kwargs):
            raise CosmosHttpResponseError(status_code=409, message="already exists")

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    with pytest.raises(storage_cosmos.WriteConflictError, match="was created"):
        storage_cosmos.create_doc_if_absent("users", "user-1", "active_trip", {})


def test_conditional_replace_maps_precondition_failure(monkeypatch) -> None:
    class FakeContainer:
        def replace_item(self, **kwargs):
            raise CosmosHttpResponseError(status_code=412, message="precondition failed")

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    with pytest.raises(storage_cosmos.WriteConflictError, match="changed"):
        storage_cosmos.replace_doc_if_version(
            "users", "user-1", "active_trip", {}, '"stale"'
        )


def test_conditional_delete_uses_version(monkeypatch) -> None:
    captured = {}

    class FakeContainer:
        def delete_item(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    storage_cosmos.delete_doc_if_version(
        "users", "user-1", "active_trip", '"version-7"'
    )

    assert captured["item"] == "active_trip"
    assert captured["partition_key"] == "user-1"
    assert captured["etag"] == '"version-7"'


def test_conditional_delete_maps_precondition_failure(monkeypatch) -> None:
    class FakeContainer:
        def delete_item(self, **kwargs):
            raise CosmosHttpResponseError(status_code=412, message="precondition failed")

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    with pytest.raises(storage_cosmos.WriteConflictError, match="changed"):
        storage_cosmos.delete_doc_if_version(
            "users", "user-1", "active_trip", '"stale"'
        )


def _sdk_container():
    """A real azure-cosmos ContainerProxy over a faked HTTP transport.

    A fake *container* cannot catch a hook the SDK rejects, because the SDK --
    not the fake -- decides how a ``response_hook`` is called.
    """
    from azure.core.pipeline.transport import HttpTransport
    from azure.core.rest._http_response_impl import HttpResponseImpl
    from azure.cosmos import CosmosClient

    endpoint = "https://account.documents.azure.com:443/"
    location = [{"name": "local", "databaseAccountEndpoint": endpoint}]
    account = {
        "id": "account",
        "_rid": "account",
        "writableLocations": location,
        "readableLocations": location,
        "userReplicationPolicy": {},
        "userConsistencyPolicy": {"defaultConsistencyLevel": "Session"},
        "systemReplicationPolicy": {},
        "readPolicy": {},
        "queryEngineConfiguration": "{}",
    }
    collection = {
        "id": "users",
        "_rid": "abc=",
        "_self": "dbs/abc=/colls/abc=/",
        "partitionKey": {"paths": ["/user_id"], "kind": "Hash", "version": 2},
    }
    item = {"id": "active_trip", "user_id": "user-1", "destination": "Goa", "_etag": '"1"'}

    class Response(HttpResponseImpl):
        def __init__(self, request, body: dict) -> None:
            super().__init__(
                request=request,
                internal_response=None,
                status_code=200,
                headers={"Content-Type": "application/json", "x-ms-request-charge": "2.5"},
                reason="OK",
                content_type="application/json",
                stream_download_generator=None,
            )
            self._content = json.dumps(body).encode("utf-8")

        def body(self) -> bytes:
            return self._content

        def text(self, encoding=None) -> str:
            return self._content.decode("utf-8")

    class Transport(HttpTransport):
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def open(self) -> None:
            return None

        def close(self) -> None:
            return None

        def send(self, request, **_kwargs):
            if "/docs" in request.url:
                return Response(request, item)
            if "/colls/" in request.url:
                return Response(request, collection)
            return Response(request, account)

    client = CosmosClient(endpoint, credential="a2V5", transport=Transport())
    return client.get_database_client("db").get_container_client("users")


def test_request_charge_hook_matches_how_the_sdk_calls_it(monkeypatch) -> None:
    """Every point operation passes a response_hook; a wrong arity fails the call.

    The first version of the hook took one argument. The SDK calls it with two
    after the request succeeds, so every Cosmos read and write raised TypeError
    while every test -- each of which faked the container -- stayed green.
    """
    recorded: list[dict] = []

    @contextmanager
    def capture(*_args, **_kwargs):
        fields: dict = {}
        yield fields
        recorded.append(fields)

    container = _sdk_container()
    monkeypatch.setattr(storage_cosmos, "_container", lambda _name: container)
    monkeypatch.setattr(storage_cosmos, "timed_operation", capture)

    assert storage_cosmos.read_doc("users", "user-1", "active_trip") == {"destination": "Goa"}
    storage_cosmos.upsert_doc("users", "user-1", "active_trip", {"destination": "Goa"})

    assert [fields.get("ru") for fields in recorded] == [2.5, 2.5]
