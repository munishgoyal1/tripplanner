"""Tests for the public HAFAS REST train/coach provider.

Fixtures mirror payloads captured live from the `hafas-rest-api` family
(v6.db.transport.rest / v6.vbb.transport.rest): journeys carry `legs`,
`refreshToken`, and an optional `price`. Fare-zone networks omit `price`
entirely, which must yield a timed but unpriced offer rather than a fake fare.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tripplanner.config import Settings
from tripplanner.providers.hafas_rest_client import (
    HafasRestCoachSource,
    HafasRestError,
    HafasRestTrainSource,
)
from tripplanner.providers.models import CoachSearchQuery, QuoteStatus, RailSearchQuery
from tripplanner.providers.registry import (
    _selected_provider,
    get_coach_provider,
    get_train_provider,
)


def _leg(
    *,
    departure: str,
    arrival: str,
    origin: str,
    destination: str,
    operator: str,
    product: str = "nationalExpress",
    walking: bool = False,
) -> dict:
    if walking:
        return {
            "walking": True,
            "departure": departure,
            "arrival": arrival,
            "origin": {"name": origin},
            "destination": {"name": destination},
        }
    return {
        "departure": departure,
        "plannedDeparture": departure,
        "arrival": arrival,
        "plannedArrival": arrival,
        "origin": {"type": "stop", "id": "8011160", "name": origin},
        "destination": {"type": "stop", "id": "8000105", "name": destination},
        "tripId": "1|317591|0|80|1052020",
        "line": {
            "type": "line",
            "name": "ICE 702",
            "mode": "train",
            "product": product,
            "operator": {"type": "operator", "name": operator},
        },
    }


PRICED_JOURNEY = {
    "type": "journey",
    "refreshToken": "T$A=1@O=Berlin Hbf@L=8011160@",
    "price": {"amount": 47.9, "currency": "EUR", "hint": None},
    "legs": [
        _leg(
            departure="2026-08-12T08:34:00+02:00",
            arrival="2026-08-12T12:47:00+02:00",
            origin="Berlin Hbf",
            destination="Frankfurt (Main) Hbf",
            operator="DB Fernverkehr AG",
        )
    ],
}

UNPRICED_JOURNEY = {
    "type": "journey",
    "refreshToken": "T$A=1@O=S+U Berlin Hauptbahnhof@L=900003201@",
    "legs": [
        _leg(
            departure="2026-08-12T12:57:00+02:00",
            arrival="2026-08-12T13:32:00+02:00",
            origin="S+U Berlin Hauptbahnhof",
            destination="S Potsdam Hauptbahnhof",
            operator="S-Bahn Berlin GmbH",
            product="suburban",
        )
    ],
}


@pytest.fixture
def rail_query() -> RailSearchQuery:
    return RailSearchQuery(
        origin="Berlin Hbf",
        destination="Frankfurt (Main) Hbf",
        departure_date="2026-08-12",
        adults=1,
        currency="EUR",
    )


@pytest.fixture
def coach_query() -> CoachSearchQuery:
    return CoachSearchQuery(
        origin="Berlin Hbf",
        destination="Hamburg Hbf",
        departure_date="2026-08-12",
        adults=1,
        currency="EUR",
    )


class TestHafasRestTrainSource:
    def test_name_and_default_endpoint(self) -> None:
        source = HafasRestTrainSource()
        assert source.name == "hafas_rest_trains"
        assert source._transport._base_url == "https://v6.db.transport.rest"

    def test_trailing_slash_is_normalised(self) -> None:
        source = HafasRestTrainSource("https://v6.vbb.transport.rest/")
        assert source._transport._base_url == "https://v6.vbb.transport.rest"

    def test_priced_journey_is_parsed(self, rail_query: RailSearchQuery) -> None:
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[PRICED_JOURNEY]):
            offers = source.search_rails(rail_query)

        assert len(offers) == 1
        offer = offers[0]
        assert offer.provider == "hafas_rest_trains"
        assert offer.total is not None
        assert offer.total.amount == 47.9
        assert offer.total.currency == "EUR"
        assert offer.journey_duration_min == 253
        assert offer.changes == 0
        assert offer.direct is True
        assert offer.status == QuoteStatus.LIVE
        assert offer.segments[0]["operator"] == "DB Fernverkehr AG"

    def test_unpriced_journey_keeps_timing_without_inventing_a_fare(
        self, rail_query: RailSearchQuery
    ) -> None:
        source = HafasRestTrainSource("https://v6.vbb.transport.rest")
        with patch.object(source._transport, "journeys", return_value=[UNPRICED_JOURNEY]):
            offers = source.search_rails(rail_query)

        assert len(offers) == 1
        assert offers[0].total is None
        assert offers[0].journey_duration_min == 35

    def test_walking_legs_do_not_count_as_transfers(
        self, rail_query: RailSearchQuery
    ) -> None:
        journey = {
            "refreshToken": "tok",
            "price": {"amount": 30.0, "currency": "EUR"},
            "legs": [
                _leg(
                    departure="2026-08-12T08:00:00+02:00",
                    arrival="2026-08-12T08:05:00+02:00",
                    origin="Hotel",
                    destination="Berlin Hbf",
                    operator="",
                    walking=True,
                ),
                _leg(
                    departure="2026-08-12T08:34:00+02:00",
                    arrival="2026-08-12T10:00:00+02:00",
                    origin="Berlin Hbf",
                    destination="Hannover Hbf",
                    operator="DB Fernverkehr AG",
                ),
            ],
        }
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[journey]):
            offers = source.search_rails(rail_query)

        assert offers[0].changes == 0
        assert offers[0].direct is True
        assert len(offers[0].segments) == 1
        # Duration still spans the walk to the station.
        assert offers[0].journey_duration_min == 120

    def test_transfer_count_uses_transit_legs(self, rail_query: RailSearchQuery) -> None:
        journey = {
            "refreshToken": "tok",
            "price": {"amount": 88.0, "currency": "EUR"},
            "legs": [
                _leg(
                    departure="2026-08-12T08:00:00+02:00",
                    arrival="2026-08-12T10:00:00+02:00",
                    origin="Berlin Hbf",
                    destination="Hannover Hbf",
                    operator="DB Fernverkehr AG",
                ),
                _leg(
                    departure="2026-08-12T10:20:00+02:00",
                    arrival="2026-08-12T12:00:00+02:00",
                    origin="Hannover Hbf",
                    destination="Koln Hbf",
                    operator="DB Fernverkehr AG",
                ),
            ],
        }
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[journey]):
            offers = source.search_rails(rail_query)

        assert offers[0].changes == 1
        assert offers[0].direct is False

    def test_zero_and_missing_price_are_treated_as_unpriced(
        self, rail_query: RailSearchQuery
    ) -> None:
        zero = {**PRICED_JOURNEY, "price": {"amount": 0, "currency": "EUR"}}
        null_currency = {**PRICED_JOURNEY, "price": {"amount": 12.0, "currency": None}}
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[zero, null_currency]):
            offers = source.search_rails(rail_query)

        assert [o.total for o in offers] == [None, None]

    def test_journey_without_transit_legs_is_skipped(
        self, rail_query: RailSearchQuery
    ) -> None:
        walk_only = {
            "refreshToken": "tok",
            "legs": [
                _leg(
                    departure="2026-08-12T08:00:00+02:00",
                    arrival="2026-08-12T08:20:00+02:00",
                    origin="A",
                    destination="B",
                    operator="",
                    walking=True,
                )
            ],
        }
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[walk_only]):
            assert source.search_rails(rail_query) == []

    def test_max_results_is_respected(self, rail_query: RailSearchQuery) -> None:
        rail_query = rail_query.model_copy(update={"max_results": 2})
        source = HafasRestTrainSource()
        with patch.object(
            source._transport, "journeys", return_value=[PRICED_JOURNEY] * 5
        ):
            assert len(source.search_rails(rail_query)) == 2

    def test_endpoint_failure_returns_empty(self, rail_query: RailSearchQuery) -> None:
        source = HafasRestTrainSource()
        with patch.object(
            source._transport, "journeys", side_effect=HafasRestError("HTTP 503")
        ):
            assert source.search_rails(rail_query) == []

    def test_search_trains_is_an_alias(self, rail_query: RailSearchQuery) -> None:
        source = HafasRestTrainSource()
        with patch.object(source._transport, "journeys", return_value=[PRICED_JOURNEY]):
            via_alias = source.search_trains(rail_query)
            direct = source.search_rails(rail_query)

        fields = {"provider", "provider_ref", "total", "segments", "changes", "direct"}
        assert [o.model_dump(include=fields) for o in via_alias] == [
            o.model_dump(include=fields) for o in direct
        ]


class TestHafasRestCoachSource:
    def test_name(self) -> None:
        assert HafasRestCoachSource().name == "hafas_rest_coaches"

    def test_coach_journey_is_parsed(self, coach_query: CoachSearchQuery) -> None:
        journey = {
            "refreshToken": "tok",
            "price": {"amount": 14.99, "currency": "EUR"},
            "legs": [
                _leg(
                    departure="2026-08-12T22:00:00+02:00",
                    arrival="2026-08-13T04:30:00+02:00",
                    origin="Berlin ZOB",
                    destination="Hamburg ZOB",
                    operator="FlixBus",
                    product="bus",
                )
            ],
        }
        source = HafasRestCoachSource()
        with patch.object(source._transport, "journeys", return_value=[journey]):
            offers = source.search_coaches(coach_query)

        assert len(offers) == 1
        assert offers[0].provider == "hafas_rest_coaches"
        assert offers[0].total is not None
        assert offers[0].total.amount == 14.99
        assert offers[0].operator_name == "FlixBus"
        assert offers[0].journey_duration_min == 390

    def test_endpoint_failure_returns_empty(self, coach_query: CoachSearchQuery) -> None:
        source = HafasRestCoachSource()
        with patch.object(
            source._transport, "journeys", side_effect=HafasRestError("boom")
        ):
            assert source.search_coaches(coach_query) == []


class TestStopResolution:
    def test_numeric_place_is_used_directly(self) -> None:
        source = HafasRestTrainSource()
        with patch.object(source._transport, "_get") as get:
            assert source._transport.resolve_stop_id("8011160") == "8011160"
        get.assert_not_called()

    def test_first_stop_result_wins_over_addresses(self) -> None:
        source = HafasRestTrainSource()
        payload = [
            {"type": "location", "id": "999", "name": "Berlin, Some Street"},
            {"type": "stop", "id": "8011160", "name": "Berlin Hbf"},
        ]
        with patch.object(source._transport, "_get", return_value=payload):
            assert source._transport.resolve_stop_id("Berlin Hbf") == "8011160"

    def test_no_stop_match_returns_none(self) -> None:
        source = HafasRestTrainSource()
        with patch.object(source._transport, "_get", return_value=[]):
            assert source._transport.resolve_stop_id("Nowhere") is None

    def test_unresolvable_stop_yields_no_offers(self, rail_query: RailSearchQuery) -> None:
        source = HafasRestTrainSource()
        with patch.object(source._transport, "_get", return_value=[]):
            assert source.search_rails(rail_query) == []


class TestRegistryIntegration:
    def test_hafas_is_selected_when_no_keyed_provider_exists(self) -> None:
        settings = Settings(kiwi_api_key="")
        assert _selected_provider("train", settings) == "hafas"
        assert _selected_provider("coach", settings) == "hafas"

    def test_keyed_provider_takes_priority(self) -> None:
        settings = Settings(kiwi_api_key="kiwi_key")
        assert _selected_provider("train", settings) == "kiwi"

    def test_explicit_override_wins(self) -> None:
        settings = Settings(kiwi_api_key="kiwi_key", travel_train_provider="hafas")
        assert _selected_provider("train", settings) == "hafas"

    def test_get_train_provider_builds_hafas_source(self) -> None:
        settings = Settings(kiwi_api_key="", enable_train_pricing=True)
        provider = get_train_provider(settings)
        assert isinstance(provider, HafasRestTrainSource)

    def test_get_coach_provider_builds_hafas_source(self) -> None:
        settings = Settings(kiwi_api_key="", enable_coach_pricing=True)
        provider = get_coach_provider(settings)
        assert isinstance(provider, HafasRestCoachSource)

    def test_disabled_pricing_returns_none(self) -> None:
        assert get_train_provider(Settings(enable_train_pricing=False)) is None
        assert get_coach_provider(Settings(enable_coach_pricing=False)) is None

    def test_blank_base_url_is_rejected(self) -> None:
        settings = Settings(
            travel_train_provider="hafas",
            hafas_rest_base_url="",
            enable_train_pricing=True,
        )
        with pytest.raises(ValueError, match="HAFAS_REST_BASE_URL"):
            get_train_provider(settings)

    def test_ferry_remains_kiwi_only(self) -> None:
        settings = Settings(kiwi_api_key="kiwi_key")
        assert _selected_provider("ferry", settings) == "kiwi"
