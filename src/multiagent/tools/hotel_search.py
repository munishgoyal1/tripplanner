"""Hotel search via Amadeus Hotel Search API."""

from __future__ import annotations

from langchain_core.tools import tool

from multiagent.tools import amadeus_client
from multiagent.tools.flight_search import resolve_iata


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
    """
    if not amadeus_client.is_configured():
        return (
            "Amadeus API not configured. Set AMADEUS_API_KEY and AMADEUS_API_SECRET in .env.\n"
            "Sign up free at https://developers.amadeus.com\n"
            "Falling back to general knowledge for hotel suggestions."
        )

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
            return f"No hotels found in {city} ({city_code})."
    except Exception as e:
        return f"Hotel list error: {e}"

    # Step 2: Get offers for those hotels
    try:
        offer_params: dict = {
            "hotelIds": ",".join(hotel_ids[:max_results * 2]),
            "checkInDate": checkin,
            "checkOutDate": checkout,
            "adults": adults,
            "roomQuantity": rooms,
            "currency": "INR",
        }
        if price_max:
            offer_params["priceRange"] = f"0-{price_max}"

        data = amadeus_client.get("/v3/shopping/hotel-offers", offer_params)
        result = _format_hotels(data)
        if len(data.get("data", [])) > max_results:
            # Trim to requested count
            data["data"] = data["data"][:max_results]
            result = _format_hotels(data)
        return result
    except Exception as e:
        return f"Hotel search error: {e}"
