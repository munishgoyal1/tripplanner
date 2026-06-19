"""Flight search via Amadeus Flight Offers Search API."""

from __future__ import annotations

from langchain_core.tools import tool

from tripplanner.tools import amadeus_client

# Common city → IATA code mapping (India-focused + major international)
_IATA_CODES: dict[str, str] = {
    "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR", "chennai": "MAA", "madras": "MAA",
    "kolkata": "CCU", "calcutta": "CCU", "hyderabad": "HYD",
    "ahmedabad": "AMD", "pune": "PNQ", "jaipur": "JAI", "lucknow": "LKO",
    "goa": "GOI", "kochi": "COK", "cochin": "COK", "thiruvananthapuram": "TRV",
    "trivandrum": "TRV", "guwahati": "GAU", "chandigarh": "IXC",
    "amritsar": "ATQ", "varanasi": "VNS", "indore": "IDR", "bhopal": "BHO",
    "nagpur": "NAG", "patna": "PAT", "ranchi": "IXR", "srinagar": "SXR",
    "leh": "IXL", "udaipur": "UDR", "jodhpur": "JDH", "bagdogra": "IXB",
    "port blair": "IXZ", "andaman": "IXZ", "coimbatore": "CJB",
    "visakhapatnam": "VTZ", "vizag": "VTZ", "mangalore": "IXE",
    "dehradun": "DED", "shimla": "SLV", "dharamshala": "DHM",
    # International
    "london": "LHR", "new york": "JFK", "dubai": "DXB", "singapore": "SIN",
    "bangkok": "BKK", "tokyo": "NRT", "paris": "CDG", "hong kong": "HKG",
    "kuala lumpur": "KUL", "sydney": "SYD", "san francisco": "SFO",
    "los angeles": "LAX", "toronto": "YYZ", "amsterdam": "AMS",
    "frankfurt": "FRA", "zurich": "ZRH", "rome": "FCO", "barcelona": "BCN",
    "istanbul": "IST", "cairo": "CAI", "nairobi": "NBO", "cape town": "CPT",
    "colombo": "CMB", "kathmandu": "KTM", "dhaka": "DAC", "male": "MLE",
    "maldives": "MLE", "bali": "DPS", "phuket": "HKT", "hanoi": "HAN",
    "ho chi minh": "SGN", "seoul": "ICN", "beijing": "PEK", "shanghai": "PVG",
    "abu dhabi": "AUH", "doha": "DOH", "muscat": "MCT", "jeddah": "JED",
    "mauritius": "MRU", "seychelles": "SEZ", "zanzibar": "ZNZ",
}


def resolve_iata(city: str) -> str:
    """Resolve a city name to its IATA code. Returns as-is if already a code."""
    lower = city.lower().strip()
    if lower in _IATA_CODES:
        return _IATA_CODES[lower]
    if len(city) == 3 and city.isalpha():
        return city.upper()
    return city.upper()[:3]


def _format_segment(seg: dict) -> str:
    dep = seg["departure"]
    arr = seg["arrival"]
    carrier = seg.get("carrierCode", "??")
    flight_no = seg.get("number", "")
    aircraft = seg.get("aircraft", {}).get("code", "")
    duration = seg.get("duration", "").replace("PT", "").lower()
    return (
        f"  {carrier}{flight_no} | {dep['iataCode']} {dep['at'][11:16]} → "
        f"{arr['iataCode']} {arr['at'][11:16]} | {duration} | {aircraft}"
    )


def _format_flights(data: dict) -> str:
    offers = data.get("data", [])
    if not offers:
        return "No flights found for the given criteria."

    dictionaries = data.get("dictionaries", {})
    carriers = dictionaries.get("carriers", {})

    lines: list[str] = []
    for i, offer in enumerate(offers, 1):
        price = offer["price"]
        currency = price.get("currency", "INR")
        total = price.get("grandTotal", price.get("total", "?"))

        lines.append(f"\n--- Option {i} — {currency} {total} ---")

        for j, itin in enumerate(offer.get("itineraries", [])):
            direction = "Outbound" if j == 0 else "Return"
            duration = itin.get("duration", "").replace("PT", "").lower()
            segments = itin.get("segments", [])
            stops = len(segments) - 1
            stop_str = "Direct" if stops == 0 else f"{stops} stop(s)"
            lines.append(f"  [{direction}] {stop_str} — total {duration}")
            for seg in segments:
                carrier_name = carriers.get(seg.get("carrierCode", ""), "")
                lines.append(_format_segment(seg))
                if carrier_name:
                    lines[-1] += f" ({carrier_name})"

    lines.append(f"\n{len(offers)} option(s) found.")
    return "\n".join(lines)


@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    travel_class: str = "ECONOMY",
    max_results: int = 5,
) -> str:
    """Search for real flights with airlines, timings, stops, and prices.

    Args:
        origin: Origin city name or IATA code (e.g. 'Delhi' or 'DEL').
        destination: Destination city name or IATA code.
        departure_date: Departure date as YYYY-MM-DD.
        return_date: Return date as YYYY-MM-DD (omit for one-way).
        adults: Number of adults.
        children: Number of children (2-11 years).
        infants: Number of infants (under 2).
        travel_class: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST.
        max_results: Maximum flight options to return (1-10).
    """
    if not amadeus_client.is_configured():
        return (
            "Amadeus API not configured. Set AMADEUS_API_KEY and AMADEUS_API_SECRET in .env.\n"
            "Sign up free at https://developers.amadeus.com (2000 calls/month free).\n"
            "Falling back to general knowledge for flight suggestions."
        )

    origin_code = resolve_iata(origin)
    dest_code = resolve_iata(destination)

    params: dict = {
        "originLocationCode": origin_code,
        "destinationLocationCode": dest_code,
        "departureDate": departure_date,
        "adults": adults,
        "travelClass": travel_class,
        "max": min(max_results, 10),
        "currencyCode": "INR",
    }
    if children:
        params["children"] = children
    if infants:
        params["infants"] = infants
    if return_date:
        params["returnDate"] = return_date

    try:
        data = amadeus_client.get("/v2/shopping/flight-offers", params)
        return _format_flights(data)
    except Exception as e:
        return f"Flight search error: {e}"

