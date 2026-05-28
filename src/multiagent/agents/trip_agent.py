"""Trip Planner Agent — help plan trips with itineraries and logistics."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for flights between two cities on a given date."""
    return f"[STUB] Would search flights from {origin} to {destination} on {date}."


@tool
def search_hotels(city: str, checkin: str, checkout: str, budget: str = "moderate") -> str:
    """Search for hotels in a city within a budget range."""
    return f"[STUB] Would search {budget} hotels in {city} from {checkin} to {checkout}."


@tool
def create_itinerary(destination: str, days: int, interests: str = "") -> str:
    """Generate a day-by-day trip itinerary."""
    return (
        f"[STUB] Would create a {days}-day itinerary for {destination}. "
        f"Interests: {interests or 'general sightseeing'}."
    )


TRIP_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Trip Planner Agent. You help the user plan trips end-to-end:
flights, hotels, itineraries, packing lists, and local tips.
Ask clarifying questions about dates, budget, and preferences before planning.
""")

TRIP_TOOLS = [search_flights, search_hotels, create_itinerary]
