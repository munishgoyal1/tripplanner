from __future__ import annotations

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError

from tripplanner import storage_cosmos
from tripplanner.storage_cosmos import _client_options


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


def test_conditional_replace_maps_precondition_failure(monkeypatch) -> None:
    class FakeContainer:
        def replace_item(self, **kwargs):
            raise CosmosHttpResponseError(status_code=412, message="precondition failed")

    monkeypatch.setattr(storage_cosmos, "_container", lambda _: FakeContainer())

    with pytest.raises(storage_cosmos.WriteConflictError, match="changed"):
        storage_cosmos.replace_doc_if_version(
            "users", "user-1", "active_trip", {}, '"stale"'
        )
