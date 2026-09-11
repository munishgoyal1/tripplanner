"""Tests for src/tripplanner/billing_guardrails.py — shared config loader."""

from __future__ import annotations

from tripplanner import billing_guardrails


def test_load_reads_real_config_file():
    billing_guardrails.reset_cache_for_tests()
    data = billing_guardrails.load()
    assert "gcp" in data
    assert "azureInfraHealthAlerts" in data


def test_load_is_cached(monkeypatch):
    billing_guardrails.reset_cache_for_tests()
    calls = {"count": 0}
    real_loads = billing_guardrails.json.loads

    def counting_loads(*args, **kwargs):
        calls["count"] += 1
        return real_loads(*args, **kwargs)

    monkeypatch.setattr(billing_guardrails.json, "loads", counting_loads)
    billing_guardrails.load()
    billing_guardrails.load()
    assert calls["count"] == 1


def test_gcp_quota_per_minute_uses_environment(monkeypatch):
    billing_guardrails.reset_cache_for_tests()
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "canary")
    local_value = billing_guardrails.gcp_quota_per_minute(
        "places.googleapis.com", "SearchTextRequestPerMinutePerProject", default=999
    )
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    other_value = billing_guardrails.gcp_quota_per_minute(
        "places.googleapis.com", "SearchTextRequestPerMinutePerProject", default=999
    )
    assert local_value != 999
    assert other_value != 999


def test_gcp_quota_per_minute_falls_back_to_default_for_unknown_quota():
    billing_guardrails.reset_cache_for_tests()
    value = billing_guardrails.gcp_quota_per_minute(
        "places.googleapis.com", "NotARealQuotaId", default=42
    )
    assert value == 42
