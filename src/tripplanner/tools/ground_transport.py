"""Ground transportation search via Kiwi.com trains, coaches, and ferries APIs."""

from __future__ import annotations

from langchain_core.tools import tool

from tripplanner.providers.models import CoachOffer, CoachSearchQuery, FerryOffer, FerrySearchQuery, RailOffer, RailSearchQuery
from tripplanner.providers.registry import get_coach_provider, get_ferry_provider, get_train_provider


def _format_rail(offers: list[RailOffer]) -> str:
    """Format train/rail offers for display to the user."""
    if not offers:
        return "No train options found for the given criteria."

    lines: list[str] = []
    for i, offer in enumerate(offers, 1):
        total = offer.total
        price_str = f"{total.currency} {total.amount}" if total else "price not published"

        provider = offer.provider
        journey_duration = offer.journey_duration_min
        direct = "Direct" if offer.direct else f"{offer.changes or 0} stop(s)"
        status = offer.status.value if offer.status else "unknown"
        
        duration_str = ""
        if journey_duration:
            hours = journey_duration // 60
            minutes = journey_duration % 60
            duration_str = f" | {hours}h {minutes}m"
        
        lines.append(f"\n--- Option {i} — {price_str} ---")
        lines.append(f"  Provider: {provider}")
        lines.append(f"  Journey: {direct}{duration_str}")
        lines.append(f"  Status: {status}")
        
        if offer.booking_url:
            lines.append(f"  Book: {offer.booking_url}")
        
        # Show segments
        for j, seg in enumerate(offer.segments, 1):
            dep = seg.get("departure", "?")
            arr = seg.get("arrival", "?")
            operator = seg.get("operator", "")
            duration = seg.get("duration", "")
            lines.append(f"    Leg {j}: {dep} → {arr}{' | ' + operator if operator else ''}{' | ' + str(duration) if duration else ''}")

    lines.append(f"\n{len(offers)} train option(s) found.")
    return "\n".join(lines)


def _format_coach(offers: list[CoachOffer]) -> str:
    """Format coach/bus offers for display to the user."""
    if not offers:
        return "No coach/bus options found for the given criteria."

    lines: list[str] = []
    for i, offer in enumerate(offers, 1):
        total = offer.total
        price_str = f"{total.currency} {total.amount}" if total else "price not published"

        provider = offer.provider
        operator = offer.operator_name or "Unknown operator"
        journey_duration = offer.journey_duration_min
        status = offer.status.value if offer.status else "unknown"
        
        duration_str = ""
        if journey_duration:
            hours = journey_duration // 60
            minutes = journey_duration % 60
            duration_str = f" | {hours}h {minutes}m"
        
        lines.append(f"\n--- Option {i} — {price_str} ---")
        lines.append(f"  Operator: {operator}")
        lines.append(f"  Provider: {provider}")
        lines.append(f"  Journey{duration_str}")
        lines.append(f"  Status: {status}")
        
        if offer.amenities:
            lines.append(f"  Amenities: {', '.join(offer.amenities)}")
        
        if offer.booking_url:
            lines.append(f"  Book: {offer.booking_url}")
        
        # Show segments
        for j, seg in enumerate(offer.segments, 1):
            dep = seg.get("departure", "?")
            arr = seg.get("arrival", "?")
            operator_seg = seg.get("operator", "")
            duration = seg.get("duration", "")
            lines.append(f"    Leg {j}: {dep} → {arr}{' | ' + operator_seg if operator_seg else ''}{' | ' + str(duration) if duration else ''}")

    lines.append(f"\n{len(offers)} coach option(s) found.")
    return "\n".join(lines)


def _format_ferry(offers: list[FerryOffer]) -> str:
    """Format ferry offers for display to the user."""
    if not offers:
        return "No ferry options found for the given criteria."

    lines: list[str] = []
    for i, offer in enumerate(offers, 1):
        total = offer.total
        currency = total.currency
        amount = total.amount
        
        provider = offer.provider
        route = offer.route_name or "Unknown route"
        journey_duration = offer.journey_duration_min
        status = offer.status.value if offer.status else "unknown"
        
        duration_str = ""
        if journey_duration:
            hours = journey_duration // 60
            minutes = journey_duration % 60
            duration_str = f" | {hours}h {minutes}m"
        
        lines.append(f"\n--- Option {i} — {currency} {amount} ---")
        lines.append(f"  Route: {route}")
        lines.append(f"  Provider: {provider}")
        lines.append(f"  Journey{duration_str}")
        lines.append(f"  Status: {status}")
        
        if offer.cabin_options:
            lines.append(f"  Cabin options: {', '.join(offer.cabin_options)}")
        
        if offer.booking_url:
            lines.append(f"  Book: {offer.booking_url}")
        
        # Show segments
        for j, seg in enumerate(offer.segments, 1):
            dep = seg.get("departure", "?")
            arr = seg.get("arrival", "?")
            operator_seg = seg.get("operator", "")
            duration = seg.get("duration", "")
            lines.append(f"    Leg {j}: {dep} → {arr}{' | ' + operator_seg if operator_seg else ''}{' | ' + str(duration) if duration else ''}")

    lines.append(f"\n{len(offers)} ferry option(s) found.")
    return "\n".join(lines)


@tool
def search_trains(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    children: int = 0,
    max_results: int = 5,
) -> str:
    """Search for real train routes with pricing and timings.

    Args:
        origin: Origin city or station name (e.g. 'Delhi' or 'New Delhi Railway Station').
        destination: Destination city or station name.
        departure_date: Departure date as YYYY-MM-DD.
        return_date: Return date as YYYY-MM-DD (omit for one-way).
        adults: Number of adults.
        children: Number of children.
        max_results: Maximum train options to return (1-20).

    Returns:
        Formatted train options with prices, durations, and booking links.
    """
    provider = get_train_provider()
    if provider is None:
        return (
            "Train provider not configured. Set KIWI_API_KEY in .env to enable train search.\n"
            "Sign up free at https://www.kiwi.com/business/trains"
        )

    try:
        query = RailSearchQuery(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            children=children,
            max_results=min(max_results, 20),
        )
        offers = provider.search_rails(query)
        return _format_rail(offers)
    except Exception as e:
        return f"Train search error: {e}"


@tool
def search_coaches(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    children: int = 0,
    max_results: int = 5,
) -> str:
    """Search for real coach/bus routes with pricing and timings.

    Args:
        origin: Origin city name (e.g. 'Delhi' or 'New Delhi').
        destination: Destination city name.
        departure_date: Departure date as YYYY-MM-DD.
        return_date: Return date as YYYY-MM-DD (omit for one-way).
        adults: Number of adults.
        children: Number of children.
        max_results: Maximum coach options to return (1-20).

    Returns:
        Formatted coach options with prices, operators, amenities, and booking links.
    """
    provider = get_coach_provider()
    if provider is None:
        return (
            "Coach provider not configured. Set KIWI_API_KEY in .env to enable coach search.\n"
            "Sign up free at https://www.kiwi.com/business/coaches"
        )

    try:
        query = CoachSearchQuery(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            children=children,
            max_results=min(max_results, 20),
        )
        offers = provider.search_coaches(query)
        return _format_coach(offers)
    except Exception as e:
        return f"Coach search error: {e}"


@tool
def search_ferries(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    children: int = 0,
    max_results: int = 5,
) -> str:
    """Search for real ferry routes with pricing and timings.

    Args:
        origin: Origin port city name (e.g. 'Istanbul' or 'Genoa').
        destination: Destination port city name.
        departure_date: Departure date as YYYY-MM-DD.
        return_date: Return date as YYYY-MM-DD (omit for one-way).
        adults: Number of adults.
        children: Number of children.
        max_results: Maximum ferry options to return (1-20).

    Returns:
        Formatted ferry options with prices, routes, cabin options, and booking links.
    """
    provider = get_ferry_provider()
    if provider is None:
        return (
            "Ferry provider not configured. Set KIWI_API_KEY in .env to enable ferry search.\n"
            "Sign up free at https://www.kiwi.com/business/ferries"
        )

    try:
        query = FerrySearchQuery(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            children=children,
            max_results=min(max_results, 20),
        )
        offers = provider.search_ferries(query)
        return _format_ferry(offers)
    except Exception as e:
        return f"Ferry search error: {e}"
