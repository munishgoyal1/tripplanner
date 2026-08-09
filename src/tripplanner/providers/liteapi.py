"""Read-only LiteAPI hotel and flight availability adapter.

Capability is limited to what the vendor documents: hotel rates and the
legs-based flight rates/verify endpoints. LiteAPI publishes no rail, coach or
ferry API, so this adapter must not grow one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from tripplanner.providers.models import (
    FlightOffer,
    FlightSearchQuery,
    HotelOffer,
    HotelSearchQuery,
    Money,
)


class LiteAPIError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: Any, default_currency: str) -> Money | None:
    if isinstance(value, list):
        for item in value:
            parsed = _money(item, default_currency)
            if parsed:
                return parsed
        return None
    if not isinstance(value, dict):
        amount = _number(value)
        return Money(amount=amount, currency=default_currency) if amount is not None else None

    amount = _number(value.get("amount"))
    total_value = value.get("total")
    if amount is None:
        amount = _number(total_value)
    if amount is None:
        for nested in (
            total_value,
            value.get("display"),
            value.get("final"),
            value.get("offerRetailRate"),
            value.get("retailRate"),
        ):
            parsed = _money(nested, default_currency)
            if parsed:
                return parsed
        return None
    return Money(
        amount=amount,
        currency=str(value.get("currency") or default_currency),
        taxes=_number(value.get("taxes")),
        fees=_number(value.get("fees")),
        due_at_property=_number(value.get("dueAtProperty")),
    )


def _cancellation_summary(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [part for item in value if (part := _cancellation_summary(item))]
        return "; ".join(parts) or None
    if isinstance(value, dict):
        for key in ("description", "remarks", "text", "name"):
            if value.get(key):
                return str(value[key])
        parts = [
            f"{key}: {item}"
            for key, item in value.items()
            if isinstance(item, (str, int, float, bool))
        ]
        return "; ".join(parts) or None
    return str(value)


_HOTEL_CITY_CODES = {
    "london": "LON",
    "new york": "NYC",
    "paris": "PAR",
    "tokyo": "TYO",
}

_IATA_CODES = {
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "goa": "GOI",
    "london": "LHR",
    "new york": "JFK",
    "paris": "CDG",
    "tokyo": "NRT",
    "dubai": "DXB",
    "singapore": "SIN",
}


def _resolve_iata(place: str) -> str:
    normalized = place.lower().strip()
    if normalized in _IATA_CODES:
        return _IATA_CODES[normalized]
    if len(place) == 3 and place.isalpha():
        return place.upper()
    return place.upper()[:3]


def _hotel_location_code(destination: str) -> str:
    normalized = destination.strip().lower()
    return _HOTEL_CITY_CODES.get(normalized, _resolve_iata(destination))


class LiteAPIProvider:
    name = "liteapi"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any], timeout: float = 20) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self._base_url}/{path.lstrip('/')}",
                headers={"X-API-Key": self._api_key, "Accept": "application/json"},
                json=payload,
                timeout=timeout,
            )
            if response.status_code == 204:
                return {"data": []}
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise LiteAPIError(f"LiteAPI returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LiteAPIError(f"LiteAPI request failed: {type(exc).__name__}") from exc

    def search_hotels(self, query: HotelSearchQuery) -> list[HotelOffer]:
        occupancies = [
            {
                "adults": query.adults_per_room,
                "children": query.children_ages if room == 0 else [],
            }
            for room in range(query.rooms)
        ]
        payload = self._post(
            "hotels/rates",
            {
                "iataCode": _hotel_location_code(query.destination),
                "checkin": query.checkin,
                "checkout": query.checkout,
                "currency": query.currency,
                "guestNationality": query.guest_nationality,
                "occupancies": occupancies,
                "refundableRatesOnly": query.refundable_only,
                "maxRatesPerHotel": 2,
                "includeHotelData": True,
                "limit": query.max_results,
                "timeout": 12,
            },
            timeout=15,
        )
        quoted_at = _utc_now()
        hotel_metadata = {
            str(hotel.get("id")): hotel for hotel in payload.get("hotels", []) if hotel.get("id")
        }
        offers: list[HotelOffer] = []
        for hotel in payload.get("data", []):
            hotel_id = str(hotel.get("hotelId") or "")
            metadata = hotel_metadata.get(hotel_id, {})
            for room in hotel.get("roomTypes", []):
                for rate in room.get("rates", []):
                    total = (
                        _money(room.get("offerRetailRate"), query.currency)
                        or _money(rate.get("retailRate"), query.currency)
                        or _money(rate.get("price"), query.currency)
                    )
                    if not total:
                        continue
                    cancellation = rate.get("cancellationPolicies")
                    refundable = rate.get("refundable")
                    if refundable is None and isinstance(cancellation, dict):
                        refundable = cancellation.get("refundable")
                    offers.append(
                        HotelOffer(
                            provider=self.name,
                            provider_ref={
                                "hotel_id": hotel_id,
                                "offer_id": str(room.get("offerId") or ""),
                                "rate_id": str(rate.get("rateId") or ""),
                            },
                            hotel_name=str(metadata.get("name") or hotel.get("name") or hotel_id),
                            search_destination=query.destination,
                            room_name=str(rate.get("name") or room.get("name") or "Room"),
                            board_name=rate.get("boardName"),
                            total=total,
                            refundable=refundable if isinstance(refundable, bool) else None,
                            cancellation_summary=_cancellation_summary(cancellation),
                            quoted_at=quoted_at,
                            address=metadata.get("address"),
                            rating=_number(metadata.get("rating")),
                        )
                    )
        offers.sort(key=lambda offer: offer.total.amount)
        return offers[: query.max_results]

    def search_flights(self, query: FlightSearchQuery) -> list[FlightOffer]:
        legs = [
            {
                "origin": _resolve_iata(query.origin),
                "destination": _resolve_iata(query.destination),
                "date": query.departure_date,
                "direction": "OUTBOUND",
            }
        ]
        if query.return_date:
            legs.append(
                {
                    "origin": _resolve_iata(query.destination),
                    "destination": _resolve_iata(query.origin),
                    "date": query.return_date,
                    "direction": "INBOUND",
                }
            )
        payload = self._post(
            "flights/rates",
            {
                "legs": legs,
                "adults": query.adults,
                "children": query.children,
                "infants": query.infants,
                "cabinClass": query.cabin_class.upper(),
                "currency": query.currency,
                "country": query.country,
            },
            timeout=45,
        )
        return self._flight_offers(payload, query.currency, query.max_results)

    def verify_flight(self, offer_id: str) -> FlightOffer:
        payload = self._post("flights/verify", {"offerId": offer_id}, timeout=30)
        offers = self._flight_offers(payload, "INR", 1, changes=payload.get("changes"))
        if not offers:
            raise LiteAPIError("LiteAPI flight offer is no longer available")
        return offers[0]

    def _flight_offers(
        self,
        payload: dict[str, Any],
        currency: str,
        max_results: int,
        changes: dict[str, Any] | None = None,
    ) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        raw_data = payload.get("data", [])
        batches = [raw_data] if isinstance(raw_data, dict) else raw_data
        for batch in batches:
            journeys = batch.get("journeys", []) if isinstance(batch, dict) else []
            if isinstance(batch, dict) and batch.get("journey"):
                journeys = [batch["journey"]]
                changes = batch.get("changes") or changes
            for journey in journeys:
                journey_offers = journey.get("offers") or [journey]
                for offer in journey_offers:
                    total = _money(offer.get("pricing") or journey.get("pricing"), currency)
                    if not total:
                        continue
                    segment_fares = offer.get("segmentFares") or journey.get("segmentFares") or []
                    seats = [
                        int(fare["seatsRemaining"])
                        for fare in segment_fares
                        if fare.get("seatsRemaining") is not None
                    ]
                    quoted_at = _parse_datetime(journey.get("timestamp")) or _utc_now()
                    offers.append(
                        FlightOffer(
                            provider=self.name,
                            provider_ref={
                                "offer_id": str(offer.get("offerId") or ""),
                                "journey_key": str(journey.get("journeyKey") or ""),
                            },
                            total=total,
                            segments=journey.get("segments") or [],
                            quoted_at=quoted_at,
                            expires_at=_parse_datetime(
                                offer.get("expiration") or journey.get("expiration")
                            ),
                            seats_remaining=min(seats) if seats else None,
                            baggage=offer.get("baggage"),
                            terms=offer.get("terms"),
                            changes=changes,
                        )
                    )
        offers.sort(key=lambda offer: offer.total.amount)
        return offers[:max_results]
