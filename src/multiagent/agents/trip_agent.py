"""Trip Planner Agent — preference-aware trip planning with itineraries, transport & hotels."""

from __future__ import annotations

import json

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from multiagent.tools.user_preferences import (
    add_past_trip,
    load_preferences,
    update_preferences,
)


# ---------------------------------------------------------------------------
# Preference management tools
# ---------------------------------------------------------------------------
@tool
def get_travel_preferences() -> str:
    """Retrieve the user's saved travel preferences (family, style, budget, hotel, transport, food)."""
    prefs = load_preferences()
    return json.dumps(prefs, indent=2)


@tool
def save_travel_preferences(updates_json: str) -> str:
    """Save or update travel preferences. Pass a JSON string with keys to update.

    Top-level keys: family, trip_style, budget_level, hotel_preferences,
    transport_preferences, food_preferences, accessibility_needs.

    Example: '{"family": {"adults": 2, "children": 1, "child_ages": [5]}, "trip_style": "leisure"}'
    """
    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError:
        return "Error: invalid JSON. Please provide a valid JSON string."
    merged = update_preferences(updates)
    return f"Preferences updated.\n{json.dumps(merged, indent=2)}"


@tool
def record_past_trip(destination: str, dates: str, rating: int = 0, notes: str = "") -> str:
    """Record a completed trip to build preference history.

    Args:
        destination: City or region visited.
        dates: e.g. '2025-12-20 to 2025-12-27'.
        rating: 1-5 (0 = unrated).
        notes: What the user liked/disliked about this trip.
    """
    add_past_trip(destination, dates, rating or None, notes)
    return f"Recorded trip to {destination} ({dates})."


# ---------------------------------------------------------------------------
# Suggestion tools — preference-aware
# ---------------------------------------------------------------------------
def _prefs_summary() -> str:
    """Build a compact preference context string for LLM prompts."""
    p = load_preferences()
    fam = p["family"]
    family_str = f"{fam['adults']} adults"
    if fam["children"]:
        family_str += f", {fam['children']} children (ages {fam['child_ages']})"
    if fam["elderly"]:
        family_str += f", {fam['elderly']} elderly"
    if fam["pets"]:
        family_str += ", traveling with pets"

    hotel = p["hotel_preferences"]
    transport = p["transport_preferences"]
    food = p["food_preferences"]

    past = p.get("past_trips", [])
    past_str = ""
    if past:
        recent = past[-5:]
        past_str = "Recent trips: " + "; ".join(
            f"{t['destination']} ({t.get('rating', '?')}/5)" for t in recent
        )

    return (
        f"Family: {family_str}\n"
        f"Trip style: {p['trip_style']}\n"
        f"Budget: {p['budget_level']}\n"
        f"Hotel: {hotel['star_rating_min']}+ stars, room={hotel['room_type']}, "
        f"amenities={hotel['preferred_amenities']}\n"
        f"Transport: flight={transport['flight_class']}, "
        f"direct={transport['prefer_direct_flights']}, "
        f"train={transport['open_to_trains']}, car={transport['open_to_rental_car']}\n"
        f"Food: dietary={food['dietary']}, likes={food['cuisine_likes']}\n"
        f"Accessibility: {p.get('accessibility_needs', [])}\n"
        f"{past_str}"
    )


@tool
def suggest_itinerary(destination: str, days: int, interests: str = "") -> str:
    """Suggest a day-by-day itinerary tailored to the user's preferences.

    Args:
        destination: City or region to visit.
        days: Number of days.
        interests: Optional extra interests for this trip (e.g. 'history, wine').
    """
    ctx = _prefs_summary()
    p = load_preferences()
    style = p["trip_style"]

    style_guidance = {
        "leisure": (
            "Plan a relaxed pace — no more than 2 activities per day. "
            "Include downtime, late starts, and leisure options (cafés, parks, spas)."
        ),
        "balanced": (
            "Mix sightseeing with free time. 2-3 activities per day with "
            "breaks for meals and rest."
        ),
        "packed_sightseeing": (
            "Pack the days with top attractions and hidden gems. "
            "Early starts, full days, maximize coverage."
        ),
        "adventure": (
            "Focus on adventure activities: hiking, water sports, local experiences. "
            "Off-the-beaten-path destinations preferred."
        ),
    }

    guidance = style_guidance.get(style, style_guidance["balanced"])

    children = p["family"]["children"]
    kid_note = ""
    if children:
        ages = p["family"]["child_ages"]
        kid_note = (
            f"\nTraveling with {children} child(ren) aged {ages}. "
            "Include kid-friendly activities, rest time, and easy dining options."
        )

    return (
        f"=== Itinerary Suggestion: {destination} ({days} days) ===\n\n"
        f"User context:\n{ctx}\n\n"
        f"Style guidance: {guidance}{kid_note}\n"
        f"Extra interests: {interests or 'none specified'}\n\n"
        f"Please generate a detailed day-by-day plan for {destination} over {days} days "
        f"considering all the above preferences. Include:\n"
        f"- Morning / afternoon / evening blocks\n"
        f"- Restaurant type suggestions matching dietary preferences\n"
        f"- Travel time estimates between spots\n"
        f"- Cost estimates per day ({p['budget_level']} budget)"
    )


@tool
def suggest_hotels(city: str, checkin: str, checkout: str) -> str:
    """Suggest hotels based on saved preferences (budget, family size, amenities).

    Args:
        city: City to stay in.
        checkin: Check-in date (YYYY-MM-DD).
        checkout: Check-out date (YYYY-MM-DD).
    """
    p = load_preferences()
    fam = p["family"]
    hotel = p["hotel_preferences"]
    budget = p["budget_level"]

    total_people = fam["adults"] + fam["children"] + fam["elderly"]
    rooms_hint = max(1, (total_people + 1) // 2)  # rough: 2 per room
    if fam["children"] and fam["adults"] >= 2:
        rooms_hint = max(1, fam["adults"] // 2 + (1 if fam["children"] else 0))

    budget_ranges = {
        "budget": "$50-$100/night",
        "moderate": "$100-$200/night",
        "premium": "$200-$400/night",
        "luxury": "$400+/night",
    }

    kid_features = ""
    if fam["children"]:
        kid_features = (
            "Family-friendly features needed: cribs/extra beds, "
            "kids' menu, babysitting, play area. "
        )

    amenities = ", ".join(hotel["preferred_amenities"]) if hotel["preferred_amenities"] else "none specified"
    chains = ", ".join(hotel["preferred_chains"]) if hotel["preferred_chains"] else "no preference"

    return (
        f"=== Hotel Suggestions: {city} ({checkin} to {checkout}) ===\n\n"
        f"Party size: {total_people} people ({fam['adults']} adults, "
        f"{fam['children']} children, {fam['elderly']} elderly)\n"
        f"Estimated rooms needed: {rooms_hint}\n"
        f"Budget range: {budget_ranges.get(budget, budget_ranges['moderate'])}\n"
        f"Minimum stars: {hotel['star_rating_min']}\n"
        f"Room type: {hotel['room_type']}\n"
        f"Required amenities: {amenities}\n"
        f"Preferred chains: {chains}\n"
        f"{kid_features}"
        f"Accessibility needs: {p.get('accessibility_needs', [])}\n\n"
        f"Please suggest 3-5 hotel options in {city} matching these criteria, "
        f"with approximate pricing and pros/cons for each."
    )


@tool
def suggest_transport(origin: str, destination: str, date: str, travelers: int = 0) -> str:
    """Suggest transport options based on saved preferences.

    Args:
        origin: Departure city.
        destination: Arrival city.
        date: Travel date (YYYY-MM-DD).
        travelers: Number of travelers (0 = auto-detect from family config).
    """
    p = load_preferences()
    fam = p["family"]
    transport = p["transport_preferences"]
    budget = p["budget_level"]

    total = travelers or (fam["adults"] + fam["children"] + fam["elderly"])

    options = []
    options.append(
        f"✈️ Flight: {transport['flight_class']} class, "
        f"{'direct preferred' if transport['prefer_direct_flights'] else 'connections OK'}"
    )
    if transport["open_to_trains"]:
        options.append("🚄 Train: user is open to train travel")
    if transport["open_to_rental_car"]:
        options.append("🚗 Rental car: user is open to driving")
    if transport["open_to_bus"]:
        options.append("🚌 Bus: user is open to bus travel")

    kid_note = ""
    if fam["children"]:
        ages = fam["child_ages"]
        kid_note = (
            f"\nTraveling with children (ages {ages}). "
            "Consider: car seats, family boarding, extra luggage allowance."
        )

    return (
        f"=== Transport Options: {origin} → {destination} on {date} ===\n\n"
        f"Travelers: {total}\n"
        f"Budget level: {budget}\n"
        f"Preferred options:\n" + "\n".join(f"  {o}" for o in options) +
        f"{kid_note}\n\n"
        f"Please compare available transport options with:\n"
        f"- Approximate cost for {total} travelers\n"
        f"- Duration and convenience\n"
        f"- Recommendation based on preferences"
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
TRIP_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Trip Planner Agent for Munish Goyal's personal assistant.

You plan trips end-to-end: itineraries, hotels, transport, packing, and local tips.
You are PREFERENCE-AWARE — always start by loading the user's saved preferences
with get_travel_preferences before making any suggestions.

Your workflow:
1. ALWAYS call get_travel_preferences first to understand the user's profile.
2. If key preferences are missing (family config, trip style, budget), ASK the user
   and then call save_travel_preferences to persist their answers.
3. When suggesting itineraries, hotels, or transport — use the preference-aware tools
   (suggest_itinerary, suggest_hotels, suggest_transport) that automatically
   incorporate saved preferences.
4. After a trip is discussed/completed, offer to record_past_trip to improve future
   suggestions.
5. Learn from past trips — if a user rated a destination poorly, avoid similar
   suggestions; if highly rated, suggest similar experiences.

Key preference dimensions you track:
- Family: adults, children (ages), elderly, pets
- Trip style: leisure (relaxed) | balanced | packed_sightseeing | adventure
- Budget: budget | moderate | premium | luxury
- Hotel: star rating, amenities, room type, chain preferences
- Transport: flight class, direct flights, openness to trains/cars/buses
- Food: dietary restrictions, cuisine preferences
- Accessibility needs
- Past trip history with ratings

Be proactive: if the user says "plan a trip to Goa" without details, pull their
preferences and generate a complete personalized suggestion rather than asking
20 questions. Only ask what you truly cannot infer.
""")

TRIP_TOOLS = [
    get_travel_preferences,
    save_travel_preferences,
    record_past_trip,
    suggest_itinerary,
    suggest_hotels,
    suggest_transport,
]
