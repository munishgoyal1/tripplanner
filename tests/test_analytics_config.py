from types import SimpleNamespace

from fastapi.testclient import TestClient

from tripplanner import api


def _config(monkeypatch, environment: str, measurement_id: str) -> dict:
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", environment)
    monkeypatch.setattr(
        "tripplanner.config.get_settings",
        lambda: SimpleNamespace(google_analytics_measurement_id=measurement_id),
    )
    return TestClient(api.app).get("/analytics/config").json()


def test_analytics_config_is_enabled_only_in_production(monkeypatch) -> None:
    assert _config(monkeypatch, "prod", "G-ABC123") == {
        "enabled": True,
        "measurement_id": "G-ABC123",
    }
    assert _config(monkeypatch, "canary", "G-ABC123") == {
        "enabled": False,
        "measurement_id": "",
    }


def test_analytics_config_rejects_invalid_measurement_id(monkeypatch) -> None:
    assert _config(monkeypatch, "production", "not-an-id") == {
        "enabled": False,
        "measurement_id": "",
    }