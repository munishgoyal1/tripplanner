"""Provider-neutral live travel inventory tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from tripplanner.providers.liteapi import LiteAPIError, LiteAPIProvider
from tripplanner.providers.models import ActivitySearchQuery, FlightSearchQuery, HotelSearchQuery
from tripplanner.providers.registry import (
    get_activity_provider,
    get_flight_provider,
    get_hotel_provider,
)
from tripplanner.providers.viator import ViatorError, ViatorProvider


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

    monkeypatch.setattr(httpx, "post", fake_post)
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
    assert offers[0].total.amount == 425.5
    assert offers[0].provider_ref == {
        "hotel_id": "hotel-1",
        "offer_id": "offer-1",
        "rate_id": "rate-1",
    }


def test_liteapi_maps_204_to_no_hotel_availability(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _response(204))
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")

    assert (
        provider.search_hotels(
            HotelSearchQuery(destination="Goa", checkin="2026-06-01", checkout="2026-06-04")
        )
        == []
    )


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
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: next(responses))
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


def test_liteapi_surfaces_provider_errors_without_response_body(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", fail)
    provider = LiteAPIProvider("secret", "https://api.liteapi.travel/v3.0")

    with pytest.raises(LiteAPIError, match="TimeoutException"):
        provider.search_hotels(
            HotelSearchQuery(destination="Goa", checkin="2026-06-01", checkout="2026-06-04")
        )


def test_viator_normalizes_activity_search_and_schedule(monkeypatch):
    calls: list[dict] = []
    affiliate_url = "https://www.viator.com/tours/London/Example/d737-123?mcid=abc"

    def fake_request(method, url, *, headers, json, timeout):
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

    monkeypatch.setattr(httpx, "request", fake_request)
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

    monkeypatch.setattr(httpx, "request", fail)
    provider = ViatorProvider("sandbox-secret", "https://api.sandbox.viator.com/partner")

    with pytest.raises(ViatorError, match="TimeoutException"):
        provider.search_activities(ActivitySearchQuery(destination="London"))
