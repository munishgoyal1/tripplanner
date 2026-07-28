from __future__ import annotations

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError

from tripplanner import storage_cosmos
from tripplanner.config import Settings
from tripplanner.storage_cosmos import _client_options


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
        def read_item(self, *, item, partition_key):
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
