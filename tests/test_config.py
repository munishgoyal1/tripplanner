from tripplanner.config import DEFAULT_AZURE_OPENAI_API_VERSION, Settings


def test_azure_openai_default_matches_deployment_contract(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    assert DEFAULT_AZURE_OPENAI_API_VERSION == "2024-10-21"
    assert Settings().azure_openai_api_version == DEFAULT_AZURE_OPENAI_API_VERSION


def test_azure_openai_api_version_allows_an_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "explicit-version")

    assert Settings().azure_openai_api_version == "explicit-version"
