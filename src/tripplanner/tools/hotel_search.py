"""Hotel search via Amadeus Hotel Search API."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from langchain_core.tools import tool

from tripplanner.hotel_research import normalize_hotel_locality

from tripplanner.config import get_settings
from tripplanner.decisions.lodging import build_lodging_decision
from tripplanner.decisions.provenance import note_price_check
from tripplanner.providers.cache import ProviderTTLCache
from tripplanner.providers.models import HotelSearchQuery
from tripplanner.providers.registry import get_hotel_providers
from tripplanner.providers.runtime import run_provider_chain
from tripplanner.tools import amadeus_client
from tripplanner.tools.flight_search import _IATA_CODES, resolve_iata
from tripplanner.tools.google_places import search_places_with_reviews

_HOTEL_RESULT_CACHE: ProviderTTLCache[list] = ProviderTTLCache("hotel-search")


def _city_in_address(city, address):
    locality = normalize_hotel_locality(city)
    return bool(locality and re.search(rf"\b{re.escape(locality)}\b",
                                      normalize_hotel_locality(address)))


def _format_hotels(data: dict) -> str:
    offers = data.get("data", [])
    if not offers:
        return "No hotels found for the given criteria."

    lines: list[str] = []
    for i, hotel in enumerate(offers, 1):
        h = hotel.get("hotel", {})
        name = h.get("name", "Unknown")
        rating = h.get("rating", "?")
        city_code = h.get("cityCode", "")

        best_offer = None
        for o in hotel.get("offers", []):
            if best_offer is None:
                best_offer = o
                continue
            if float(o["price"]["total"]) < float(best_offer["price"]["total"]):
                best_offer = o

        if best_offer:
            price = best_offer["price"]
            currency = price.get("currency", "INR")
            total = price.get("total", "?")
            room = best_offer.get("room", {})
            room_type = room.get("typeEstimated", {})
            room_desc = room_type.get("category", "Standard")
            beds = room_type.get("beds", "?")
            bed_type = room_type.get("bedType", "")
            checkin = best_offer.get("checkInDate", "")
            checkout = best_offer.get("checkOutDate", "")
            cancellation = best_offer.get("policies", {}).get(
                "cancellations", [{}]
            )
            cancel_info = ""
            if cancellation:
                c = cancellation[0] if isinstance(cancellation, list) else cancellation
                cancel_info = f" | Cancel by: {c.get('deadline', 'N/A')}"

            lines.append(
                f"\n--- Option {i}: {name} ---\n"
                f"  Rating: {rating}★ | City: {city_code}\n"
                f"  Room: {room_desc} ({beds} {bed_type})\n"
                f"  Price: {currency} {total} ({checkin} to {checkout})\n"
                f"  {cancel_info}"
            )
        else:
            lines.append(f"\n--- Option {i}: {name} ({rating}★) — no offers available ---")

    lines.append(f"\n{len(offers)} hotel(s) found.")
    return "\n".join(lines)


def _places_fallback(city, checkin, checkout, max_results, reason):
    if city.strip().casefold() not in _IATA_CODES:
        city = next((name.title() for name, code in _IATA_CODES.items()
                     if code == city.strip().upper()), city)
    try:
        raw = search_places_with_reviews.invoke(
            {"query": "well-rated hotel", "city": city, "max_results": max_results}
        )
        try:
            places = json.loads(raw)
        except (ValueError, TypeError):
            places = []
        if not isinstance(places, list):
            places = []
        candidates = [place for place in places if isinstance(place, dict)
                      and place.get("name") and place.get("place_id")
                      and place.get("address")
                      and any(kind in {"lodging", "hotel", "resort_hotel"}
                              for kind in place.get("types", []))
                      and _city_in_address(city, place["address"])]
        fallback_reason = ("no_suitable_property" if places else
                           "no_results" if (str(raw).startswith("No places found")
                                            or raw.strip() == "[]") else
                           "provider_unavailable")
    except Exception:
        candidates = []
        fallback_reason = "provider_unavailable"
    research = {
        "city": city, "checkin": checkin, "checkout": checkout,
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "candidates_available" if candidates else "unresolved",
        "reason": "rate_and_availability_unverified" if candidates else fallback_reason,
        "inventory_reason": reason, "fallback_attempted": True,
        "candidate_count": len(candidates),
    }
    return json.dumps({
        "quote_status": "unverified", "provider": "google_places",
        "hotel_research": research, "candidates": candidates,
        "guidance": (
            "Choose one suitable property using location and traveler preferences; one is enough. "
            "Save its real name, place_id, address and city, with availability_status=unverified. "
            "Property metadata does not verify price, room occupancy, refundability or dates. "
            "Keep those facts unresolved; do not replace a suitable named recommendation with TBD "
            "only because live room offers are unavailable. If hard constraints cannot be met, "
            "explain them in the hotel stop concern."
            if candidates else
            "Hotel and Places research is complete for this city. Keep a city-specific Hotel TBD "
            "anchor and explain the reason; do not repeat the same fallback or invent a hotel."
        ),
    }, ensure_ascii=False)


@tool
def search_hotels(
    city: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
    ratings: str = "3,4,5",
    price_max: int = 0,
    max_results: int = 5,
    currency: str = "INR",
    guest_nationality: str = "IN",
    children_ages: list[int] | None = None,
    refundable_only: bool = False,
    refresh: bool = False,
) -> str:
    """Search for real hotels with names, ratings, room types, and prices.

    Args:
        city: City name or IATA code (e.g. 'Goa' or 'GOI').
        checkin: Check-in date YYYY-MM-DD.
        checkout: Check-out date YYYY-MM-DD.
        adults: Number of adults per room.
        rooms: Number of rooms needed.
        ratings: Comma-separated star ratings to include (e.g. '4,5').
        price_max: Maximum price per night (0 = no limit).
        max_results: Maximum hotel options to return.
        currency: ISO currency code for live rates.
        guest_nationality: ISO country code; required for accurate taxes and rates.
        children_ages: Ages of children sharing the first room.
        refundable_only: Return only refundable live rates when supported.
        refresh: Bypass the short-lived shared result cache.
    """
    providers = get_hotel_providers()
    if providers:
        query = HotelSearchQuery(
            destination=city,
            checkin=checkin,
            checkout=checkout,
            adults_per_room=adults,
            rooms=rooms,
            children_ages=children_ages or [],
            currency=currency.upper(),
            guest_nationality=guest_nationality.upper(),
            refundable_only=refundable_only,
            max_results=max_results,
        )
        result = run_provider_chain(
            providers=providers,
            cache=_HOTEL_RESULT_CACHE,
            cache_key=query.model_dump_json(),
            ttl_seconds=get_settings().hotel_search_cache_ttl_sec,
            refresh=refresh,
            empty_value=[],
            call=lambda provider: provider.search_hotels(query),
        )
        offers = result.value
        if offers:
            note_price_check("lodging", result.provider)
            search_context = {
                "destination": query.destination,
                "adults_per_room": query.adults_per_room,
                "rooms": query.rooms,
                "children_ages": list(query.children_ages),
                "guest_nationality": query.guest_nationality,
                "refundable_only": query.refundable_only,
            }
            decision = build_lodging_decision(
                offers,
                destination=city,
                checkin=checkin,
                checkout=checkout,
                cached=result.cache_hit,
                search_context=search_context,
            )
            if decision is not None:
                from tripplanner.tools import trip_planner

                trip_planner.record_trip_decision(decision)
            return json.dumps(
                {
                    "quote_status": result.quote_status,
                    "provider": result.provider,
                    "cache_hit": result.cache_hit,
                    "checked_at": result.checked_at,
                    "expires_at": result.expires_at,
                    "decision_id": decision.id if decision else None,
                    "recommended_option_id": decision.chosen_option_id if decision else None,
                    "hotel_research": {
                        "city": city, "checkin": checkin, "checkout": checkout,
                        "checked_at": result.checked_at, "status": "candidates_available",
                        "reason": "offers_returned", "candidate_count": len(offers),
                        "fallback_attempted": False,
                    },
                    "offers": [
                        {**offer.model_dump(mode="json"), "search_context": search_context}
                        for offer in offers
                    ],
                },
                ensure_ascii=False,
                default=str,
            )
        reason = ("no_availability" if result.errors and all(
            error.endswith(": no availability") for error in result.errors
        ) else "provider_unavailable" if result.errors else "no_availability")
        return _places_fallback(city, checkin, checkout, max_results, reason)

    if not amadeus_client.is_configured():
        return _places_fallback(city, checkin, checkout, max_results, "not_configured")

    city_code = resolve_iata(city)

    # Step 1: Get hotel IDs in the city
    try:
        list_params: dict = {
            "cityCode": city_code,
            "ratings": ratings,
        }
        hotel_list = amadeus_client.get(
            "/v1/reference-data/locations/hotels/by-city", list_params
        )
        hotel_ids = [
            h["hotelId"] for h in hotel_list.get("data", [])[:20]
        ]
        if not hotel_ids:
            return _places_fallback(city, checkin, checkout, max_results, "no_availability")
    except Exception:
        return _places_fallback(city, checkin, checkout, max_results, "provider_unavailable")

    # Step 2: Get offers for those hotels
    try:
        offer_params: dict = {
            "hotelIds": ",".join(hotel_ids[:max_results * 2]),
            "checkInDate": checkin,
            "checkOutDate": checkout,
            "adults": adults,
            "roomQuantity": rooms,
            "currency": currency.upper(),
        }
        if price_max:
            offer_params["priceRange"] = f"0-{price_max}"

        data = amadeus_client.get("/v3/shopping/hotel-offers", offer_params)
        result = _format_hotels(data)
        if len(data.get("data", [])) > max_results:
            # Trim to requested count
            data["data"] = data["data"][:max_results]
            result = _format_hotels(data)
        if not data.get("data") or not any(hotel.get("offers") for hotel in data["data"]):
            return _places_fallback(city, checkin, checkout, max_results, "no_availability")
        return result
    except Exception:
        return _places_fallback(city, checkin, checkout, max_results, "provider_unavailable")
