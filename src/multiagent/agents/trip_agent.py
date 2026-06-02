"""Trip Planner Agent — full-service trip planning with real search, bookings & preferences."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from multiagent.tools.activities_search import search_activities, search_points_of_interest
from multiagent.tools.duffel_flights import search_flights_duffel
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
    add_dislike,
    add_interest,
    add_learned_note,
    add_past_trip,
    add_trip_mention,
    load_preferences,
    update_preferences,
    update_profile,
    upsert_family_member,
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


@tool
def remember_about_user(note: str, source: str = "stated") -> str:
    """Save a free-form observation about the user for future trips.

    Use this AGGRESSIVELY whenever the user reveals a stable preference, fear,
    constraint, or pattern that isn't captured by the structured preference
    schema. Examples worth remembering:
      - "prefers window seats on long flights"
      - "anxious flyer — avoid red-eye and turbulent routes"
      - "always travels with mother who needs an elevator"
      - "loves boutique hotels over chains, hates Marriott"
      - "wakes up early, prefers morning departures"
      - "vegetarian but wife eats seafood"
      - "history of motion sickness on winding roads"

    Args:
        note: One concise sentence about the user (max ~150 chars).
        source: "stated" if the user said it explicitly, "inferred" if you
                deduced it from behavior (e.g. always picks 5-star hotels →
                "prefers luxury accommodation").
    """
    add_learned_note(note, source=source)
    label = source if source in ("stated", "inferred") else "stated"
    return f"Remembered ({label}): {note}"


@tool
def update_user_profile(
    display_name: str | None = None,
    home_city: str | None = None,
    home_country: str | None = None,
    age_band: str | None = None,
    occupation: str | None = None,
) -> str:
    """Save basic profile facts about the user.

    Call this as soon as you learn the user's name, city, country, age band,
    or occupation. Pass ONLY the fields you just learned (others stay
    unchanged). Examples:
      - User: "I'm Munish from Bengaluru" → update_user_profile(display_name="Munish", home_city="Bengaluru", home_country="India")
      - User: "I'm a doctor" → update_user_profile(occupation="doctor")

    Args:
        display_name: First name or how the user introduces themselves.
        home_city: City of residence (e.g. "Bengaluru").
        home_country: Country of residence (e.g. "India").
        age_band: One of "20-30", "30-40", "40-50", "50-60", "60+".
        occupation: Free-form (e.g. "software engineer", "retired teacher").
    """
    update_profile({
        "display_name": display_name,
        "home_city": home_city,
        "home_country": home_country,
        "age_band": age_band,
        "occupation": occupation,
    })
    saved = {k: v for k, v in {
        "display_name": display_name,
        "home_city": home_city,
        "home_country": home_country,
        "age_band": age_band,
        "occupation": occupation,
    }.items() if v}
    return f"Profile updated: {saved}" if saved else "Profile unchanged (nothing to save)."


@tool
def add_family_member(
    relationship: str,
    name: str | None = None,
    age: int | None = None,
    dietary: list[str] | None = None,
    mobility: list[str] | None = None,
    interests: list[str] | None = None,
    notes: str | None = None,
) -> str:
    """Add or update a family member who travels with the user.

    Upserts by (relationship, name). Use this whenever the user mentions
    someone in their travel party — spouse, child, parent, sibling, friend,
    pet. Examples:
      - "my wife Priya loves beaches" → add_family_member(relationship="spouse", name="Priya", interests=["beaches"])
      - "my son is 8 and allergic to peanuts" → add_family_member(relationship="child", age=8, dietary=["nut-free"])
      - "my mom uses a wheelchair" → add_family_member(relationship="parent", mobility=["wheelchair"])

    Args:
        relationship: spouse | partner | child | parent | sibling | friend | pet | other
        name: Their name if known (omit if not).
        age: Age in years (omit if not known).
        dietary: Dietary restrictions (vegetarian, vegan, halal, nut-free, etc.).
        mobility: Mobility constraints (wheelchair, walking-stick, slow-walker).
        interests: Things they like (beaches, museums, hiking, photography).
        notes: One-line free-form note.
    """
    upsert_family_member(
        relationship=relationship,
        name=name,
        age=age,
        dietary=dietary,
        mobility=mobility,
        interests=interests,
        notes=notes,
    )
    label = f"{relationship}" + (f" '{name}'" if name else "")
    return f"Saved family member: {label}."


@tool
def add_user_interest(item: str) -> str:
    """Add a high-level interest the user revealed (de-duped automatically).

    Use for broad themes — NOT trip-specific desires. Examples:
      - "I love photography" → add_user_interest("photography")
      - "we always do a wildlife safari" → add_user_interest("wildlife")
      - "I'm a foodie" → add_user_interest("food")
    """
    add_interest(item)
    return f"Added interest: {item}"


@tool
def add_user_dislike(item: str) -> str:
    """Add a high-level dislike (de-duped automatically).

    Examples:
      - "I hate crowded places" → add_user_dislike("crowded places")
      - "never put me on a bus longer than 4 hours" → add_user_dislike("long bus rides")
    """
    add_dislike(item)
    return f"Added dislike: {item}"


@tool
def record_trip_mention(
    destination: str,
    when: str | None = None,
    with_whom: str | None = None,
    sentiment: str = "neutral",
    notes: str = "",
) -> str:
    """Record a trip the user CASUALLY MENTIONED (different from record_past_trip).

    Use this when the user references past travel in conversation — even briefly:
      - "we went to Bali last summer and loved it" → record_trip_mention("Bali", when="summer 2024", sentiment="positive", notes="loved it")
      - "Goa was too crowded for us" → record_trip_mention("Goa", sentiment="negative", notes="found it too crowded")
      - "I visited Paris in 2019" → record_trip_mention("Paris", when="2019")

    De-dupes by (destination, when) — same trip won't be saved twice.

    Args:
        destination: City / region / country.
        when: Free-form time reference ("summer 2024", "Dec 2023", "2019").
        with_whom: "family", "friends", "solo", "spouse", etc.
        sentiment: "positive" | "negative" | "mixed" | "neutral".
        notes: One-line note about what made it positive/negative.
    """
    add_trip_mention(
        destination=destination,
        when=when,
        with_whom=with_whom,
        sentiment=sentiment,
        notes=notes,
    )
    return f"Recorded trip mention: {destination} ({when or 'unspecified time'}, {sentiment})."


# ---------------------------------------------------------------------------
# System prompt — built fresh on every request so today's date is current.
# ---------------------------------------------------------------------------
_PROMPT_TEMPLATE = """\
You are a full-service Trip Planner Agent. Your goal is to produce a complete,
bookable trip plan in the fewest interactions possible — ideally under 30 minutes
of user time.

═══════════════════════════════════════════════════════════════
TEMPORAL CONTEXT (refreshed each turn — trust this over your training data):
═══════════════════════════════════════════════════════════════
- TODAY is {today_iso} ({today_human}).
- Current year: {year}. Current month: {month_name}.
- Earliest sensible trip start: {min_trip_start} (≈ 1 week out for bookings).
- Default trip window if user is vague: {default_start} to {default_end}
  (4-6 weeks out, a comfortable booking horizon).

═══════════════════════════════════════════════════════════════
WORKFLOW (follow this order every time):
═══════════════════════════════════════════════════════════════

STEP 1 — LOAD PREFERENCES (silent, automatic)
  Call get_travel_preferences immediately. Never skip this.
  The loaded prefs include:
    • profile (name, home_city, country, age_band, occupation) — use to
      personalize greetings ("Hi Munish") and infer trip origins
    • family_members (spouse, kids, parents, pets with ages/dietary/mobility)
      — use these counts/needs INSTEAD of asking
    • interests / dislikes — bias suggestions toward likes, away from dislikes
    • past_trip_mentions — trips the user casually mentioned (with sentiment)
    • past_trips — agent-planned trips with ratings
    • learned_notes — observations from past conversations (fears, quirks,
      must-haves, deal-breakers)
  Use ALL of this to pre-tailor your suggestions instead of asking again.
  If genuinely critical info is missing (e.g. trip budget for THIS trip), ask
  ONCE with a consolidated question. Otherwise: DON'T ASK, INFER + EXTRACT.
  Save answers/extractions immediately via the appropriate tool.

STEP 2 — UNDERSTAND THE REQUEST
  User says something like "plan a trip to Goa" or "we want to go somewhere warm".
  Extract: destination, dates, origin city.
  DATE HANDLING (strict):
    - Resolve all relative phrases against TODAY shown above.
      "next weekend"  → the upcoming Saturday-Sunday from today.
      "next month"    → the next calendar month (not "30 days from now").
      "in 2 weeks"    → today + 14 days.
      "Diwali", "Christmas break", "Easter" → the next occurrence after today.
    - NEVER suggest a trip start date earlier than {min_trip_start}.
    - If no dates are given, propose {default_start} to {default_end} and confirm.
    - If the user gives a year, use it. If they don't, assume {year} (or {next_year}
      if the implied month has already passed this year).
  Call create_trip_plan to initialize the plan.

STEP 3 — PARALLEL SEARCH (do all at once)
  Call these tools in parallel based on preferences:
  a) search_flights_duffel — PREFERRED flight search (Duffel API). Real airlines,
     times, stops, prices. Use this first. Only fall back to search_flights
     (Amadeus) if Duffel returns nothing useful — Amadeus self-service is being
     decommissioned on July 17, 2026.
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
  IMMEDIATELY AFTER, call record_past_trip with destination, dates, and an
  initial rating of 0 (unrated) — the user will rate later. Include short
  notes summarizing what was booked (e.g. "5 nights at Taj Goa, IndiGo flights,
  3 activities — leisure trip with parents"). This is non-negotiable.
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
PASSIVE LEARNING — get smarter every conversation:
═══════════════════════════════════════════════════════════════
You are not just a planner — you are this user's lifelong travel concierge.
Every conversation MUST leave you smarter about them. NEVER ask for info you
can extract from what they've already said.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION CHECKLIST — listen for ANY of these signals every turn:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Signal user gives                          | Tool to call IMMEDIATELY    |
|--------------------------------------------|-----------------------------|
| Own name, city, country, age, job          | update_user_profile         |
| Family/partner/child/parent/pet mentioned  | add_family_member           |
| High-level interest ("I love photography") | add_user_interest           |
| High-level dislike ("I hate crowds")       | add_user_dislike            |
| Past trip mentioned ("we went to Bali")    | record_trip_mention         |
| Structured pref (food/hotel/flight class)  | save_travel_preferences     |
| Anything else (quirks, fears, life facts)  | remember_about_user         |

PARALLEL TOOL CALLS — when one message has multiple signals, FIRE ALL
RELEVANT TOOLS IN THE SAME TURN (parallel tool calls).
Example: "Hi, I'm Munish from Bengaluru, my wife Priya loves beaches and
my 8yo son is allergic to peanuts. We did Goa last year and it was too crowded."
→ Call ALL of these in one turn:
  • update_user_profile(display_name="Munish", home_city="Bengaluru", home_country="India")
  • add_family_member(relationship="spouse", name="Priya", interests=["beaches"])
  • add_family_member(relationship="child", age=8, dietary=["nut-free"])
  • record_trip_mention(destination="Goa", when="last year", sentiment="negative", notes="too crowded")
  • add_user_dislike("crowded places")

REFINEMENT RULES (keep prior data fresh as you learn more):
- ADD: brand-new info → save as a new entry
- MERGE: more detail on existing entity → call the same tool with the new
  fields; the upsert logic merges them
- CONFLICT: new info contradicts old → ASK ONCE ("I had you down as preferring
  X — is that changing permanently or just for this trip?") then update

QUALITY BAR (be aggressive but precise):
- ✅ DO save: stable preferences ("I always..."), reactions ("I hate..."),
     identity facts (name/city/job), family roster, past trip references,
     allergies, mobility constraints.
- ❌ DON'T save: one-off trip requests ("this time cheaper"), trip dates,
     duplicates of existing entries, guesses you're <80% confident about,
     anything sensitive the user clearly wants kept private.

CONFIRMATION (build trust, allow corrections):
- After extracting, give ONE SHORT acknowledgement at the end of your reply:
  "Got it — I've noted you're in Bengaluru, traveling with Priya and your son."
  Keep it to one line so the user can correct in one breath.

SOURCE TAGGING:
- For remember_about_user and record_trip_mention, use source="stated" when
  the user said it explicitly, "inferred" when you deduced it from their
  choices (e.g. they keep rejecting chain hotels → infer "prefers boutique").

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
4. LEARN FROM HISTORY — past_trips and learned_notes are your memory.
   - If a user rated a past trip 4-5, suggest similar experiences (same style,
     hotel tier, pace, activity types).
   - If rated 1-2, avoid similar options and call out why ("Last time you
     didn't enjoy beach resorts, so I'm focusing on hill stations").
   - Cite learned_notes when relevant: "Since you prefer aisle seats, I've
     filtered for those." Makes the user feel known.
5. COMPLETE PLANS — a finalized plan must include: flights, hotels, day-wise
   itinerary, activity tickets, local transport, restaurant suggestions, and
   a total cost breakdown.
6. If Amadeus API is not configured, use your knowledge to provide realistic
   recommendations with approximate pricing, and note that real-time prices
   require API setup.
7. NEVER suggest dates in the past relative to TODAY ({today_iso}). If the user
   asks for a date that has already passed, gently confirm whether they meant
   next year's equivalent.
"""


def build_trip_system_prompt(today: date | None = None) -> SystemMessage:
    """Construct the trip planner system prompt with today's date injected.

    Called per-request from the graph so the LLM always sees the current date.
    """
    today = today or datetime.now(timezone.utc).date()
    default_start = today + timedelta(weeks=4)
    default_end = today + timedelta(weeks=4, days=6)
    content = _PROMPT_TEMPLATE.format(
        today_iso=today.isoformat(),
        today_human=today.strftime("%A, %d %B %Y"),
        year=today.year,
        next_year=today.year + 1,
        month_name=today.strftime("%B"),
        min_trip_start=(today + timedelta(days=7)).isoformat(),
        default_start=default_start.isoformat(),
        default_end=default_end.isoformat(),
    )
    return SystemMessage(content=content)


# Back-compat: importers that still grab TRIP_SYSTEM_PROMPT get a snapshot
# built at import time. Prefer build_trip_system_prompt() for live agents.
TRIP_SYSTEM_PROMPT = build_trip_system_prompt()

TRIP_TOOLS = [
    # Preferences
    get_travel_preferences,
    save_travel_preferences,
    record_past_trip,
    remember_about_user,
    # Continuous learning (extract during natural conversation)
    update_user_profile,
    add_family_member,
    add_user_interest,
    add_user_dislike,
    record_trip_mention,
    # Flights — Duffel preferred, Amadeus kept as fallback (deprecating 2026-07-17)
    search_flights_duffel,
    search_flights,
    # Real search (Amadeus — bookable inventory)
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
