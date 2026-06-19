"""Flight search via Duffel API (v2).

Duffel is a modern flight search & booking API used as the primary flight
provider while Amadeus Self-Service is being decommissioned (July 17, 2026).

Sign up free for a test-mode token (no credit card required):
  https://app.duffel.com/sign-up

Test-mode tokens look like ``duffel_test_xxx`` and return synthetic offers from
Duffel Airways — perfect for development without billing risk.

Docs: https://duffel.com/docs/api/offer-requests/create-offer-request
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from tripplanner.config import get_settings
from tripplanner.tools.flight_search import resolve_iata

_BASE_URL = "https://api.duffel.com"
_DUFFEL_VERSION = "v2"


def is_configured() -> bool:
    """Return True if a Duffel API key is set."""
    return bool(get_settings().duffel_api_key)


def _headers() -> dict[str, str]:
    token = get_settings().duffel_api_key
    return {
        "Authorization": f"Bearer {token}",
        "Duffel-Version": _DUFFEL_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }


def _format_duration(iso: str) -> str:
    """Convert ISO 8601 duration like 'PT5H30M' to '5h 30m'."""
    if not iso or not iso.startswith("PT"):
        return iso or ""
    body = iso[2:]
    out = ""
    num = ""
    for ch in body:
        if ch.isdigit():
            num += ch
        elif ch == "H" and num:
            out += f"{num}h "
            num = ""
        elif ch == "M" and num:
            out += f"{num}m "
            num = ""
    return out.strip()


def _format_segment(seg: dict) -> str:
    carrier = seg.get("marketing_carrier", {})
    code = carrier.get("iata_code", "??")
    flight_no = seg.get("marketing_carrier_flight_number") or seg.get("flight_number", "")
    origin = seg.get("origin", {}).get("iata_code", "?")
    dest = seg.get("destination", {}).get("iata_code", "?")
    dep = (seg.get("departing_at") or "")[11:16]
    arr = (seg.get("arriving_at") or "")[11:16]
    duration = _format_duration(seg.get("duration", ""))
    aircraft = (seg.get("aircraft") or {}).get("name") or ""
    line = f"  {code}{flight_no} | {origin} {dep} → {dest} {arr} | {duration}"
    if aircraft:
        line += f" | {aircraft}"
    return line


def _format_offers(offers: list[dict], max_results: int) -> str:
    if not offers:
        return "No Duffel offers found for the given criteria."

    # Sort by price ascending
    try:
        offers = sorted(offers, key=lambda o: float(o.get("total_amount", "999999")))
    except (TypeError, ValueError):
        pass

    lines: list[str] = []
    for i, offer in enumerate(offers[:max_results], 1):
        currency = offer.get("total_currency", "?")
        amount = offer.get("total_amount", "?")
        owner = (offer.get("owner") or {}).get("name", "")
        lines.append(f"\n--- Option {i} — {currency} {amount} ({owner}) ---")

        for j, sl in enumerate(offer.get("slices", [])):
            direction = "Outbound" if j == 0 else "Return"
            duration = _format_duration(sl.get("duration", ""))
            segments = sl.get("segments", [])
            stops = len(segments) - 1
            stop_str = "Direct" if stops == 0 else f"{stops} stop(s)"
            lines.append(f"  [{direction}] {stop_str} — total {duration}")
            for seg in segments:
                lines.append(_format_segment(seg))

    lines.append(f"\n{len(offers)} Duffel offer(s) found (showing top {min(max_results, len(offers))}).")
    return "\n".join(lines)


@tool
def search_flights_duffel(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    cabin_class: str = "economy",
    max_connections: int = 1,
    max_results: int = 5,
) -> str:
    """Search real flights via Duffel — airlines, times, stops, and prices.

    Preferred flight provider (Amadeus self-service is being deprecated July 17, 2026).

    Args:
        origin: Origin city name or IATA code (e.g. 'Delhi' or 'DEL').
        destination: Destination city name or IATA code.
        departure_date: Departure date YYYY-MM-DD.
        return_date: Return date YYYY-MM-DD (omit for one-way).
        adults: Number of adult passengers.
        children: Number of child passengers (2-11 years).
        infants: Number of infant passengers (under 2, on adult's lap).
        cabin_class: one of 'economy', 'premium_economy', 'business', 'first'.
        max_connections: Max connections per slice (0 = direct only).
        max_results: How many cheapest offers to return (1-10).
    """
    if not is_configured():
        return (
            "Duffel API not configured. Set DUFFEL_API_KEY in .env.\n"
            "Sign up free for a test token at https://app.duffel.com/sign-up "
            "(no credit card required, returns synthetic offers from Duffel Airways)."
        )

    origin_code = resolve_iata(origin)
    dest_code = resolve_iata(destination)

    slices: list[dict] = [
        {
            "origin": origin_code,
            "destination": dest_code,
            "departure_date": departure_date,
        }
    ]
    if return_date:
        slices.append(
            {
                "origin": dest_code,
                "destination": origin_code,
                "departure_date": return_date,
            }
        )

    passengers: list[dict] = []
    passengers.extend({"type": "adult"} for _ in range(max(1, adults)))
    passengers.extend({"type": "child"} for _ in range(max(0, children)))
    passengers.extend({"type": "infant_without_seat"} for _ in range(max(0, infants)))

    body = {
        "data": {
            "slices": slices,
            "passengers": passengers,
            "cabin_class": cabin_class,
            "max_connections": max_connections,
        }
    }

    try:
        resp = httpx.post(
            f"{_BASE_URL}/air/offer_requests",
            params={"return_offers": "true"},
            headers=_headers(),
            json=body,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        offers = data.get("offers", [])
        return _format_offers(offers, max_results)
    except httpx.HTTPStatusError as e:
        body_text = ""
        try:
            errs = e.response.json().get("errors", [])
            if errs:
                body_text = "; ".join(
                    f"{er.get('title','')}: {er.get('message','')}" for er in errs
                )
        except Exception:
            body_text = e.response.text[:300]
        return f"Duffel API error {e.response.status_code}: {body_text}"
    except Exception as e:
        return f"Duffel search error: {e}"

