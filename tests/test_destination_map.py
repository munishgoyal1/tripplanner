"""Tests for the destination map URL builder."""

from __future__ import annotations

import pytest

from multiagent.web.trip_view import build_destination_overview, build_map_url


def _patch_key(monkeypatch, value: str) -> None:
    from multiagent import config

    # The Settings model reads os.getenv at class-definition time, so the
    # cached instance attribute is what we have to override.
    config.get_settings.cache_clear()
    instance = config.get_settings()
    monkeypatch.setattr(instance, "google_places_api_key", value)


@pytest.fixture
def configured_key(monkeypatch):
    _patch_key(monkeypatch, "fake-test-key")
    yield "fake-test-key"
    from multiagent import config

    config.get_settings.cache_clear()


@pytest.fixture
def no_key(monkeypatch):
    _patch_key(monkeypatch, "")
    yield
    from multiagent import config

    config.get_settings.cache_clear()


def test_map_url_empty_when_no_destination(configured_key) -> None:
    assert build_map_url("") == ""


def test_map_url_empty_when_no_key(no_key) -> None:
    assert build_map_url("Paris") == ""


def test_map_url_uses_destination(configured_key) -> None:
    url = build_map_url("Paris, France")
    assert url.startswith("https://www.google.com/maps/embed/v1/place")
    assert "key=fake-test-key" in url
    assert "Paris%2C%20France" in url


def test_map_url_prepends_highlight(configured_key) -> None:
    url = build_map_url("Paris", ["Eiffel Tower"])
    assert "Eiffel%20Tower%2C%20Paris" in url


def test_map_url_url_encodes_special_chars(configured_key) -> None:
    url = build_map_url("S\u00e3o Paulo")
    assert "S%C3%A3o%20Paulo" in url


def test_overview_includes_map_url_field(no_key) -> None:
    # Even with no key configured, the field exists in the response shape.
    out = build_destination_overview("Paris", include_news=False)
    assert "map_url" in out
    assert out["map_url"] == ""
