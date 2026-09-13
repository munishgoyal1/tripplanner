"""The flight chain must not stop at the first provider that answers with nothing."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tripplanner.providers.liteapi import LiteAPIError
from tripplanner.providers.models import QuoteStatus
from tripplanner.tools import duffel_flights, flight_search


@pytest.fixture(autouse=True)
def automatic_provider_selection(monkeypatch):
    monkeypatch.setattr(duffel_flights.get_settings(), "travel_flight_provider", "auto")


class StubProvider:
    def __init__(self, name: str, offers: list | None = None, error: Exception | None = None):
        self.name = name
        self._offers = offers or []
        self._error = error
        self.calls = 0

    def search_flights(self, query):
        self.calls += 1
        if self._error:
            raise self._error
        return self._offers


def call_tool(**kwargs) -> str:
    payload = {
        "origin": "Lisbon",
        "destination": "Porto",
        "departure_date": "2026-10-12",
    }
    payload.update(kwargs)
    return duffel_flights.search_flights_duffel.invoke(payload)


def test_an_empty_provider_result_falls_through_to_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = StubProvider("liteapi", offers=[])
    monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: provider)
    monkeypatch.setattr(duffel_flights, "is_configured", lambda: False)

    payload = json.loads(call_tool())

    assert provider.calls == 1
    assert payload["quote_status"] == QuoteStatus.UNAVAILABLE.value
    assert payload["errors"] == ["liteapi: no availability"]
    assert "DUFFEL_API_KEY" in payload["notice"]


def test_a_failing_provider_is_reported_and_does_not_end_the_search(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = StubProvider("liteapi", error=LiteAPIError("LiteAPI returned HTTP 502"))
    monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: provider)
    monkeypatch.setattr(duffel_flights, "is_configured", lambda: False)

    payload = json.loads(call_tool())

    assert payload["quote_status"] == QuoteStatus.UNAVAILABLE.value
    assert payload["errors"] == ["liteapi: LiteAPI returned HTTP 502"]


def test_a_provider_with_offers_still_short_circuits(monkeypatch: pytest.MonkeyPatch):
    class Offer:
        def model_dump(self, mode: str = "json"):
            return {"total": {"amount": 120.0, "currency": "EUR"}}

    provider = StubProvider("liteapi", offers=[Offer()])
    monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: provider)
    monkeypatch.setattr(duffel_flights, "is_configured", lambda: True)
    monkeypatch.setattr(duffel_flights, "note_price_check", lambda *args, **kwargs: None)

    payload = json.loads(call_tool())

    assert payload["quote_status"] == QuoteStatus.LIVE.value
    assert payload["provider"] == "liteapi"
    assert len(payload["offers"]) == 1


def test_with_no_provider_and_no_fallback_the_message_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: None)
    monkeypatch.setattr(duffel_flights, "is_configured", lambda: False)

    assert "DUFFEL_API_KEY" in call_tool()


@pytest.mark.parametrize("error", [None, LiteAPIError("LiteAPI returned HTTP 403")])
def test_explicit_liteapi_never_falls_back_to_duffel(monkeypatch, error):
    monkeypatch.setattr(duffel_flights.get_settings(), "travel_flight_provider", "liteapi")
    provider = StubProvider("liteapi", error=error)
    monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: provider)
    monkeypatch.setattr(duffel_flights, "is_configured", lambda: True)
    monkeypatch.setattr(
        duffel_flights.http_client, "post",
        lambda *a, **kw: pytest.fail("Explicit LiteAPI must not call Duffel"),
    )

    result = json.loads(call_tool())

    assert provider.calls == 1
    assert result["provider"] == "liteapi"
    assert result["quote_status"] == "unavailable"
    assert result["offers"] == []
    assert "DUFFEL_API_KEY" not in result["notice"]


@pytest.mark.parametrize("error", ["no availability", "HTTP 403"])
def test_explicit_liteapi_never_falls_back_to_amadeus(monkeypatch, error):
    monkeypatch.setattr(flight_search.get_settings(), "travel_flight_provider", "liteapi")
    monkeypatch.setattr(flight_search, "get_flight_providers", lambda: [StubProvider("liteapi")])
    monkeypatch.setattr(
        flight_search, "run_provider_chain",
        lambda **kw: SimpleNamespace(value=[], errors=[error]),
    )
    monkeypatch.setattr(
        flight_search.amadeus_client, "is_configured",
        lambda: pytest.fail("Explicit LiteAPI must not enter the Amadeus fallback"),
    )

    result = json.loads(flight_search.search_flights.invoke({
        "origin": "DEL", "destination": "GOI", "departure_date": "2026-11-12",
    }))

    assert result["provider"] == "liteapi"
    assert result["quote_status"] == "unavailable"
    assert result["offers"] == []
