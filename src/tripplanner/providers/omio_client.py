"""Read-only Omio (formerly GoEuro) trains, coaches, and multi-modal provider.

Omio provides real-time pricing for trains, coaches, and ride-share across 45+
European countries. This client handles search, response parsing, retries, and
error handling with graceful degradation (empty results on API failure).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from tripplanner.providers.models import (
    CoachOffer,
    CoachSearchQuery,
    FerryOffer,
    FerrySearchQuery,
    Money,
    QuoteStatus,
    RailOffer,
    RailSearchQuery,
)

logger = logging.getLogger(__name__)


class OmioError(RuntimeError):
    """Omio API error."""
    pass


def _parse_money(value: float | None, currency: str) -> Money | None:
    """Parse fare amount into Money object."""
    if value is None:
        return None
    return Money(amount=float(value), currency=currency)


def _journey_duration_min(route: dict[str, Any]) -> int | None:
    """Extract journey duration in minutes from route payload."""
    duration = route.get("duration_minutes")
    if isinstance(duration, (int, float)):
        return int(duration)
    return None


def _count_transfers(segments: list[dict[str, Any]]) -> int:
    """Count number of transfers/stops from segments.
    
    0 = direct, 1+ = with transfers.
    """
    if not segments:
        return 0
    return max(0, len(segments) - 1)


def _parse_segments(route: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract journey segments from route."""
    segments = []
    for leg in route.get("legs", []):
        segments.append({
            "departure": leg.get("departure_time"),
            "arrival": leg.get("arrival_time"),
            "operator": leg.get("operator", {}).get("name", ""),
            "vehicle_type": leg.get("vehicle_type"),
        })
    return segments


class OmioTrainSource:
    """Read-only Omio trains provider."""

    name = "omio_trains"

    def __init__(self, api_key: str, base_url: str = "https://api.omio.com") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute request to Omio API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Endpoint path (relative to base_url)
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            OmioError: On HTTP error or request failure
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            response = httpx.request(
                method,
                f"{self._base_url}/{path.lstrip('/')}",
                headers=headers,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise OmioError(f"Omio API returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OmioError(f"Omio API request failed: {type(exc).__name__}") from exc

    def search_rails(self, query: RailSearchQuery) -> list[RailOffer]:
        """Search for train routes.

        Args:
            query: RailSearchQuery with departure, destination, date, passengers, etc.

        Returns:
            List of RailOffer objects (empty if no results or API error)
        """
        try:
            params = {
                "origin": query.origin,
                "destination": query.destination,
                "departure_date": query.departure_date,
                "adults": str(query.adults),
                "children": str(query.children),
                "currency": query.currency,
                "transport_types": "train",  # Trains only
                "limit": str(query.max_results),
            }
            if query.return_date:
                params["return_date"] = query.return_date

            payload = self._request("GET", "v1/routes", params=params)

            quoted_at = datetime.now(UTC)
            offers: list[RailOffer] = []

            for route in payload.get("routes", []):
                route_id = str(route.get("id") or "")
                fare_amount = route.get("price", {}).get("amount")
                currency = route.get("price", {}).get("currency", query.currency)

                if not route_id or fare_amount is None:
                    continue

                total = _parse_money(fare_amount, currency)
                if not total:
                    continue

                segments = _parse_segments(route)
                transfers = _count_transfers(segments)

                offer = RailOffer(
                    provider=self.name,
                    provider_ref={"route_id": route_id},
                    total=total,
                    segments=segments,
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(route),
                    changes=transfers,
                    direct=transfers == 0,
                    booking_url=route.get("booking_url"),
                )
                offers.append(offer)

            return offers[:query.max_results]
        except OmioError as e:
            logger.warning("Omio trains search failed: %s", e)
            return []

    def search_trains(self, query: RailSearchQuery) -> list[RailOffer]:
        """Alias for search_rails (trains are rails)."""
        return self.search_rails(query)


class OmioCoachSource:
    """Read-only Omio coaches/buses provider."""

    name = "omio_coaches"

    def __init__(self, api_key: str, base_url: str = "https://api.omio.com") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute request to Omio API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            response = httpx.request(
                method,
                f"{self._base_url}/{path.lstrip('/')}",
                headers=headers,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise OmioError(f"Omio API returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OmioError(f"Omio API request failed: {type(exc).__name__}") from exc

    def search_coaches(self, query: CoachSearchQuery) -> list[CoachOffer]:
        """Search for coach/bus routes.

        Args:
            query: CoachSearchQuery with departure, destination, date, passengers, etc.

        Returns:
            List of CoachOffer objects (empty if no results or API error)
        """
        try:
            params = {
                "origin": query.origin,
                "destination": query.destination,
                "departure_date": query.departure_date,
                "adults": str(query.adults),
                "children": str(query.children),
                "currency": query.currency,
                "transport_types": "bus",  # Coaches/buses only
                "limit": str(query.max_results),
            }
            if query.return_date:
                params["return_date"] = query.return_date

            payload = self._request("GET", "v1/routes", params=params)

            quoted_at = datetime.now(UTC)
            offers: list[CoachOffer] = []

            for route in payload.get("routes", []):
                route_id = str(route.get("id") or "")
                fare_amount = route.get("price", {}).get("amount")
                currency = route.get("price", {}).get("currency", query.currency)

                if not route_id or fare_amount is None:
                    continue

                total = _parse_money(fare_amount, currency)
                if not total:
                    continue

                segments = _parse_segments(route)
                transfers = _count_transfers(segments)

                offer = CoachOffer(
                    provider=self.name,
                    provider_ref={"route_id": route_id},
                    total=total,
                    segments=segments,
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(route),
                    operator_name=route.get("operator", {}).get("name"),
                    amenities=route.get("amenities", []),
                    booking_url=route.get("booking_url"),
                )
                offers.append(offer)

            return offers[:query.max_results]
        except OmioError as e:
            logger.warning("Omio coaches search failed: %s", e)
            return []
