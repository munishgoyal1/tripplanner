from tripplanner.config import DEFAULT_AZURE_OPENAI_API_VERSION, Settings


def test_azure_openai_default_matches_deployment_contract(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    assert DEFAULT_AZURE_OPENAI_API_VERSION == "2024-10-21"
    assert Settings().azure_openai_api_version == DEFAULT_AZURE_OPENAI_API_VERSION


def test_azure_openai_api_version_allows_an_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "explicit-version")
    assert Settings().azure_openai_api_version == "explicit-version"


def test_google_places_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_PLACES", raising=False)
    assert Settings().enable_google_places is False


def test_google_places_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv("ENABLE_GOOGLE_PLACES", "1")
    assert Settings().enable_google_places is True


def test_cache_ttl_scale_is_owner_configurable(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SCALE", "0.5")
    settings = Settings()

    assert settings.cache_ttl(600) == 300
    assert settings.cache_ttl(1) == 1
