from types import SimpleNamespace

import pytest

from tripplanner import storage_cosmos
from tripplanner.config import Settings


@pytest.fixture
def clean_cosmos(monkeypatch):
    monkeypatch.setattr(storage_cosmos, "_client", None)
    monkeypatch.setattr(storage_cosmos, "_database", None)
    monkeypatch.setattr(storage_cosmos, "_containers", {})


@pytest.mark.parametrize("client_id", ["", "assigned-identity-client-id"])
def test_identity_ignores_stale_secrets_and_never_provisions(monkeypatch, clean_cosmos, client_id):
    import azure.cosmos
    import azure.identity

    calls = []
    container = object()
    database = SimpleNamespace(get_container_client=lambda name: calls.append(name) or container)
    client = SimpleNamespace(get_database_client=lambda name: calls.append(name) or database)
    credential = object()
    settings = Settings(
        cosmos_endpoint="https://example.documents.azure.com",
        cosmos_database="tripplanner-prod",
        cosmos_use_managed_identity=True,
        cosmos_managed_identity_client_id=client_id,
        cosmos_emulator=False,
        cosmos_key="stale-key",
        cosmos_connection_string="stale-connection-string",
    )
    monkeypatch.setattr(storage_cosmos, "get_settings", lambda: settings)
    monkeypatch.setattr(
        azure.identity,
        "ManagedIdentityCredential",
        lambda **kwargs: calls.append(kwargs) or credential,
    )
    monkeypatch.setattr(
        azure.cosmos,
        "CosmosClient",
        lambda endpoint, **kwargs: calls.append((endpoint, kwargs)) or client,
    )
    assert storage_cosmos._container("provider_usage") is container
    assert storage_cosmos._container("provider_usage") is container
    assert calls == [
        {"client_id": client_id or None},
        (settings.cosmos_endpoint, {"credential": credential}),
        "tripplanner-prod",
        "provider_usage",
    ]


def test_identity_failure_does_not_retry_with_key(monkeypatch, clean_cosmos):
    import azure.cosmos
    import azure.identity

    monkeypatch.setattr(
        storage_cosmos,
        "get_settings",
        lambda: Settings(
            cosmos_endpoint="https://example.documents.azure.com",
            cosmos_use_managed_identity=True,
            cosmos_emulator=False,
            cosmos_key="stale",
        ),
    )
    monkeypatch.setattr(azure.identity, "ManagedIdentityCredential", lambda **kwargs: object())
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("identity unavailable")

    monkeypatch.setattr(azure.cosmos, "CosmosClient", fail)
    with pytest.raises(RuntimeError, match="identity unavailable"):
        storage_cosmos._client_singleton()
    assert len(calls) == 1
    assert calls[0]["credential"] != "stale"


def test_emulator_keeps_resource_initialization(monkeypatch, clean_cosmos):
    import azure.cosmos

    calls = []
    container = object()
    database = SimpleNamespace(
        create_container_if_not_exists=lambda **kw: calls.append(kw) or container
    )
    client = SimpleNamespace(
        create_database_if_not_exists=lambda **kw: calls.append(kw) or database
    )
    monkeypatch.setattr(
        storage_cosmos,
        "get_settings",
        lambda: Settings(
            cosmos_endpoint="https://localhost:8081",
            cosmos_key="emulator-key",
            cosmos_database="local",
            cosmos_emulator=True,
            cosmos_use_managed_identity=False,
            cosmos_connection_string="",
        ),
    )
    monkeypatch.setattr(
        azure.cosmos, "CosmosClient", lambda endpoint, **kw: calls.append(kw) or client
    )
    assert storage_cosmos._container("trips") is container
    assert calls[0] == {
        "credential": "emulator-key",
        "connection_mode": "Gateway",
        "connection_verify": False,
    }
    assert calls[1] == {"id": "local"}
    assert calls[2]["id"] == "trips"


def test_identity_cannot_target_emulator(monkeypatch, clean_cosmos):
    monkeypatch.setattr(
        storage_cosmos,
        "get_settings",
        lambda: Settings(
            cosmos_endpoint="https://localhost:8081",
            cosmos_emulator=True,
            cosmos_use_managed_identity=True,
        ),
    )
    with pytest.raises(ValueError, match="Managed identity cannot"):
        storage_cosmos._client_singleton()


def test_explicit_legacy_connection_string_still_works(monkeypatch, clean_cosmos):
    import azure.cosmos

    calls = []
    client = SimpleNamespace(create_database_if_not_exists=lambda **kw: object())
    factory = SimpleNamespace(
        from_connection_string=lambda value, **kw: calls.append(value) or client
    )
    monkeypatch.setattr(azure.cosmos, "CosmosClient", factory)
    monkeypatch.setattr(
        storage_cosmos,
        "get_settings",
        lambda: Settings(
            cosmos_endpoint="https://example.documents.azure.com",
            cosmos_use_managed_identity=False,
            cosmos_emulator=False,
            cosmos_connection_string="legacy-local-connection",
        ),
    )
    assert storage_cosmos._client_singleton() is client
    assert calls == ["legacy-local-connection"]
