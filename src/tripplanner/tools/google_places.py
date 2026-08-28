"""Google Places API (New) v1 — restaurants, attractions, reviews, ratings.

Sign up free: https://console.cloud.google.com → enable "Places API (New)"
Free tier: $200/month credit (~10K text searches, ~17K place details calls).

Used to ground hotel/restaurant/attraction recommendations in real ratings &
review snippets instead of LLM guesses.
"""

from __future__ import annotations

import hashlib
import json

import httpx
from langchain_core.tools import tool

from tripplanner import http_client
from tripplanner.caching import get_cache
from tripplanner.config import get_settings
from tripplanner.places_budget import consume

_BASE = "https://places.googleapis.com/v1"
_SEARCH_CACHE = get_cache("google-places-search", default_ttl_seconds=604800, volatile=False)
_REVIEWS_CACHE = get_cache("google-places-reviews", default_ttl_seconds=604800, volatile=False)


def _cache_key(operation: str, payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{operation}:{hashlib.sha256(encoded).hexdigest()}"


def is_configured() -> bool:
    settings = get_settings()
    return settings.enable_google_places and bool(settings.google_places_api_key)


def _headers(field_mask: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_settings().google_places_api_key,
        "X-Goog-FieldMask": field_mask,
    }


def _format_place(p: dict) -> dict:
    """Extract the most useful fields from a Places API response."""
    location = p.get("location") or {}
    return {
        "name": p.get("displayName", {}).get("text", ""),
        "address": p.get("formattedAddress", ""),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "price_level": p.get("priceLevel"),  # PRICE_LEVEL_INEXPENSIVE..VERY_EXPENSIVE
        "types": p.get("types", [])[:3],
        "website": p.get("websiteUri", ""),
        "phone": p.get("internationalPhoneNumber", ""),
        "open_now": p.get("currentOpeningHours", {}).get("openNow"),
        "place_id": p.get("id", ""),
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "photo_refs": [
            photo.get("name") for photo in (p.get("photos") or []) if photo.get("name")
        ],
    }


def _remember_places(places: list[dict], city: str) -> None:
    from tripplanner.web.places_cache import remember_places

    remember_places(places, city)


def _format_reviews(reviews: list[dict], limit: int = 3) -> list[dict]:
    return [
        {
            "rating": r.get("rating"),
            "text": (r.get("text", {}).get("text", "") or "")[:300],
            "author": r.get("authorAttribution", {}).get("displayName", ""),
            "relative_time": r.get("relativePublishTimeDescription", ""),
        }
        for r in reviews[:limit]
    ]


@tool
def search_places_with_reviews(query: str, city: str = "", max_results: int = 5) -> str:
    """Search Google Places for hotels, attractions, restaurants etc. with real ratings.

    Returns top results with rating, review count, price level, and website.
    Use this BEFORE recommending any specific place to verify it exists and is good.

    Args:
        query: What to search, e.g. "kid-friendly resort in Goa", "best seafood near Calangute".
        city: Optional city/region to bias results.
        max_results: How many to return (1-10).
    """
    if not is_configured():
        return (
            "Google Places API disabled or not configured. "
            "Set ENABLE_GOOGLE_PLACES=1 and GOOGLE_PLACES_API_KEY in .env. "
            "Get a key at https://console.cloud.google.com (enable 'Places API (New)')."
        )

    full_query = f"{query} {city}".strip()
    cache_key = _cache_key(
        "search",
        {"query": " ".join(full_query.lower().split()), "max_results": max_results},
    )
    cached = _SEARCH_CACHE.get(cache_key)
    if isinstance(cached, str):
        _remember_places(json.loads(cached), city)
        return cached
    if not consume("text_search"):
        return "Google Places search budget reached for this planning turn. Reuse prior results."
    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.rating,"
        "places.userRatingCount,places.priceLevel,places.types,places.websiteUri,"
        "places.internationalPhoneNumber,places.currentOpeningHours.openNow,"
        "places.location,places.photos"
    )
    try:
        resp = http_client.post(
            f"{_BASE}/places:searchText",
            headers=_headers(field_mask),
            json={"textQuery": full_query, "pageSize": min(max(max_results, 1), 10)},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"Google Places search failed: {e}"

    places = [_format_place(p) for p in resp.json().get("places", [])]
    if not places:
        return f"No places found for '{full_query}'."
    _remember_places(places, city)
    result = json.dumps(places, indent=2)
    _SEARCH_CACHE.set(
        cache_key,
        result,
        ttl_seconds=get_settings().google_places_search_cache_ttl_sec,
    )
    return result


@tool
def get_place_reviews(place_id: str, max_reviews: int = 5) -> str:
    """Get detailed reviews for a specific place (use place_id from search_places_with_reviews).

    Returns rating breakdown plus the most helpful review snippets.
    """
    if not is_configured():
        return (
            "Google Places API disabled or not configured. "
            "Set ENABLE_GOOGLE_PLACES=1 and GOOGLE_PLACES_API_KEY in .env."
        )
    cache_key = _cache_key("reviews", {"place_id": place_id, "max_reviews": max_reviews})
    cached = _REVIEWS_CACHE.get(cache_key)
    if isinstance(cached, str):
        return cached
    if not consume("review_details"):
        return "Google Places review budget reached for this planning turn. Reuse prior ratings."

    field_mask = "id,displayName,rating,userRatingCount,reviews,editorialSummary"
    try:
        resp = http_client.get(
            f"{_BASE}/places/{place_id}",
            headers=_headers(field_mask),
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"Failed to fetch place details: {e}"

    p = resp.json()
    out = {
        "name": p.get("displayName", {}).get("text", ""),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "editorial_summary": p.get("editorialSummary", {}).get("text", ""),
        "reviews": _format_reviews(p.get("reviews", []), max_reviews),
    }
    result = json.dumps(out, indent=2)
    _REVIEWS_CACHE.set(
        cache_key,
        result,
        ttl_seconds=get_settings().google_places_reviews_cache_ttl_sec,
    )
    return result


@tool
def nearby_restaurants(
    city: str,
    cuisine: str = "",
    dietary: str = "",
    min_rating: float = 4.0,
    max_results: int = 8,
) -> str:
    """Find well-rated restaurants in a city, optionally filtered by cuisine & dietary needs.

    Args:
        city: e.g. "Goa", "Paris", "Mumbai".
        cuisine: e.g. "Italian", "seafood", "South Indian".
        dietary: e.g. "vegetarian", "vegan", "gluten-free", "halal".
        min_rating: Only return restaurants with rating >= this (default 4.0).
        max_results: How many to return.
    """
    if not is_configured():
        return (
            "Google Places API disabled or not configured. "
            "Set ENABLE_GOOGLE_PLACES=1 and GOOGLE_PLACES_API_KEY in .env."
        )

    parts = [p for p in [dietary, cuisine, "restaurants", "in", city] if p]
    cache_key = _cache_key(
        "restaurants",
        {
            "city": " ".join(city.lower().split()),
            "cuisine": " ".join(cuisine.lower().split()),
            "dietary": " ".join(dietary.lower().split()),
            "min_rating": min_rating,
            "max_results": max_results,
        },
    )
    cached = _SEARCH_CACHE.get(cache_key)
    if isinstance(cached, str):
        _remember_places(json.loads(cached), city)
        return cached
    if not consume("text_search"):
        return "Google Places search budget reached for this planning turn. Reuse prior results."
    query = " ".join(parts)
    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.rating,"
        "places.userRatingCount,places.priceLevel,places.types,places.websiteUri,"
        "places.location,places.photos"
    )
    try:
        resp = http_client.post(
            f"{_BASE}/places:searchText",
            headers=_headers(field_mask),
            json={"textQuery": query, "pageSize": min(max(max_results * 2, 1), 20)},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"Google Places search failed: {e}"

    results = [_format_place(p) for p in resp.json().get("places", [])]
    filtered = [r for r in results if (r.get("rating") or 0) >= min_rating]
    filtered.sort(key=lambda r: ((r.get("review_count") or 0), r.get("rating") or 0), reverse=True)
    top = filtered[:max_results]
    if not top:
        return f"No restaurants found in {city} matching the criteria (min rating {min_rating})."
    _remember_places(top, city)
    result = json.dumps(top, indent=2)
    _SEARCH_CACHE.set(
        cache_key,
        result,
        ttl_seconds=get_settings().google_places_search_cache_ttl_sec,
    )
    return result
