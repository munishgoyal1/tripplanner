"""Sightseeing, tours, and attraction search via Amadeus Tours & Activities API."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from tripplanner.config import get_settings
from tripplanner.providers.cache import ProviderTTLCache
from tripplanner.providers.models import ActivitySearchQuery
from tripplanner.providers.registry import get_activity_providers
from tripplanner.providers.runtime import run_provider_chain
from tripplanner.tools import amadeus_client

_ACTIVITY_RESULT_CACHE: ProviderTTLCache[list] = ProviderTTLCache()

# Approximate coordinates for popular destinations
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "goa": (15.4909, 73.8278), "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090), "new delhi": (28.6139, 77.2090),
    "jaipur": (26.9124, 75.7873), "udaipur": (24.5854, 73.7125),
    "agra": (27.1767, 78.0081), "varanasi": (25.3176, 82.9739),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707), "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867), "kochi": (9.9312, 76.2673),
    "shimla": (31.1048, 77.1734), "manali": (32.2432, 77.1892),
    "darjeeling": (27.0410, 88.2663), "munnar": (10.0889, 77.0595),
    "rishikesh": (30.0869, 78.2676), "amritsar": (31.6340, 74.8723),
    "jodhpur": (26.2389, 73.0243), "pushkar": (26.4899, 74.5509),
    "hampi": (15.3350, 76.4600), "mysore": (12.2958, 76.6394),
    "pondicherry": (11.9416, 79.8083), "ooty": (11.4102, 76.6950),
    "alleppey": (9.4981, 76.3388), "leh": (34.1526, 77.5771),
    "srinagar": (34.0837, 74.7973), "andaman": (11.7401, 92.6586),
    # International
    "paris": (48.8566, 2.3522), "london": (51.5074, -0.1278),
    "dubai": (25.2048, 55.2708), "singapore": (1.3521, 103.8198),
    "bangkok": (13.7563, 100.5018), "bali": (-8.3405, 115.0920),
    "tokyo": (35.6762, 139.6503), "new york": (40.7128, -74.0060),
    "rome": (41.9028, 12.4964), "barcelona": (41.3874, 2.1686),
    "amsterdam": (52.3676, 4.9041), "istanbul": (41.0082, 28.9784),
    "phuket": (7.8804, 98.3923), "maldives": (3.2028, 73.2207),
    "sydney": (33.8688, 151.2093), "cape town": (-33.9249, 18.4241),
    "mauritius": (-20.3484, 57.5522), "zurich": (47.3769, 8.5417),
    "san francisco": (37.7749, -122.4194),
}


def _get_coords(city: str) -> tuple[float, float] | None:
    """Look up approximate coordinates for a city."""
    return _CITY_COORDS.get(city.lower().strip())


def _format_activities(data: dict) -> str:
    activities = data.get("data", [])
    if not activities:
        return "No activities/tours found for this location."

    lines: list[str] = []
    for i, act in enumerate(activities, 1):
        name = act.get("name", "Unknown")
        desc = act.get("shortDescription", act.get("description", ""))
        if len(desc) > 200:
            desc = desc[:197] + "..."
        price = act.get("price", {})
        currency = price.get("currencyCode", "INR")
        amount = price.get("amount", "?")
        rating = act.get("rating", "?")
        booking_link = act.get("bookingLink", "")
        duration = act.get("duration", "")
        pictures = act.get("pictures", [])
        picture_url = pictures[0] if pictures else ""

        lines.append(
            f"\n--- Activity {i}: {name} ---\n"
            f"  {desc}\n"
            f"  Price: {currency} {amount} | Rating: {rating}/5"
        )
        if duration:
            lines.append(f"  Duration: {duration}")
        if booking_link:
            lines.append(f"  Book: {booking_link}")
        if picture_url:
            lines.append(f"  Photo: {picture_url}")

    lines.append(f"\n{len(activities)} activity/tour(s) found.")
    return "\n".join(lines)


@tool
def search_activities(
    city: str,
    max_results: int = 10,
    latitude: float = 0,
    longitude: float = 0,
    radius: int = 20,
    start_date: str = "",
    end_date: str = "",
    adults: int = 1,
    children: int = 0,
    currency: str = "INR",
    refresh: bool = False,
) -> str:
    """Search for sightseeing tours, attraction tickets, and local experiences.

    Args:
        city: City name (e.g. 'Goa', 'Paris', 'Jaipur').
        max_results: Maximum number of activities to return.
        latitude: Override latitude (0 = auto-detect from city name).
        longitude: Override longitude (0 = auto-detect from city name).
        radius: Search radius in km from the city center.
        start_date: Optional activity window start date, YYYY-MM-DD.
        end_date: Optional activity window end date, YYYY-MM-DD.
        adults: Number of adults for future exact-party pricing compatibility.
        children: Number of children for future exact-party pricing compatibility.
        currency: ISO currency code for provider from-prices.
        refresh: Bypass the short-lived shared result cache.
    """
    providers = get_activity_providers()
    if providers:
        query = ActivitySearchQuery(
            destination=city,
            start_date=start_date,
            end_date=end_date,
            adults=adults,
            children=children,
            currency=currency.upper(),
            max_results=max_results,
        )
        result = run_provider_chain(
            providers=providers,
            cache=_ACTIVITY_RESULT_CACHE,
            cache_key=query.model_dump_json(),
            ttl_seconds=get_settings().activity_search_cache_ttl_sec,
            refresh=refresh,
            empty_value=[],
            call=lambda provider: provider.search_activities(query),
        )
        offers = result.value
        if offers:
            return json.dumps(
                {
                    "quote_status": result.quote_status,
                    "provider": result.provider,
                    "cache_hit": result.cache_hit,
                    "checked_at": result.checked_at,
                    "expires_at": result.expires_at,
                    "pricing_scope": "from_price; not an exact party total or held quote",
                    "booking_supported": False,
                    "offers": [offer.model_dump(mode="json") for offer in offers],
                },
                ensure_ascii=False,
                default=str,
            )
        if result.errors:
            return json.dumps(
                {
                    "quote_status": result.quote_status,
                    "provider": result.provider,
                    "booking_supported": False,
                    "errors": result.errors,
                },
                ensure_ascii=False,
                default=str,
            )

    if not amadeus_client.is_configured():
        return (
            "Viator and Amadeus APIs not configured. Set VIATOR_API_KEY for read-only "
            "activity prices and schedules.\n"
            "Sign up free at https://developers.amadeus.com\n"
            "Falling back to general knowledge for activity suggestions."
        )

    lat, lon = latitude, longitude
    if lat == 0 and lon == 0:
        coords = _get_coords(city)
        if not coords:
            return (
                f"Could not find coordinates for '{city}'. "
                "Please provide latitude and longitude, or use a well-known city name."
            )
        lat, lon = coords

    try:
        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "radius": radius,
        }
        data = amadeus_client.get("/v1/shopping/activities", params)
        activities = data.get("data", [])
        if len(activities) > max_results:
            data["data"] = activities[:max_results]
        return _format_activities(data)
    except Exception as e:
        return f"Activity search error: {e}"


@tool
def search_points_of_interest(city: str, categories: str = "", max_results: int = 10) -> str:
    """Search for points of interest (landmarks, attractions, restaurants) in a city.

    Args:
        city: City name.
        categories: Comma-separated: SIGHTS, NIGHTLIFE, RESTAURANT, SHOPPING (omit for all).
        max_results: Maximum results.
    """
    if not amadeus_client.is_configured():
        return (
            "Amadeus API not configured. Falling back to general knowledge.\n"
            "Set AMADEUS_API_KEY and AMADEUS_API_SECRET in .env."
        )

    coords = _get_coords(city)
    if not coords:
        return f"Could not find coordinates for '{city}'."

    lat, lon = coords
    try:
        params: dict = {
            "latitude": lat,
            "longitude": lon,
            "radius": 20,
            "page[limit]": max_results,
        }
        if categories:
            params["categories"] = categories
        data = amadeus_client.get("/v1/reference-data/locations/pois", params)
        pois = data.get("data", [])
        if not pois:
            return f"No points of interest found near {city}."

        lines = [f"\nPoints of Interest near {city}:"]
        for i, poi in enumerate(pois, 1):
            name = poi.get("name", "Unknown")
            cat = poi.get("category", "")
            tags = ", ".join(poi.get("tags", [])[:5])
            lines.append(f"  {i}. {name} [{cat}] — {tags}")
        return "\n".join(lines)
    except Exception as e:
        return f"POI search error: {e}"

