"""Read-only train and coach search via public HAFAS REST instances.

Targets the `hafas-rest-api` family hosted at *.transport.rest — notably
`v6.db.transport.rest` (Deutsche Bahn, long-distance rail with fares) plus the
regional VBB/BVG instances. These endpoints need no API key and are rate limited
to roughly 100 requests/minute.

Fares are only present when the upstream network publishes them: Deutsche Bahn
long-distance journeys carry `price`, while fare-zone networks such as VBB do
not. An unpriced journey is still returned so the itinerary keeps its timing and
transfer count, with `total` left unset rather than invented.

Schema verified live against the documented `/locations` and `/journeys` routes:
https://v6.db.transport.rest/api.html
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from tripplanner.providers.models import (
    CoachOffer,
    CoachSearchQuery,
    Money,
    QuoteStatus,
    RailOffer,
    RailSearchQuery,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://v6.db.transport.rest"

# Departure time used when the caller supplies a date with no time of day.
# Sent without an offset so the upstream network resolves it in its own local
# timezone, which is what "leave in the morning" means to a traveller.
DEFAULT_DEPARTURE_TIME = "08:00:00"

_RAIL_PRODUCTS = {
    "nationalExpress": "true",
    "national": "true",
    "regionalExpress": "true",
    "regional": "true",
    "suburban": "true",
    "bus": "false",
    "ferry": "false",
    "subway": "false",
    "tram": "false",
    "taxi": "false",
}

_COACH_PRODUCTS = {
    "nationalExpress": "false",
    "national": "false",
    "regionalExpress": "false",
    "regional": "false",
    "suburban": "false",
    "bus": "true",
    "ferry": "false",
    "subway": "false",
    "tram": "false",
    "taxi": "false",
}


class HafasRestError(RuntimeError):
    """HAFAS REST endpoint returned an error or unusable payload."""


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_transit_leg(leg: dict[str, Any]) -> bool:
    """Walking transfers are routing filler, not a ride the traveller books."""
    return not leg.get("walking")


def _journey_duration_min(legs: list[dict[str, Any]]) -> int | None:
    if not legs:
        return None
    start = _parse_dt(legs[0].get("departure") or legs[0].get("plannedDeparture"))
    end = _parse_dt(legs[-1].get("arrival") or legs[-1].get("plannedArrival"))
    if start is None or end is None:
        return None
    minutes = int((end - start).total_seconds() // 60)
    return minutes if minutes > 0 else None


def _operator_name(leg: dict[str, Any]) -> str:
    line = leg.get("line") or {}
    operator = line.get("operator") or {}
    return operator.get("name") or line.get("name") or ""


def _segments(legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for leg in legs:
        line = leg.get("line") or {}
        segments.append(
            {
                "departure": leg.get("departure") or leg.get("plannedDeparture"),
                "arrival": leg.get("arrival") or leg.get("plannedArrival"),
                "origin": (leg.get("origin") or {}).get("name"),
                "destination": (leg.get("destination") or {}).get("name"),
                "operator": _operator_name(leg),
                "line": line.get("name"),
                "vehicle_type": line.get("product") or line.get("mode"),
            }
        )
    return segments


def _price(journey: dict[str, Any]) -> Money | None:
    """Return the published fare, or None when the network publishes none."""
    price = journey.get("price")
    if not isinstance(price, dict):
        return None
    amount = price.get("amount")
    currency = price.get("currency")
    if not isinstance(amount, (int, float)) or amount <= 0 or not currency:
        return None
    return Money(amount=float(amount), currency=str(currency))


def _departure_param(departure_date: str) -> str:
    date = (departure_date or "").strip()
    if not date:
        return ""
    return date if "T" in date else f"{date}T{DEFAULT_DEPARTURE_TIME}"


class _HafasRestTransport:
    """Shared HTTP access to one hafas-rest-api instance."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 20.0) -> None:
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout

    def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = httpx.get(
                f"{self._base_url}/{path.lstrip('/')}",
                params=params,
                headers={"Accept": "application/json", "User-Agent": "tripplanner/1.0"},
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise HafasRestError(
                f"{self._base_url} returned HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HafasRestError(
                f"{self._base_url} request failed: {type(exc).__name__}"
            ) from exc

    def resolve_stop_id(self, place: str) -> str | None:
        """Map a free-text place name to a stop ID the journeys route accepts."""
        place = (place or "").strip()
        if not place:
            return None
        if place.isdigit():
            return place
        payload = self._get(
            "locations",
            {"query": place, "results": "3", "addresses": "false", "poi": "false"},
        )
        if not isinstance(payload, list):
            return None
        for entry in payload:
            if isinstance(entry, dict) and entry.get("type") == "stop" and entry.get("id"):
                return str(entry["id"])
        return None

    def journeys(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        max_results: int,
        products: dict[str, str],
    ) -> list[dict[str, Any]]:
        from_id = self.resolve_stop_id(origin)
        to_id = self.resolve_stop_id(destination)
        if not from_id or not to_id:
            raise HafasRestError(f"Could not resolve stops for {origin!r} -> {destination!r}")

        params: dict[str, str] = {
            "from": from_id,
            "to": to_id,
            "results": str(max(1, max_results)),
            "tickets": "true",
            "stopovers": "false",
            "remarks": "false",
            "pretty": "false",
            **products,
        }
        departure = _departure_param(departure_date)
        if departure:
            params["departure"] = departure

        payload = self._get("journeys", params)
        journeys = payload.get("journeys") if isinstance(payload, dict) else None
        return [j for j in journeys or [] if isinstance(j, dict)]


class HafasRestTrainSource:
    """Read-only train search over a public HAFAS REST instance."""

    name = "hafas_rest_trains"

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._transport = _HafasRestTransport(base_url)

    def search_rails(self, query: RailSearchQuery) -> list[RailOffer]:
        try:
            journeys = self._transport.journeys(
                query.origin,
                query.destination,
                query.departure_date,
                query.max_results,
                _RAIL_PRODUCTS,
            )
        except HafasRestError as exc:
            logger.warning("HAFAS train search failed: %s", exc)
            return []

        quoted_at = datetime.now(UTC)
        offers: list[RailOffer] = []
        for journey in journeys:
            legs = [leg for leg in journey.get("legs") or [] if isinstance(leg, dict)]
            transit_legs = [leg for leg in legs if _is_transit_leg(leg)]
            if not transit_legs:
                continue
            changes = max(0, len(transit_legs) - 1)
            offers.append(
                RailOffer(
                    provider=self.name,
                    provider_ref={"refresh_token": str(journey.get("refreshToken") or "")},
                    total=_price(journey),
                    segments=_segments(transit_legs),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(legs),
                    changes=changes,
                    direct=changes == 0,
                )
            )
        return offers[: query.max_results]

    def search_trains(self, query: RailSearchQuery) -> list[RailOffer]:
        return self.search_rails(query)


class HafasRestCoachSource:
    """Read-only coach/bus search over a public HAFAS REST instance."""

    name = "hafas_rest_coaches"

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._transport = _HafasRestTransport(base_url)

    def search_coaches(self, query: CoachSearchQuery) -> list[CoachOffer]:
        try:
            journeys = self._transport.journeys(
                query.origin,
                query.destination,
                query.departure_date,
                query.max_results,
                _COACH_PRODUCTS,
            )
        except HafasRestError as exc:
            logger.warning("HAFAS coach search failed: %s", exc)
            return []

        quoted_at = datetime.now(UTC)
        offers: list[CoachOffer] = []
        for journey in journeys:
            legs = [leg for leg in journey.get("legs") or [] if isinstance(leg, dict)]
            transit_legs = [leg for leg in legs if _is_transit_leg(leg)]
            if not transit_legs:
                continue
            offers.append(
                CoachOffer(
                    provider=self.name,
                    provider_ref={"refresh_token": str(journey.get("refreshToken") or "")},
                    total=_price(journey),
                    segments=_segments(transit_legs),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE,
                    journey_duration_min=_journey_duration_min(legs),
                    operator_name=_operator_name(transit_legs[0]) or None,
                )
            )
        return offers[: query.max_results]
