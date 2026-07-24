from __future__ import annotations

import pytest

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
