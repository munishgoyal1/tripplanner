"""Provider-neutral live travel inventory tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from tripplanner import http_client
from tripplanner.config import get_settings
from tripplanner.providers.cache import ProviderTTLCache
from tripplanner.providers.liteapi import LiteAPIError, LiteAPIProvider
from tripplanner.providers.models import (
    ActivitySearchQuery,
    FlightOffer,
    FlightSearchQuery,
    HotelOffer,
    HotelSearchQuery,
    Money,
)
from tripplanner.providers.registry import (
    get_activity_provider,
    get_flight_provider,
    get_hotel_provider,
    get_train_provider,
    provider_catalog,
    provider_status,
)
from tripplanner.providers.runtime import run_provider_chain
from tripplanner.providers.viator import ViatorError, ViatorProvider
from tripplanner.tools import flight_search, hotel_search, trip_planner


def _response(status: int, payload: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.liteapi.travel/v3.0/test")
    return (
        httpx.Response(status, request=request, json=payload)
        if payload
        else httpx.Response(status, request=request)
    )


def test_registry_auto_selects_liteapi_by_capability():
    settings = SimpleNamespace(
        liteapi_api_key="test-key",
        liteapi_base_url="https://api.liteapi.travel/v3.0",
        travel_hotel_provider="auto",
        travel_flight_provider="auto",
        viator_api_key="test-viator-key",
        viator_base_url="https://api.sandbox.viator.com/partner",
        travel_activity_provider="auto",
    )

    assert get_hotel_provider(settings).name == "liteapi"  # type: ignore[arg-type, union-attr]
    assert get_flight_provider(settings).name == "liteapi"  # type: ignore[arg-type, union-attr]
    assert get_activity_provider(settings).name == "viator"  # type: ignore[arg-type, union-attr]


def test_registry_auto_preserves_legacy_when_liteapi_is_unconfigured():
    settings = SimpleNamespace(
        liteapi_api_key="",
        travel_hotel_provider="auto",
        travel_flight_provider="auto",
        viator_api_key="",
        travel_activity_provider="auto",
    )

    assert get_hotel_provider(settings) is None  # type: ignore[arg-type]
    assert get_flight_provider(settings) is None  # type: ignore[arg-type]
    assert get_activity_provider(settings) is None  # type: ignore[arg-type]


def test_partner_gated_transport_providers_are_not_auto_enabled():
    settings = SimpleNamespace(
        liteapi_api_key="test-key",
        travel_train_provider="auto",
        enable_train_pricing=True,
    )

    assert get_train_provider(settings) is None  # type: ignore[arg-type]


def test_registry_rejects_unverified_explicit_transport_provider():
    settings = SimpleNamespace(
        kiwi_api_key="test-key",
        travel_train_provider="kiwi",
        enable_train_pricing=True,
    )

    with pytest.raises(ValueError, match="Unknown or inactive train provider: kiwi"):
        get_train_provider(settings)  # type: ignore[arg-type]


def test_provider_catalog_keeps_gated_candidates_disabled():
    catalog = {candidate.name: candidate for candidate in provider_catalog()}

    assert catalog["liteapi"].free_mvp_ok is True
    assert catalog["kiwi"].enabled is False
    assert catalog["omio"].enabled is False
    assert catalog["tiqets"].enabled is False
    assert catalog["travelpayouts"].enabled is False


def test_provider_status_reports_readiness_without_secrets():
    settings = SimpleNamespace(
        liteapi_api_key="liteapi-key",
        viator_api_key="",
        openrouteservice_api_key="ors-key",
    )
    status = {item["name"]: item for item in provider_status(settings)}

    assert status["liteapi"]["active"] is True
    assert status["viator"]["configured"] is False
    assert status["openrouteservice"]["active"] is True
    assert "liteapi-key" not in str(status)
    assert "ors-key" not in str(status)


class EmptyProvider:
    name = "empty"

    def search(self):
        return []


class WorkingProvider:
    name = "working"

    def __init__(self):
        self.calls = 0

    def search(self):
        self.calls += 1
        return ["offer"]


def test_provider_chain_falls_back_and_caches():
    working = WorkingProvider()
    cache: ProviderTTLCache[list[str]] = ProviderTTLCache()

    first = run_provider_chain(
        providers=[EmptyProvider(), working],
        cache=cache,
        cache_key="same-query",
        ttl_seconds=60,
        refresh=False,
        empty_value=[],
        call=lambda provider: provider.search(),
    )
    second = run_provider_chain(
        providers=[EmptyProvider(), working],
        cache=cache,
        cache_key="same-query",
        ttl_seconds=60,
        refresh=False,
        empty_value=[],
        call=lambda provider: provider.search(),
    )

    assert first.value == ["offer"]
    assert first.provider == "working"
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.provider == "working"
    assert working.calls == 1


def test_provider_ttl_cache_uses_memory_fallback_when_redis_unavailable(monkeypatch):
    monkeypatch.setenv("CACHE_REDIS_ENABLED", "1")
    monkeypatch.setenv("CACHE_REDIS_URL", "redis://127.0.0.1:6399/0")
    get_settings.cache_clear()

    try:
        cache: ProviderTTLCache[list[str]] = ProviderTTLCache()
        cache.set("fallback-key", ["offer"], provider="working", ttl_seconds=60)

        entry = cache.get("fallback-key")
        assert entry is not None
        assert entry.provider == "working"
        assert entry.value == ["offer"]
    finally:
        monkeypatch.delenv("CACHE_REDIS_ENABLED", raising=False)
        monkeypatch.delenv("CACHE_REDIS_URL", raising=False)
        get_settings.cache_clear()


def test_liteapi_normalizes_live_hotel_rates(monkeypatch):
    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return _response(
            200,
            {
                "hotels": [{"id": "hotel-1", "name": "Harbour Hotel", "rating": 4.6}],
                "data": [
                    {
                        "hotelId": "hotel-1",
                        "roomTypes": [
                            {
                                "name": "Deluxe Room",
                                "offerId": "offer-1",
                                "offerRetailRate": {"amount": 425.5, "currency": "USD"},
                                "rates": [
                                    {
                                        "rateId": "rate-1",
                                        "boardName": "Breakfast",
                                        "refundable": True,
                                        "cancellationPolicies": {"description": "Free until 1 May"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(http_client, "post", fake_post)
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")
    offers = provider.search_hotels(
        HotelSearchQuery(
            destination="London",
            checkin="2026-06-01",
            checkout="2026-06-04",
            guest_nationality="IN",
            currency="USD",
        )
    )

    assert captured["headers"]["X-API-Key"] == "secret"
    assert captured["json"]["iataCode"] == "LON"
    assert captured["json"]["occupancies"] == [{"adults": 2, "children": []}]
    assert len(offers) == 1
    assert offers[0].hotel_name == "Harbour Hotel"
    assert offers[0].search_destination == "London"
    assert offers[0].total.amount == 425.5
    assert offers[0].provider_ref == {
        "hotel_id": "hotel-1",
        "offer_id": "offer-1",
        "rate_id": "rate-1",
    }


def test_liteapi_maps_204_to_no_hotel_availability(monkeypatch):
    monkeypatch.setattr(http_client, "post", lambda *args, **kwargs: _response(204))
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")

    assert (
        provider.search_hotels(
            HotelSearchQuery(destination="Goa", checkin="2026-06-01", checkout="2026-06-04")
        )
        == []
    )


def test_hotel_search_records_the_exact_compared_candidates(monkeypatch):
    class Hotels:
        name = "stub-hotels"

        def __init__(self):
            self.calls = 0

        def search_hotels(self, query):
            self.calls += 1
            return [
                HotelOffer(
                    provider=self.name,
                    provider_ref={
                        "hotel_id": f"hotel-{index}",
                        "offer_id": f"offer-{index}",
                        "rate_id": f"rate-{index}",
                    },
                    hotel_name=name,
                    search_destination=query.destination,
                    room_name="King room",
                    total=Money(amount=amount, currency="EUR"),
                    refundable=True,
                    quoted_at=datetime.now(UTC),
                    rating=rating,
                )
                for index, (name, amount, rating) in enumerate(
                    [("Memmo Alfama", 640, 4.7), ("Hotel Mundial", 520, 4.5)], 1
                )
            ]

    provider = Hotels()
    saved: dict = {}
    hotel_search._HOTEL_RESULT_CACHE.clear()
    monkeypatch.setattr(hotel_search, "get_hotel_providers", lambda: [provider])
    monkeypatch.setattr(hotel_search, "note_price_check", lambda *args: None)
    monkeypatch.setattr(
        trip_planner,
        "record_trip_decision",
        lambda decision: saved.update({"decision": decision}) or True,
    )

    payload = json.loads(
        hotel_search.search_hotels.invoke(
            {
                "city": "Lisbon",
                "checkin": "2026-10-02",
                "checkout": "2026-10-05",
                "currency": "EUR",
            }
        )
    )

    assert provider.calls == 1
    assert payload["decision_id"] == saved["decision"].id
    assert payload["recommended_option_id"] == saved["decision"].chosen_option_id
    assert {option.label for option in saved["decision"].options} == {
        "Memmo Alfama",
        "Hotel Mundial",
    }
    refs = {option.lodging.provider_ref["offer_id"] for option in saved["decision"].options}
    assert refs == {"offer-1", "offer-2"}


def test_liteapi_normalizes_flight_search_and_verify(monkeypatch):
    responses = iter(
        [
            _response(
                200,
                {
                    "data": {
                        "journeys": [
                            {
                                "journeyKey": "journey-1",
                                "segments": [{"origin": "DEL", "destination": "LHR"}],
                                "offers": [
                                    {
                                        "offerId": "flight-1",
                                        "pricing": {"total": {"amount": 820.0, "currency": "USD"}},
                                        "expiration": "2026-04-01T12:00:00Z",
                                        "segmentFares": [{"seatsRemaining": 3}],
                                    }
                                ],
                            }
                        ]
                    }
                },
            ),
            _response(
                200,
                {
                    "changes": {"priceChanged": True},
                    "data": {
                        "journey": {
                            "journeyKey": "journey-1",
                            "segments": [{"origin": "DEL", "destination": "LHR"}],
                            "offers": [
                                {
                                    "offerId": "flight-1",
                                    "pricing": {"total": 845.0, "currency": "USD"},
                                }
                            ],
                        }
                    },
                },
            ),
        ]
    )
    monkeypatch.setattr(http_client, "post", lambda *args, **kwargs: next(responses))
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")

    found = provider.search_flights(
        FlightSearchQuery(
            origin="Delhi",
            destination="London",
            departure_date="2026-04-20",
            currency="USD",
        )
    )
    verified = provider.verify_flight("flight-1")

    assert found[0].provider_ref["offer_id"] == "flight-1"
    assert found[0].total.amount == 820.0
    assert found[0].seats_remaining == 3
    assert verified.total.amount == 845.0
    assert verified.changes == {"priceChanged": True}


def test_flight_search_records_the_exact_compared_candidates(monkeypatch):
    class Flights:
        name = "stub-flights"

        def __init__(self):
            self.calls = 0

        def search_flights(self, query):
            self.calls += 1
            return [
                FlightOffer(
                    provider=self.name,
                    provider_ref={"offer_id": offer_id},
                    total=Money(amount=amount, currency="USD"),
                    segments=segments,
                    quoted_at=datetime.now(UTC),
                )
                for offer_id, amount, segments in [
                    (
                        "direct",
                        900,
                        [{"origin": "DEL", "destination": "LHR", "carrier": "A"}],
                    ),
                    (
                        "connecting",
                        650,
                        [
                            {"origin": "DEL", "destination": "DXB", "carrier": "B"},
                            {"origin": "DXB", "destination": "LHR", "carrier": "B"},
                        ],
                    ),
                ]
            ]

    provider = Flights()
    saved: dict = {}
    flight_search._FLIGHT_RESULT_CACHE.clear()
    monkeypatch.setattr(flight_search, "get_flight_providers", lambda: [provider])
    monkeypatch.setattr(flight_search, "note_price_check", lambda *args: None)
    monkeypatch.setattr(
        trip_planner,
        "record_trip_decision",
        lambda decision: saved.update({"decision": decision}) or True,
    )

    payload = json.loads(
        flight_search.search_flights.invoke(
            {
                "origin": "Delhi",
                "destination": "London",
                "departure_date": "2026-10-02",
                "currency": "USD",
            }
        )
    )

    assert provider.calls == 1
    assert payload["decision_id"] == saved["decision"].id
    assert payload["recommended_option_id"] == saved["decision"].chosen_option_id
    refs = {option.flight.provider_ref["offer_id"] for option in saved["decision"].options}
    assert refs == {"direct", "connecting"}


def test_liteapi_surfaces_provider_errors_without_response_body(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(http_client, "post", fail)
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")

    with pytest.raises(LiteAPIError, match="TimeoutException"):
        provider.search_hotels(
            HotelSearchQuery(destination="Goa", checkin="2026-06-01", checkout="2026-06-04")
        )


def test_viator_normalizes_activity_search_and_schedule(monkeypatch):
    calls: list[dict] = []
    affiliate_url = "https://www.viator.com/tours/London/Example/d737-123?mcid=abc"

    def fake_request(method, url, *, headers, json, timeout=None):
        calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        if method == "POST":
            return _response(
                200,
                {
                    "products": {
                        "results": [
                            {
                                "productCode": "123LON",
                                "title": "London food walk",
                                "destinations": [{"ref": "737", "name": "London"}],
                                "pricing": {
                                    "summary": {"fromPrice": 74.5},
                                    "currency": "GBP",
                                },
                                "duration": {"fixedDurationInMinutes": 180},
                                "reviews": {
                                    "combinedAverageRating": 4.8,
                                    "totalReviews": 321,
                                },
                                "cancellationPolicy": {
                                    "type": "STANDARD",
                                    "description": "Free cancellation up to 24 hours before",
                                },
                                "confirmationType": "INSTANT",
                                "productUrl": affiliate_url,
                            }
                        ]
                    }
                },
            )
        return _response(
            200,
            {
                "bookableItems": [
                    {
                        "productOptionCode": "TG1",
                        "seasons": [{"startDate": "2026-06-01", "endDate": "2026-06-30"}],
                    }
                ]
            },
        )

    monkeypatch.setattr(http_client, "request", fake_request)
    provider = ViatorProvider("sandbox-secret", "https://api.sandbox.viator.com/partner")
    offers = provider.search_activities(
        ActivitySearchQuery(
            destination="London",
            start_date="2026-06-10",
            end_date="2026-06-14",
            adults=2,
            currency="GBP",
        )
    )

    assert calls[0]["headers"] == {
        "exp-api-key": "sandbox-secret",
        "Accept": "application/json;version=2.0",
        "Accept-Language": "en-US",
    }
    assert calls[0]["json"]["productFiltering"]["dateRange"] == {
        "from": "2026-06-10",
        "to": "2026-06-14",
    }
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"].endswith("/availability/schedules/123LON")
    assert offers[0].from_price.amount == 74.5
    assert offers[0].total is None
    assert offers[0].available is True
    assert offers[0].availability_ranges == [
        {"from": "2026-06-01", "to": "2026-06-30"}
    ]
    assert offers[0].duration_minutes == {"from": 180, "to": 180}
    assert offers[0].rating == 4.8
    assert offers[0].review_count == 321
    assert offers[0].provider_url == affiliate_url


def test_viator_surfaces_provider_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(http_client, "request", fail)
    provider = ViatorProvider("sandbox-secret", "https://api.sandbox.viator.com/partner")

    with pytest.raises(ViatorError, match="TimeoutException"):
        provider.search_activities(ActivitySearchQuery(destination="London"))
