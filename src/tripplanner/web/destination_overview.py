"""Destination-level overview: photos, attractions, reviews, and news."""

from __future__ import annotations

from typing import Any

from tripplanner.concurrency import run_parallel
from tripplanner.config import get_settings
from tripplanner.web import places_cache
from tripplanner.web.gallery import _MAX_GALLERY_ITEMS
from tripplanner.web.map_pins import _MAX_OVERVIEW_ATTRACTIONS, build_map_url
from tripplanner.web.place_guide import _MAX_REVIEWS_PER_ITEM

_MAX_NEWS_ITEMS = 4


def build_destination_overview(
    destination: str,
    *,
    include_news: bool = True,
    places_loader: Any | None = None,
) -> dict[str, Any]:
    """Build a destination-level overview shown before any trip exists.

    Combines Google Places (photos, key attractions, reviews) with fresh
    Tavily news. Frontend-agnostic — consumed by ``GET /destination/overview``
    and rendered by the SPA. Network calls degrade gracefully: a missing API
    key just yields an empty section rather than an error.
    """
    destination = (destination or "").strip()
    if not destination:
        return {
            "destination": "",
            "summary": "",
            "rating": None,
            "review_count": 0,
            "photos": [],
            "key_attractions": [],
            "reviews": [],
            "news": [],
            "map_url": "",
        }

    # Places and news share nothing, so the overview costs the slower of the two
    # rather than their sum.
    branches = run_parallel(
        {
            "places": lambda: (places_loader or _overview_places)(destination),
            "news": (lambda: _fetch_destination_news(destination)) if include_news else list,
        }
    )
    photos, key_attractions, reviews, summary = branches["places"] or ([], [], [], "")
    news: list[dict[str, str]] = branches["news"] or []

    rated = [a["rating"] for a in key_attractions if a.get("rating")]
    agg_rating = round(sum(rated) / len(rated), 1) if rated else None
    agg_reviews = sum(
        int(a["review_count"]) for a in key_attractions if a.get("review_count")
    )

    return {
        "destination": destination,
        "summary": summary,
        "rating": agg_rating,
        "review_count": agg_reviews,
        "photos": photos[:_MAX_GALLERY_ITEMS],
        "key_attractions": key_attractions,
        "reviews": reviews[:_MAX_REVIEWS_PER_ITEM * 3],
        "news": news,
        "map_url": build_map_url(destination, [a["name"] for a in key_attractions[:5]]),
    }


def _overview_places(
    destination: str,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], str]:
    """Photos, key attractions, sample reviews, and a summary for ``destination``."""
    attraction_names = places_cache.top_places(
        destination, "attraction", n=_MAX_OVERVIEW_ATTRACTIONS
    )
    photo_limit = get_settings().google_places_max_photos_per_request
    places_cache.prefetch(
        attraction_names[:photo_limit], destination, max_photos=1, with_reviews=False
    )

    photos: list[str] = []
    key_attractions: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    summary = ""
    for name in attraction_names:
        info = places_cache.get_details(name, destination) or {}
        pics = (
            places_cache.get_photos(name, destination, max_photos=1)
            if name in attraction_names[:photo_limit]
            else []
        )
        photos.extend(pics)
        if not summary and info.get("editorial_summary"):
            summary = info["editorial_summary"]
        key_attractions.append(
            {
                "name": info.get("name") or name,
                "rating": info.get("rating"),
                "review_count": info.get("review_count"),
                "summary": info.get("editorial_summary") or "",
                "photo": pics[0] if pics else None,
            }
        )
    return photos, key_attractions, reviews, summary


def _fetch_destination_news(destination: str) -> list[dict[str, str]]:
    """Fetch fresh travel news for ``destination`` via Tavily; never raises."""
    try:
        from tripplanner.tools import web_search

        data = web_search.search_raw(
            f"latest positive travel news, new openings and good updates for {destination}",
            max_results=_MAX_NEWS_ITEMS,
            topic="news",
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for r in data.get("results", [])[:_MAX_NEWS_ITEMS]:
        if r.get("title"):
            out.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
            )
    return out

