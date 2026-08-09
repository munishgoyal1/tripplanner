"""Experimental Kiwi.com transport adapter.

Kiwi/Tequila is partner-gated and is not registered as an active MVP provider.
Keep this module out of default execution until current approved API access and
terms are verified for the account.
"""

from __future__ import annotations

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


class KiwiError(RuntimeError):
    pass


def _parse_money(value: float | None, currency: str) -> Money | None:
    """Parse fare amount into Money object."""
    if value is None:
        return None
    return Money(amount=float(value), currency=currency)


def _journey_duration_min(route: dict[str, Any]) -> int | None:
    """Extract journey duration in minutes from route payload."""
    duration = route.get("duration")
    if isinstance(duration, (int, float)):
        return int(duration)
    return None


def _parse_segments(route: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract journey segments from route."""
    segments = []
    for leg in route.get("legs", []):
        segments.append({
            "departure": leg.get("departure"),
            "arrival": leg.get("arrival"),
            "duration": leg.get("duration"),
            "operator": leg.get("operator"),
        })
    return segments


class KiwiTrainSource:
    """Read-only Kiwi.com trains provider."""

    name = "kiwi_trains"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute request to Kiwi API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Endpoint path (relative to base_url)
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            KiwiError: On HTTP error or request failure
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
            raise KiwiError(f"Kiwi API returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise KiwiError(f"Kiwi API request failed: {type(exc).__name__}") from exc

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
                "limit": str(query.max_results),
            }
            if query.return_date:
                params["return_date"] = query.return_date

            payload = self._request("GET", "trains/search", params=params)

            quoted_at = datetime.now(UTC)
            offers: list[RailOffer] = []

            for route in payload.get("data", []):
                route_id = str(route.get("id") or "")
                fare_amount = route.get("price")

                if not route_id or fare_amount is None:
                    continue

                total = _parse_money(fare_amount, query.currency)
                if not total:
                    continue

                offer = RailOffer(
                    provider=self.name,
                    provider_ref={"route_id": route_id},
                    total=total,
                    segments=_parse_segments(route),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(route),
                    changes=route.get("stops", 0),
                    direct=route.get("stops", 0) == 0,
                    booking_url=route.get("booking_url"),
                )
                offers.append(offer)

            return offers[:query.max_results]
        except KiwiError as e:
            # Log error but don't propagate; return empty list for graceful degradation
            print(f"Kiwi trains search failed: {e}")
            return []

    def search_trains(self, query: RailSearchQuery) -> list[RailOffer]:
        """Alias for search_rails (trains are rails)."""
        return self.search_rails(query)


class KiwiCoachSource:
    """Read-only Kiwi.com coaches/buses provider."""

    name = "kiwi_coaches"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute request to Kiwi API."""
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
            raise KiwiError(f"Kiwi API returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise KiwiError(f"Kiwi API request failed: {type(exc).__name__}") from exc

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
                "limit": str(query.max_results),
            }
            if query.return_date:
                params["return_date"] = query.return_date

            payload = self._request("GET", "buses/search", params=params)

            quoted_at = datetime.now(UTC)
            offers: list[CoachOffer] = []

            for route in payload.get("data", []):
                route_id = str(route.get("id") or "")
                fare_amount = route.get("price")

                if not route_id or fare_amount is None:
                    continue

                total = _parse_money(fare_amount, query.currency)
                if not total:
                    continue

                offer = CoachOffer(
                    provider=self.name,
                    provider_ref={"route_id": route_id},
                    total=total,
                    segments=_parse_segments(route),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(route),
                    operator_name=route.get("operator"),
                    amenities=route.get("amenities", []),
                    booking_url=route.get("booking_url"),
                )
                offers.append(offer)

            return offers[:query.max_results]
        except KiwiError as e:
            print(f"Kiwi coaches search failed: {e}")
            return []


class KiwiFerrySource:
    """Read-only Kiwi.com ferries provider."""

    name = "kiwi_ferries"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute request to Kiwi API."""
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
            raise KiwiError(f"Kiwi API returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise KiwiError(f"Kiwi API request failed: {type(exc).__name__}") from exc

    def search_ferries(self, query: FerrySearchQuery) -> list[FerryOffer]:
        """Search for ferry routes.

        Args:
            query: FerrySearchQuery with departure, destination, date, passengers, etc.

        Returns:
            List of FerryOffer objects (empty if no results or API error)
        """
        try:
            params = {
                "origin": query.origin,
                "destination": query.destination,
                "departure_date": query.departure_date,
                "adults": str(query.adults),
                "children": str(query.children),
                "currency": query.currency,
                "limit": str(query.max_results),
            }
            if query.return_date:
                params["return_date"] = query.return_date

            payload = self._request("GET", "ferries/search", params=params)

            quoted_at = datetime.now(UTC)
            offers: list[FerryOffer] = []

            for route in payload.get("data", []):
                route_id = str(route.get("id") or "")
                fare_amount = route.get("price")

                if not route_id or fare_amount is None:
                    continue

                total = _parse_money(fare_amount, query.currency)
                if not total:
                    continue

                offer = FerryOffer(
                    provider=self.name,
                    provider_ref={"route_id": route_id},
                    total=total,
                    segments=_parse_segments(route),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(route),
                    route_name=route.get("route_name"),
                    cabin_options=route.get("cabin_options", []),
                    booking_url=route.get("booking_url"),
                )
                offers.append(offer)

            return offers[:query.max_results]
        except KiwiError as e:
            print(f"Kiwi ferries search failed: {e}")
            return []
