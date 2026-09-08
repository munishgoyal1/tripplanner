import re
from pathlib import Path

from dotenv import dotenv_values

from tripplanner.config import DEFAULT_AZURE_OPENAI_API_VERSION, Settings

SECRET_KEYS = {
    "AMADEUS_API_KEY",
    "AMADEUS_API_SECRET",
    "AZURE_COMMUNICATION_CONNECTION_STRING",
    "AZURE_OPENAI_API_KEY",
    "CACHE_REDIS_URL",
    "COSMOS_CONNECTION_STRING",
    "COSMOS_KEY",
    "DUFFEL_API_KEY",
    "GOOGLE_MAPS_BROWSER_KEY",
    "GOOGLE_PLACES_API_KEY",
    "KIWI_API_KEY",
    "LITEAPI_API_KEY",
    "OMIO_API_KEY",
    "OAUTH_GITHUB_CLIENT_SECRET",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    "OPENROUTESERVICE_API_KEY",
    "SECONDARY_DURABLE_CACHE_CONNECTION_STRING",
    "SECONDARY_DURABLE_CACHE_KEY",
    "SMTP_PASSWORD",
    "TAVILY_API_KEY",
    "VIATOR_API_KEY",
    "WEB_SESSION_SECRET",
}


def _profile_values(name: str) -> dict[str, str | None]:
    path = Path(__file__).parents[1] / "config" / "environments" / f"{name}.env"
    return dict(dotenv_values(path))


def test_azure_openai_default_matches_deployment_contract(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    assert DEFAULT_AZURE_OPENAI_API_VERSION == "2024-10-21"
    assert Settings().azure_openai_api_version == DEFAULT_AZURE_OPENAI_API_VERSION


def test_azure_openai_api_version_allows_an_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "explicit-version")
    assert Settings().azure_openai_api_version == "explicit-version"


def test_azure_openai_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_AZURE_OPENAI", raising=False)
    assert Settings().enable_azure_openai is False


def test_azure_openai_requires_explicit_enable(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_AZURE_OPENAI", "1")
    assert Settings().enable_azure_openai is True


def test_google_places_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_PLACES", raising=False)
    assert Settings().enable_google_places is False


def test_google_places_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv("ENABLE_GOOGLE_PLACES", "1")
    assert Settings().enable_google_places is True


def test_google_maps_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_GOOGLE_MAPS", raising=False)
    assert Settings().enable_google_maps is False


def test_google_maps_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv("ENABLE_GOOGLE_MAPS", "1")
    assert Settings().enable_google_maps is True


def test_cache_ttl_scale_is_owner_configurable(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SCALE", "0.5")
    settings = Settings()

    assert settings.cache_ttl(600) == 300
    assert settings.cache_ttl(1) == 1


def test_stable_and_volatile_forever_flags_are_independent(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SCALE", "0.5")
    monkeypatch.setenv("CACHE_STABLE_FOREVER", "1")
    monkeypatch.setenv("CACHE_VOLATILE_FOREVER", "0")
    settings = Settings()

    assert settings.stable_cache_ttl(600) == -1
    assert settings.volatile_cache_ttl(600) == 300

    monkeypatch.setenv("CACHE_STABLE_FOREVER", "0")
    monkeypatch.setenv("CACHE_VOLATILE_FOREVER", "1")
    settings = Settings()

    assert settings.stable_cache_ttl(600) == 300
    assert settings.volatile_cache_ttl(600) == -1


def test_warm_everything_flag_is_owner_configurable(monkeypatch):
    monkeypatch.setenv("CACHE_WARM_EVERYTHING", "1")

    assert Settings().cache_warm_everything is True


def test_secondary_durable_cache_is_local_only_by_default() -> None:
    profiles = {name: _profile_values(name) for name in ("local", "canary", "prod")}

    assert profiles["local"]["SECONDARY_DURABLE_CACHE_ENABLED"] == "1"
    assert profiles["local"]["SECONDARY_DURABLE_CACHE_ENDPOINT"] == (
        "https://localhost:8081"
    )
    assert profiles["local"]["SECONDARY_DURABLE_CACHE_DATABASE"] == "tripplanner-cache"
    assert profiles["canary"]["SECONDARY_DURABLE_CACHE_ENABLED"] == "0"
    assert profiles["prod"]["SECONDARY_DURABLE_CACHE_ENABLED"] == "0"


def test_local_launcher_routes_secondary_cache_by_cosmos_backend() -> None:
    launcher = (
        Path(__file__).parents[1] / "scripts" / "dev" / "dev-spa.ps1"
    ).read_text(encoding="utf-8")

    assert '$env:SECONDARY_DURABLE_CACHE_KEY = $env:COSMOS_KEY' in launcher
    assert '$env:SECONDARY_DURABLE_CACHE_CONNECTION_STRING = ""' in launcher
    assert '$env:SECONDARY_DURABLE_CACHE_USE_MANAGED_IDENTITY = "0"' in launcher
    assert '$env:SECONDARY_DURABLE_CACHE_ENABLED = "0"' in launcher


def test_google_places_cost_policy_is_owner_configurable(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_SEARCH_CACHE_TTL_SEC", "86400")
    monkeypatch.setenv("GOOGLE_PLACES_MAX_TEXT_SEARCHES_PER_TRIP", "2")
    settings = Settings()

    assert settings.google_places_search_cache_ttl_sec == 86400
    assert settings.google_places_max_text_searches_per_trip == 2


def test_checked_in_environment_profiles_have_the_same_non_secret_keys() -> None:
    profiles = {name: _profile_values(name) for name in ("local", "canary", "prod")}

    assert profiles["local"].keys() == profiles["canary"].keys() == profiles["prod"].keys()
    assert not (profiles["local"].keys() & SECRET_KEYS)
    for name, values in profiles.items():
        assert values["TRIPPLANNER_ENVIRONMENT"] == name


def test_every_settings_environment_key_is_owned_by_profiles_or_secret_overlay() -> None:
    config_source = (
        Path(__file__).parents[1] / "src" / "tripplanner" / "config.py"
    ).read_text(encoding="utf-8")
    referenced_keys = set(
        re.findall(
            r'(?:os\.getenv|_env_positive_int|_env_positive_float)\(\s*["\']'
            r'([A-Z][A-Z0-9_]+)["\']',
            config_source,
        )
    )

    assert referenced_keys <= (_profile_values("local").keys() | SECRET_KEYS)


def test_env_example_is_only_the_secret_overlay_template() -> None:
    template = dict(dotenv_values(Path(__file__).parents[1] / ".env.example"))

    assert template.keys() == SECRET_KEYS
    assert not (template.keys() & _profile_values("local").keys())
