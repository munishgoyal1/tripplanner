"""Saved trip context for editable booking searches; no provider calls."""

import math
import re

from tripplanner.party import party_counts, party_size


def _count(value, fallback):
    try:
        parsed = float(value)
        return (
            int(parsed)
            if math.isfinite(parsed) and parsed >= 0 and parsed.is_integer()
            else fallback
        )
    except (ValueError, TypeError):
        return fallback


def research_defaults(plan: dict) -> dict:
    preferences = plan.get("preferences_snapshot") or {}
    family = preferences.get("family") or {}
    text = str(plan.get("travelers") or "")
    counts = party_counts(plan.get("travelers"))
    assumptions = []
    if counts:
        adults = counts.get("adults", 1)
        children = counts.get("children", 0)
        infants = counts.get("infants", 0)
        if "adults" not in counts:
            assumptions.append("One adult assumed; the trip does not specify the adult count.")
    elif party_size(plan.get("travelers")):
        adults, children, infants = party_size(plan.get("travelers")), 0, 0
        assumptions.append(
            "The saved headcount does not distinguish ages; all travellers are provisionally adults."
        )
    else:
        adults = _count(family.get("adults"), 1) or 1
        children = _count(family.get("children"), 0)
        infants = 0
        assumptions.append("Party counts use saved family defaults; confirm who is travelling.")
    ages_match = re.search(
        r"(?:\bages?\s*[:=]?\s*\[?|\b(?:children|kids?)\s*\()\s*(\d[\d.,\sand]*)", text, re.I
    )
    ages = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", ages_match[1])] if ages_match else []
    if len(ages) != children + infants:
        ages = list(family.get("child_ages") or [])
        if ages:
            assumptions.append(
                "Child ages use the saved family profile; confirm ages on the travel dates."
            )
    if len(ages) != children + infants:
        ages = []
        if children + infants:
            assumptions.append("Supply an age for every child/infant before hotel research.")
    valid_ages = []
    for age in ages:
        try:
            number = float(age)
            if math.isfinite(number) and 0 <= number < 18:
                valid_ages.append(math.floor(number))
        except (ValueError, TypeError):
            pass
    ages = valid_ages
    # The flight provider distinguishes under-twos from children. Saved trip
    # wording may include a toddler in the child count.
    flight_children, flight_infants = children, infants
    if ages and len(ages) == children + infants:
        flight_children = sum(age >= 2 for age in ages)
        flight_infants = sum(age < 2 for age in ages)
    common = {
        "origin": plan.get("origin") or "",
        "destination": plan.get("destination") or "",
        "start_date": plan.get("departure_date") or "",
        "end_date": plan.get("return_date") or "",
        "adults": adults,
        "children": flight_children,
        "infants": flight_infants,
        "children_ages": ages,
        "rooms": 1,
        "currency": plan.get("currency") or "INR",
        "nationality": "",
        "cabin": "ECONOMY",
        "refundable_only": False,
    }
    flights = []
    for index, flight in enumerate(plan.get("selected_flights") or []):
        if not isinstance(flight, dict):
            continue
        flights.append(
            {
                "id": f"flight-{index}",
                "label": str(flight.get("name") or flight.get("airline") or "Saved flight"),
                "search": {
                    **common,
                    "category": "flights",
                    "origin": flight.get("from") or common["origin"],
                    "destination": flight.get("to") or common["destination"],
                    "start_date": flight.get("departure_date") or common["start_date"],
                    "end_date": flight.get("return_date") or "",
                },
                "assumptions": assumptions,
            }
        )
    hotels = []
    for index, hotel in enumerate(plan.get("selected_hotels") or []):
        if not isinstance(hotel, dict):
            continue
        context = hotel.get("search_context") or {}
        rooms = _count(context.get("rooms"), 1) or 1
        per_room = _count(context.get("adults_per_room"), adults) or adults
        notes = list(assumptions)
        if per_room * rooms != adults or not context.get("rooms"):
            rooms, per_room = 1, adults
            notes.append(
                "All adults are included in one room provisionally; set the room allocation before research."
            )
        city = hotel.get("city") or hotel.get("destination") or context.get("destination") or ""
        if not city:
            notes.append("The saved hotel has no city; enter its city before research.")
        nationality = context.get("guest_nationality") or ""
        if not nationality:
            notes.append("Guest nationality is not recorded; enter it before hotel research.")
        hotels.append(
            {
                "id": f"hotel-{index}",
                "label": str(hotel.get("name") or hotel.get("hotel_name") or "Saved stay"),
                "search": {
                    **common,
                    "category": "hotels",
                    "destination": city,
                    "start_date": hotel.get("checkin") or "",
                    "end_date": hotel.get("checkout") or "",
                    "rooms": rooms,
                    "adults": per_room,
                    "nationality": nationality,
                },
                "assumptions": notes,
            }
        )
    return {
        "flights": flights
        or [
            {
                "id": "flight",
                "label": "Trip dates",
                "search": {**common, "category": "flights"},
                "assumptions": assumptions,
            }
        ],
        "hotels": hotels
        or [
            {
                "id": "hotel",
                "label": "Trip dates — choose stay city",
                "search": {**common, "category": "hotels"},
                "assumptions": [
                    *assumptions,
                    "One room assumed. Confirm stay city, check-in, checkout and guest nationality.",
                ],
            }
        ],
    }
