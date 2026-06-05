"""Local events / festivals / public-holiday lookup, backed by Tavily.

The trip agent calls this during STEP 4 to flag big events overlapping the
trip dates — a festival can double hotel prices, a parade can close streets,
and a public holiday can shut museums. Better the agent surfaces these than
the user finds out the hard way.
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from multiagent.tools.web_search import is_configured, search_raw


def _build_query(destination: str, start_date: str, end_date: str, kinds: str) -> str:
    return (
        f"{kinds} in {destination} between {start_date} and {end_date} — "
        "festivals, concerts, parades, exhibitions, public holidays, sporting events"
    )


@tool
def find_local_events(
    destination: str,
    start_date: str,
    end_date: str,
    kinds: str = "festivals and major events",
) -> str:
    """Find festivals / concerts / public holidays / parades during the trip dates.

    Use during itinerary planning to:
      - Catch holidays that close museums or shift restaurant hours
      - Surface festivals worth attending OR worth avoiding (price surges,
        crowds)
      - Warn about marathons / parades / strikes that may disrupt transit

    Args:
        destination: City or region, e.g. "Paris", "Goa", "Tokyo".
        start_date:  ISO date "YYYY-MM-DD".
        end_date:    ISO date "YYYY-MM-DD".
        kinds: Optional filter phrase. Default "festivals and major events".

    Returns JSON with a Tavily summary + top 5 source links. Treat as a
    starting point, not a complete event calendar — verify on official
    tourism / event sites before re-planning around an event.
    """
    if not is_configured():
        return (
            "Web search not configured — set TAVILY_API_KEY to enable event lookup. "
            "Until then, ask the user to check the destination's official "
            "tourism site for festivals during their dates."
        )

    if not destination.strip() or not start_date.strip() or not end_date.strip():
        return "destination, start_date and end_date are required."

    query = _build_query(destination.strip(), start_date.strip(), end_date.strip(), kinds.strip())

    try:
        raw = search_raw(query, max_results=8, search_depth="advanced", topic="news")
    except (RuntimeError, httpx.HTTPError) as e:
        return f"Event search failed: {e}"

    results = raw.get("results", [])[:5]
    out = {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "summary": raw.get("answer", ""),
        "results": results,
        "note": (
            "Sourced from web search. Confirm event dates and venues on the "
            "official organizer's site before re-planning around them."
        ),
    }
    return json.dumps(out, indent=2)
