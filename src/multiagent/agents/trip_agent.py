"""Trip Planner Agent — full-service trip planning with real search, bookings & preferences."""

from __future__ import annotations

import json

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from multiagent.tools.activities_search import search_activities, search_points_of_interest
from multiagent.tools.flight_search import search_flights
from multiagent.tools.google_places import (
    get_place_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from multiagent.tools.hotel_search import search_hotels
from multiagent.tools.trip_planner import (
    create_trip_plan,
    execute_bookings,
    finalize_trip,
    get_trip_plan,
    list_past_trips,
    update_trip_plan,
)
from multiagent.tools.user_preferences import (
    add_past_trip,
    load_preferences,
    update_preferences,
)
from multiagent.tools.web_search import web_search


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
    """Record a completed trip to build preference history and improve future suggestions.

    Args:
        destination: City or region visited.
        dates: e.g. '2025-12-20 to 2025-12-27'.
        rating: 1-5 (0 = unrated).
        notes: What the user liked/disliked about this trip.
    """
    add_past_trip(destination, dates, rating or None, notes)
    return f"Recorded trip to {destination} ({dates})."


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
TRIP_SYSTEM_PROMPT = SystemMessage(content="""\
You are a full-service Trip Planner Agent. Your goal is to produce a complete,
bookable trip plan in the fewest interactions possible — ideally under 30 minutes
of user time.

═══════════════════════════════════════════════════════════════
WORKFLOW (follow this order every time):
═══════════════════════════════════════════════════════════════

STEP 1 — LOAD PREFERENCES (silent, automatic)
  Call get_travel_preferences immediately. Never skip this.
  If critical info is missing (family config, budget, style), ask ONCE with a
  consolidated question covering everything you need.
  Save answers with save_travel_preferences.

STEP 2 — UNDERSTAND THE REQUEST
  User says something like "plan a trip to Goa" or "we want to go somewhere warm".
  Extract: destination, dates, origin city.
  If dates aren't given, suggest reasonable dates and confirm.
  Call create_trip_plan to initialize the plan.

STEP 3 — PARALLEL SEARCH (do all at once)
  Call these tools in parallel based on preferences:
  a) search_flights — real flights with airlines, times, stops, prices
  b) search_hotels — real hotels with names, ratings, prices (Amadeus pricing)
  c) search_places_with_reviews — Google ratings/reviews for shortlisted hotels
     and attractions. ALWAYS run this on any hotel before recommending it.
  d) search_activities — sightseeing, tours, attraction tickets with prices
  e) nearby_restaurants — top-rated restaurants near the hotel matching dietary needs
  f) web_search — fresh travel guides, recent reviews, seasonal advice when
     structured APIs don't cover it (e.g. "is Goa safe in monsoon?")

  Present results in a clean summary:
  ┌──────────────────────────────────────────────┐
  │ ✈️ FLIGHTS: top 3-5 options                  │
  │ 🏨 HOTELS: top 3-5 with Google rating + price│
  │ 🍽️ RESTAURANTS: 5-8 rated 4.0+ near hotel    │
  │ 🎯 ACTIVITIES: top 5-10 options              │
  │ 💰 COST ESTIMATE: total per person           │
  └──────────────────────────────────────────────┘

STEP 4 — BUILD ITINERARY
  Using the preferences (trip_style, family, dietary needs), build a day-by-day
  itinerary that includes:
  - Morning / afternoon / evening activities
  - Specific restaurant recommendations (matching dietary prefs)
  - Travel time between spots
  - Which attraction tickets to pre-book
  - Local transport within the destination
  - Cost per day

  Update the trip plan with update_trip_plan.

STEP 5 — REFINE (1-2 rounds max)
  Ask: "Does this look good, or would you like to adjust anything?"
  Handle changes efficiently. Don't re-search everything — just what changed.

STEP 6 — FINALIZE
  Call finalize_trip to lock the plan and show the complete cost breakdown.
  Show a clear summary with everything booked.

STEP 7 — EXECUTE (on user command)
  When user says "execute", "book it", "go ahead", or similar:
  Call execute_bookings to process all bookings.
  The trip is saved to history automatically.

═══════════════════════════════════════════════════════════════
PREFERENCE DIMENSIONS YOU TRACK:
═══════════════════════════════════════════════════════════════
- Family: adults, children (ages), elderly, pets
- Trip style: leisure | balanced | packed_sightseeing | adventure
- Budget: budget | moderate | premium | luxury
- Hotel: star rating, amenities (pool, gym, breakfast, spa), room type, chains
- Transport: flight class, direct flights preference, train/car/bus openness
- Food: dietary restrictions, cuisine likes/dislikes
- Accessibility needs
- Past trip history with ratings

═══════════════════════════════════════════════════════════════
CRITICAL RULES:
═══════════════════════════════════════════════════════════════
1. BE PROACTIVE — don't ask 20 questions. Use saved preferences + past trips to
   generate a near-final plan immediately. Only ask what you truly cannot infer.
2. SHOW REAL DATA — always search for actual flights, hotels, and activities with
   real prices. Never give vague "around $X" estimates when you can search.
   For ratings & reviews use search_places_with_reviews / get_place_reviews — do NOT
   make up ratings or review snippets. Cite real Google ratings (e.g. "4.6★, 1.2k reviews").
3. COSTS EVERYWHERE — every suggestion must have a price. Show per-person and
   total costs. Include cost breakdown at the end.
4. LEARN FROM HISTORY — if a user rated a past trip highly, suggest similar
   experiences. If rated poorly, avoid similar options.
5. COMPLETE PLANS — a finalized plan must include: flights, hotels, day-wise
   itinerary, activity tickets, local transport, restaurant suggestions, and
   a total cost breakdown.
6. If Amadeus API is not configured, use your knowledge to provide realistic
   recommendations with approximate pricing, and note that real-time prices
   require API setup.
""")

TRIP_TOOLS = [
    # Preferences
    get_travel_preferences,
    save_travel_preferences,
    record_past_trip,
    # Real search (Amadeus — bookable inventory)
    search_flights,
    search_hotels,
    search_activities,
    search_points_of_interest,
    # Ratings & reviews (Google Places)
    search_places_with_reviews,
    get_place_reviews,
    nearby_restaurants,
    # Fresh web content (Tavily)
    web_search,
    # Trip plan management
    create_trip_plan,
    get_trip_plan,
    update_trip_plan,
    finalize_trip,
    execute_bookings,
    list_past_trips,
]
