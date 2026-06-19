"""Visa & entry-requirement check, backed by Tavily web search.

There is no great free structured visa API. Instead we run a narrow Tavily
search biased toward official sources (gov / embassy / IATA TravelCentre)
and hand the agent a small JSON envelope: top results + a disclaimer that
the user MUST verify on the official site before booking.

The trip agent should call this once per international trip during STEP 4 so
the itinerary doesn't quietly assume the user has a visa they need to apply
for weeks in advance.
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from tripplanner.tools.web_search import is_configured, search_raw

_PREFERRED_DOMAINS = [
    "iatatravelcentre.com",
    "travel.state.gov",
    "gov.uk",
    "canada.ca",
    "smartraveller.gov.au",
    "mea.gov.in",
    "schengenvisainfo.com",
]


def _build_query(passport_country: str, destination_country: str, purpose: str, days: int | None) -> str:
    parts = [
        f"visa requirements for {passport_country} passport holders",
        f"travelling to {destination_country}",
        f"purpose: {purpose}",
    ]
    if days:
        parts.append(f"stay {days} days")
    parts.append("official source government embassy")
    return " — ".join(parts)


@tool
def check_visa_requirements(
    passport_country: str,
    destination_country: str,
    purpose: str = "tourism",
    length_of_stay_days: int = 0,
) -> str:
    """Check visa / entry rules for the user's passport into a destination.

    Returns a JSON envelope with the top search hits (preferring .gov and IATA
    sources) plus a Tavily-generated summary. ALWAYS link the user to the
    official source — this is NOT legal advice. Call once per international
    trip during planning; skip for domestic trips.

    Args:
        passport_country: e.g. "Indian", "US", "British".
        destination_country: e.g. "France", "United Arab Emirates", "Japan".
        purpose: "tourism" | "business" | "transit" | "study" | other. Default tourism.
        length_of_stay_days: Length of intended stay; 0 means "ignore length".
    """
    if not is_configured():
        return (
            "Web search not configured — set TAVILY_API_KEY to enable visa checks. "
            "Until then: ask the user to verify visa rules on the destination's "
            "official immigration site or IATA TravelCentre."
        )

    if not passport_country.strip() or not destination_country.strip():
        return "passport_country and destination_country are required."

    query = _build_query(
        passport_country.strip(),
        destination_country.strip(),
        purpose.strip() or "tourism",
        length_of_stay_days if length_of_stay_days > 0 else None,
    )

    try:
        raw = search_raw(query, max_results=8, search_depth="advanced")
    except (RuntimeError, httpx.HTTPError) as e:
        return f"Visa search failed: {e}"

    results = raw.get("results", [])
    preferred, other = [], []
    for r in results:
        url = (r.get("url") or "").lower()
        if any(dom in url for dom in _PREFERRED_DOMAINS):
            preferred.append(r)
        else:
            other.append(r)

    top = (preferred + other)[:5]

    out = {
        "passport_country": passport_country,
        "destination_country": destination_country,
        "purpose": purpose,
        "length_of_stay_days": length_of_stay_days or None,
        "summary": raw.get("answer", ""),
        "results": top,
        "disclaimer": (
            "Information is sourced from public web search and may be outdated "
            "or incomplete. Always verify on the destination country's official "
            "immigration site or via IATA TravelCentre before booking."
        ),
    }
    return json.dumps(out, indent=2)
