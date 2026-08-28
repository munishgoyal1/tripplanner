"""Tests for Omio provider integration (train and coach search).

Tests cover:
  - Registry configuration and provider selection
  - Omio API client request handling
  - Search result parsing and validation
  - Graceful degradation on API errors
  - Auto-provider selection logic
  - Configuration validation
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tripplanner.config import Settings
from tripplanner.providers.models import (
    CoachSearchQuery,
    QuoteStatus,
    RailSearchQuery,
)
from tripplanner.providers.omio_client import OmioCoachSource, OmioError, OmioTrainSource
from tripplanner.providers.registry import (
    _selected_provider,
    get_coach_provider,
    get_train_provider,
)


class TestOmioTrainSource:
    """OmioTrainSource integration tests."""

    @pytest.fixture
    def source(self) -> OmioTrainSource:
        return OmioTrainSource(
            api_key="test_key_12345",
            base_url="https://api.omio.com",
        )

    def test_init(self, source: OmioTrainSource) -> None:
        """Verify initialization."""
        assert source._api_key == "test_key_12345"
        assert source._base_url == "https://api.omio.com"
        assert source.name == "omio_trains"

    def test_search_trains_no_results(self, source: OmioTrainSource) -> None:
        """Return empty list when API returns no routes."""
        with patch.object(source, "_request", return_value={"routes": []}):
            query = RailSearchQuery(
                origin="BER",
                destination="PAR",
                departure_date="2025-05-15",
                adults=1,
                currency="EUR",
            )
            offers = source.search_trains(query)
            assert offers == []

    def test_search_trains_single_result(self, source: OmioTrainSource) -> None:
        """Parse and return single train result."""
        route = {
            "id": "route_123",
            "price": {"amount": 45.99, "currency": "EUR"},
            "duration_minutes": 480,
            "legs": [
                {
                    "departure_time": "2025-05-15T08:00:00Z",
                    "arrival_time": "2025-05-15T16:00:00Z",
                    "operator": {"name": "Deutsche Bahn"},
                    "vehicle_type": "train",
                }
            ],
            "booking_url": "https://omio.com/book/123",
        }
        with patch.object(source, "_request", return_value={"routes": [route]}):
            query = RailSearchQuery(
                origin="BER",
                destination="PAR",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_trains(query)

            assert len(offers) == 1
            offer = offers[0]
            assert offer.provider == "omio_trains"
            assert offer.total.amount == 45.99
            assert offer.total.currency == "EUR"
            assert offer.journey_duration_min == 480
            assert offer.changes == 0
            assert offer.direct is True
            assert offer.status == QuoteStatus.LIVE

    def test_search_trains_multiple_results_returned(self, source: OmioTrainSource) -> None:
        """Return multiple results in API order."""
        routes = [
            {
                "id": "route_1",
                "price": {"amount": 60.00, "currency": "EUR"},
                "duration_minutes": 420,
                "legs": [
                    {
                        "departure_time": "2025-05-15T14:00:00Z",
                        "arrival_time": "2025-05-15T21:00:00Z",
                        "operator": {"name": "Renfe"},
                    }
                ],
            },
            {
                "id": "route_2",
                "price": {"amount": 45.00, "currency": "EUR"},
                "duration_minutes": 600,
                "legs": [
                    {
                        "departure_time": "2025-05-15T06:00:00Z",
                        "arrival_time": "2025-05-15T16:00:00Z",
                        "operator": {"name": "Deutsche Bahn"},
                    }
                ],
            },
        ]
        with patch.object(source, "_request", return_value={"routes": routes}):
            query = RailSearchQuery(
                origin="BER",
                destination="PAR",
                departure_date="2025-05-15",
                adults=2,
            )
            offers = source.search_trains(query)

            assert len(offers) == 2
            # Results returned in API order
            assert offers[0].provider_ref["route_id"] == "route_1"
            assert offers[1].provider_ref["route_id"] == "route_2"

    def test_search_trains_malformed_result_skipped(
        self, source: OmioTrainSource
    ) -> None:
        """Skip malformed results without crashing."""
        routes = [
            {"id": "route_1"},  # Missing price
            {
                "id": "route_2",
                "price": {"amount": 50.00, "currency": "EUR"},
                "duration_minutes": 300,
                "legs": [
                    {
                        "departure_time": "2025-05-15T10:00:00Z",
                        "arrival_time": "2025-05-15T15:00:00Z",
                        "operator": {"name": "SNCF"},
                    }
                ],
            },
        ]
        with patch.object(source, "_request", return_value={"routes": routes}):
            query = RailSearchQuery(
                origin="BER",
                destination="PAR",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_trains(query)

            assert len(offers) == 1  # Only the valid result
            assert offers[0].provider_ref["route_id"] == "route_2"

    def test_search_trains_api_error_returns_empty(
        self, source: OmioTrainSource
    ) -> None:
        """Return empty list on API error."""
        with patch.object(source, "_request", side_effect=OmioError("API error")):
            query = RailSearchQuery(
                origin="BER",
                destination="PAR",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_trains(query)
            assert offers == []

    def test_search_rails_alias(self, source: OmioTrainSource) -> None:
        """search_rails() delegates to search_trains()."""
        route = {
            "id": "route_123",
            "price": {"amount": 35.00, "currency": "EUR"},
            "duration_minutes": 300,
            "legs": [
                {
                    "departure_time": "2025-05-15T09:00:00Z",
                    "arrival_time": "2025-05-15T14:00:00Z",
                    "operator": {"name": "SNCF"},
                }
            ],
        }
        with patch.object(source, "_request", return_value={"routes": [route]}):
            query = RailSearchQuery(
                origin="PAR",
                destination="LYO",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_rails(query)
            assert len(offers) == 1
            assert offers[0].total.amount == 35.00


class TestOmioCoachSource:
    """OmioCoachSource integration tests."""

    @pytest.fixture
    def source(self) -> OmioCoachSource:
        return OmioCoachSource(
            api_key="test_key_67890",
            base_url="https://api.omio.com",
        )

    def test_init(self, source: OmioCoachSource) -> None:
        """Verify initialization."""
        assert source._api_key == "test_key_67890"
        assert source._base_url == "https://api.omio.com"
        assert source.name == "omio_coaches"

    def test_search_coaches_no_results(self, source: OmioCoachSource) -> None:
        """Return empty list when API returns no routes."""
        with patch.object(source, "_request", return_value={"routes": []}):
            query = CoachSearchQuery(
                origin="London",
                destination="Paris",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_coaches(query)
            assert offers == []

    def test_search_coaches_single_result(self, source: OmioCoachSource) -> None:
        """Parse and return single coach result."""
        route = {
            "id": "coach_456",
            "price": {"amount": 25.50, "currency": "EUR"},
            "duration_minutes": 600,
            "operator": {"name": "FlixBus"},
            "legs": [
                {
                    "departure_time": "2025-05-15T22:00:00Z",
                    "arrival_time": "2025-05-16T08:00:00Z",
                    "operator": {"name": "FlixBus"},
                    "vehicle_type": "bus",
                }
            ],
            "amenities": ["wifi", "power_outlet"],
            "booking_url": "https://omio.com/book/456",
        }
        with patch.object(source, "_request", return_value={"routes": [route]}):
            query = CoachSearchQuery(
                origin="London",
                destination="Paris",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_coaches(query)

            assert len(offers) == 1
            offer = offers[0]
            assert offer.provider == "omio_coaches"
            assert offer.total.amount == 25.50
            assert offer.total.currency == "EUR"
            assert offer.journey_duration_min == 600
            assert offer.operator_name == "FlixBus"
            assert "wifi" in offer.amenities
            assert offer.status == QuoteStatus.LIVE

    def test_search_coaches_multiple_results_returned(
        self, source: OmioCoachSource
    ) -> None:
        """Return multiple results in API order."""
        routes = [
            {
                "id": "coach_1",
                "price": {"amount": 22.00, "currency": "EUR"},
                "duration_minutes": 600,
                "operator": {"name": "FlixBus"},
                "legs": [
                    {
                        "departure_time": "2025-05-15T20:00:00Z",
                        "arrival_time": "2025-05-16T06:00:00Z",
                        "operator": {"name": "FlixBus"},
                    }
                ],
            },
            {
                "id": "coach_2",
                "price": {"amount": 18.00, "currency": "EUR"},
                "duration_minutes": 720,
                "operator": {"name": "BlaBlaCar"},
                "legs": [
                    {
                        "departure_time": "2025-05-15T20:00:00Z",
                        "arrival_time": "2025-05-16T08:00:00Z",
                        "operator": {"name": "BlaBlaCar"},
                    }
                ],
            },
        ]
        with patch.object(source, "_request", return_value={"routes": routes}):
            query = CoachSearchQuery(
                origin="London",
                destination="Paris",
                departure_date="2025-05-15",
                adults=1,
            )
            offers = source.search_coaches(query)

            assert len(offers) == 2
            # Results returned in API order
            assert offers[0].provider_ref["route_id"] == "coach_1"
            assert offers[1].provider_ref["route_id"] == "coach_2"

    def test_search_coaches_api_error_returns_empty(
        self, source: OmioCoachSource
    ) -> None:
        """Return empty list on API error."""
        with patch.object(source, "_request", side_effect=OmioError("Connection error")):
            query = CoachSearchQuery(
                origin="London",
                destination="Paris",
                departure_date="2025-05-15",
                adults=2,
            )
            offers = source.search_coaches(query)
            assert offers == []


class TestRegistryIntegration:
    """Test Omio remains an experimental, partner-gated adapter."""

    def test_get_train_provider_does_not_auto_enable_omio(self) -> None:
        """Omio keys alone do not prove approved current API access."""
        settings = Settings(omio_api_key="test_key_abc", kiwi_api_key="")
        provider = get_train_provider(settings)

        assert provider is None

    def test_get_train_provider_returns_none_without_key(self) -> None:
        """Return None when no train provider is configured."""
        settings = Settings(
            omio_api_key="",
            kiwi_api_key="",
            enable_train_pricing=True,
        )
        provider = get_train_provider(settings)
        assert provider is None

    def test_get_train_provider_disabled_returns_none(self) -> None:
        """Return None when train pricing is disabled."""
        settings = Settings(
            omio_api_key="test_key",
            enable_train_pricing=False,
        )
        provider = get_train_provider(settings)
        assert provider is None

    def test_get_coach_provider_does_not_auto_enable_omio(self) -> None:
        """Coach pricing is disabled until approved partner access is confirmed."""
        settings = Settings(omio_api_key="test_key_xyz", kiwi_api_key="")
        provider = get_coach_provider(settings)

        assert provider is None

    def test_get_coach_provider_returns_none_without_key(self) -> None:
        """Return None when no coach provider is configured."""
        settings = Settings(
            omio_api_key="",
            kiwi_api_key="",
            enable_coach_pricing=True,
        )
        provider = get_coach_provider(settings)
        assert provider is None

    def test_selected_provider_does_not_prioritize_gated_train_candidates(self) -> None:
        """Partner-gated keys do not make Omio/Kiwi active providers."""
        settings = Settings(omio_api_key="omio_key", kiwi_api_key="kiwi_key")
        provider = _selected_provider("train", settings)
        assert provider is None

    def test_selected_provider_does_not_fallback_to_kiwi(self) -> None:
        """Kiwi is also partner-gated and not a free public fallback."""
        settings = Settings(omio_api_key="", kiwi_api_key="kiwi_key")
        provider = _selected_provider("train", settings)
        assert provider is None

    def test_selected_provider_explicit_override(self) -> None:
        """Explicit provider selection overrides auto-selection."""
        settings = Settings(
            omio_api_key="omio_key",
            kiwi_api_key="kiwi_key",
            travel_train_provider="kiwi",
        )
        provider = _selected_provider("train", settings)
        assert provider == "kiwi"

    def test_get_train_provider_raises_on_missing_key(self) -> None:
        """Raise ValueError when explicit provider is selected but key is missing."""
        settings = Settings(
            omio_api_key="",
            travel_train_provider="omio",
            enable_train_pricing=True,
        )
        with pytest.raises(ValueError, match="Unknown or inactive train provider: omio"):
            get_train_provider(settings)

    def test_get_coach_provider_raises_on_missing_key(self) -> None:
        """Raise ValueError when explicit coach provider is selected but key is missing."""
        settings = Settings(
            omio_api_key="",
            travel_coach_provider="omio",
            enable_coach_pricing=True,
        )
        with pytest.raises(ValueError, match="Unknown or inactive coach provider: omio"):
            get_coach_provider(settings)

    def test_ferry_provider_does_not_auto_enable_kiwi(self) -> None:
        """Ferry pricing remains unavailable until approved API access exists."""
        from tripplanner.providers.registry import get_ferry_provider

        settings = Settings(omio_api_key="test_key", kiwi_api_key="kiwi_key")
        provider = _selected_provider("ferry", settings)
        assert provider is None
        assert get_ferry_provider(settings) is None


class TestOmioErrorHandling:
    """Test graceful error handling in Omio client."""

    def test_omio_error_message(self) -> None:
        """OmioError provides clear message."""
        error = OmioError("Service unavailable")
        assert str(error) == "Service unavailable"

    def test_request_http_error_raises_omio_error(self) -> None:
        """HTTP errors are converted to OmioError."""
        source = OmioTrainSource(api_key="key")
        with patch("tripplanner.providers.omio_client.http_client.request") as mock_request:
            from httpx import HTTPStatusError, Response
            response = Response(status_code=500)
            mock_request.side_effect = HTTPStatusError(
                "Server Error", request=None, response=response
            )

            with pytest.raises(OmioError, match="HTTP 500"):
                source._request("GET", "v1/trains", params={"from": "BER"})

    def test_request_json_error_raises_omio_error(self) -> None:
        """JSON parse errors are converted to OmioError."""
        source = OmioTrainSource(api_key="key")
        with patch("tripplanner.providers.omio_client.http_client.request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_request.return_value = mock_response

            with pytest.raises(OmioError):
                source._request("GET", "v1/trains")
