from __future__ import annotations

from types import SimpleNamespace

import pytest

from tripplanner.azure_openai import AzureOpenAIDisabledError, require_azure_openai_enabled


def test_credentials_do_not_bypass_disabled_azure_openai() -> None:
    settings = SimpleNamespace(
        enable_azure_openai=False,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="valid-but-not-consent",
    )

    with pytest.raises(AzureOpenAIDisabledError, match="intentionally disabled"):
        require_azure_openai_enabled(settings)


def test_explicit_enable_allows_azure_openai_client_construction() -> None:
    settings = SimpleNamespace(enable_azure_openai=True)

    assert require_azure_openai_enabled(settings) is settings
