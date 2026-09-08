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


def _known_passport_country() -> tuple[str, str, list[str]]:
    """The user's passport country from what they have already given us.

    Returns ``(country, source, candidates)``. An empty country means we must
    ask; ``candidates`` then lists the passports we found, so the question can
    name them. Residence is never used: living in India does not make someone
    an Indian passport holder, and guessing that wrong is worse than asking.
    """
    try:
        from tripplanner.web.travel_documents import list_documents

        records = [
            record
            for record in list_documents("traveler")
            if record.get("type") == "passport"
            and str(record.get("traveller_key") or "self") == "self"
        ]
    except Exception:
        records = []

    candidates: list[str] = []
    seen: set[str] = set()
    for record in records:
        fields = record.get("fields") or {}
        value = str(fields.get("issuing_country") or fields.get("nationality") or "").strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            candidates.append(value)
    if len(candidates) == 1:
        return candidates[0], "saved passport", candidates
    if len(candidates) > 1:
        return "", "multiple saved passports", candidates

    try:
        from tripplanner.tools.user_preferences import load_preferences

        profile = load_preferences().get("profile") or {}
        stated = str(profile.get("passport_country") or "").strip()
    except Exception:
        stated = ""
    if stated:
        return stated, "stated profile", [stated]
    return "", "unknown", []


def _ask_for_passport_country(candidates: list[str]) -> str:
    if candidates:
        listed = " or ".join(candidates)
        question = f"which passport they will travel on for this trip — {listed}"
    else:
        question = 'which passport they will travel on (for example "Indian", "US", "British")'
    return (
        "Passport country unknown, so no visa check can be run yet. Ask the user exactly one "
        f"question: {question}. Then call update_user_profile(passport_country=...) so it is "
        "never asked again, and call this tool again with the answer. Do NOT guess it from "
        "their home city, residence, or destination."
    )


@tool
def check_visa_requirements(
    passport_country: str = "",
    destination_country: str = "",
    purpose: str = "tourism",
    length_of_stay_days: int = 0,
) -> str:
    """Check visa / entry rules for the user's passport into a destination.

    Returns a JSON envelope with the top search hits (preferring .gov and IATA
    sources) plus a Tavily-generated summary. ALWAYS link the user to the
    official source — this is NOT legal advice. Call once per international
    trip during planning; skip for domestic trips.

    Leave passport_country empty unless the user just named it in this turn:
    the tool resolves it from their saved passport or stated profile, and tells
    you what to ask when it cannot. Never guess it from where they live.

    Args:
        passport_country: e.g. "Indian", "US", "British". Optional — resolved
            from the user's own records when omitted.
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

    if not destination_country.strip():
        return "destination_country is required."

    source = "provided"
    if not passport_country.strip():
        passport_country, source, candidates = _known_passport_country()
        if not passport_country:
            return _ask_for_passport_country(candidates)

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
        "passport_country_source": source,
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
