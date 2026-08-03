"""Trip Planner Agent — full-service trip planning with real search, bookings & preferences."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from tripplanner.chat_interactions import request_trip_input
from tripplanner.tools.activities_search import search_activities, search_points_of_interest
from tripplanner.tools.duffel_flights import search_flights_duffel, verify_flight_offer
from tripplanner.tools.events import find_local_events
from tripplanner.tools.flight_search import search_flights
from tripplanner.tools.google_places import (
    get_place_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from tripplanner.tools.hotel_search import search_hotels
from tripplanner.tools.memory_recall import recall_relevant_memory
from tripplanner.tools.place_hours import check_place_hours
from tripplanner.tools.routing import compute_route, optimize_day_route
from tripplanner.tools.trip_planner import (
    _load_active_trip,
    create_trip_plan,
    execute_bookings,
    finalize_trip,
    get_trip_plan,
    list_past_trips,
    resume_trip,
    update_trip_plan,
)
from tripplanner.tools.trip_shape import recommend_trip_duration
from tripplanner.tools.user_preferences import (
    add_dislike,
    add_interest,
    add_learned_note,
    add_past_trip,
    add_trip_mention,
    load_preferences,
    update_past_trip_postmortem,
    update_preferences,
    update_profile,
    upsert_family_member,
)
from tripplanner.tools.visa import check_visa_requirements
from tripplanner.tools.weather import get_weather_forecast
from tripplanner.tools.web_search import web_search


# ---------------------------------------------------------------------------
# Preference management tools
# ---------------------------------------------------------------------------
@tool
def get_travel_preferences() -> str:
    """Retrieve the user's saved travel preferences (family, style, budget, hotel, transport, food)."""
    prefs = load_preferences()
    # behavior_signals is an internal counter store (search-behavior inference);
    # never surface it to the agent — it's noise in the reasoning context.
    prefs.pop("behavior_signals", None)
    prefs.pop("_promoted_signals", None)
    return json.dumps(prefs, indent=2)


@tool
def save_travel_preferences(updates_json: str) -> str:
    """Save or update travel preferences. Pass a JSON string with keys to update.

    Top-level keys: profile, family, trip_style, budget_level,
    hotel_preferences, transport_preferences, food_preferences,
    accessibility_needs.

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
def record_trip_postmortem(
    destination: str,
    rating: int = 0,
    what_worked: str = "",
    what_didnt: str = "",
    dates: str = "",
  pace_feedback: str = "",
  actual_active_minutes_per_full_day: int = 0,
) -> str:
    """Capture a structured post-mortem after the trip ends.

    Use this AFTER execute_bookings (or any time the user reflects on a
    completed trip). It updates the matching past_trip entry with a 1-5 rating
    plus what_worked / what_didnt bullet lists, and also feeds each bullet
    into learned_notes so future planning sessions can recall the lesson.

    Args:
        destination: City or region the trip was to.
        rating: 1-5 (0 = leave unchanged).
        what_worked: semicolon-separated bullets the user liked ("private guide; rooftop bar; late checkout").
        what_didnt: semicolon-separated bullets the user disliked ("morning flight; airport hotel").
        dates: optional override for the dates field on the past_trip entry.
        pace_feedback: one of too_rushed, just_right, or too_sparse.
        actual_active_minutes_per_full_day: approximate active itinerary minutes.
    """
    worked = [s for s in (what_worked or "").split(";") if s.strip()]
    didnt = [s for s in (what_didnt or "").split(";") if s.strip()]
    update_past_trip_postmortem(
        destination=destination,
        rating=rating or None,
        what_worked=worked,
        what_didnt=didnt,
        dates=dates,
        pace_feedback=pace_feedback,
        actual_active_minutes_per_full_day=(
          actual_active_minutes_per_full_day or None
        ),
    )
    summary = [f"Post-mortem recorded for {destination}."]
    if rating:
        summary.append(f"Rating: {rating}/5.")
    if worked:
        summary.append(f"Liked: {', '.join(worked)}.")
    if didnt:
        summary.append(f"Disliked: {', '.join(didnt)}.")
    if pace_feedback:
      summary.append(f"Pace: {pace_feedback.replace('_', ' ')}.")
    summary.append("Lessons saved to learned_notes for future trips.")
    return " ".join(summary)

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
- Default trip start if the user is vague: {default_start}
  (4 weeks out, a comfortable booking horizon). Never assume a fixed trip length.

═══════════════════════════════════════════════════════════════
WORKFLOW (follow this order every time):
═══════════════════════════════════════════════════════════════

STEP 1 — LOAD PREFERENCES (silent, automatic)
  Call get_travel_preferences immediately. Never skip this.
  The loaded prefs include:
    • profile (name, home_city, home_area, country, age_band, occupation) — use to
      personalize greetings ("Hi Munish") and infer trip origins
    • family_members (spouse, kids, parents, pets with ages/dietary/mobility)
      — use these counts/needs INSTEAD of asking
    • interests / dislikes — bias suggestions toward likes, away from dislikes
    • past_trip_mentions — trips the user casually mentioned (with sentiment)
    • past_trips — agent-planned trips with ratings
    • learned_notes — observations from past conversations (fears, quirks,
      must-haves, deal-breakers)
  Use ALL of this to pre-tailor your suggestions instead of asking again.
  Before the kickoff, call recommend_trip_duration for EVERY new trip. Pass an
  explicit duration when the user supplied one; otherwise pass 4-12 likely,
  preference-matched anchor experiences with realistic visit durations and
  geographic clusters. Use its recommended_days to prefill the kickoff dates.
  CHECK planning_mode in the loaded prefs (default: "direct"):
    • "direct"      — For a NEW trip, show one compact pre-filled kickoff that
                      reviews saved context and sensible trip defaults. Do not
                      ask additional free-text clarifying questions; after the
                      user submits or skips, infer anything else and proceed to
                      a complete plan with real searches.
    • "interactive" — Use the same one-step kickoff and include any unresolved
                      critical dates, companions, accessibility, budget, or
                      long-drive mode/break preferences.
  For every NEW trip, call request_trip_input ONCE before create_trip_plan so
  capable clients render pre-filled controls instead of forcing the user to type.
  Include the relevant saved or inferred facts already applied in
  known_context_json, plus only useful trip-specific fields with sensible defaults.
  After the tool call, ask one short natural-language question for clients that
  do not support structured inputs. Never repeat the choices as a long numbered
  list and never ask again after the user submits or skips the kickoff.
  Save answers/extractions immediately via the appropriate tool.

  When the prefs blob is large or a specific concern surfaces ("does my dad
  still need an elevator?", "did we like Goa last time?"), call
  recall_relevant_memory(query) to surface the top 3 most relevant notes /
  past mentions / family details — much cheaper than re-loading and re-reading
  everything every turn.

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
    - If no dates are given, start at {default_start}, apply the advisor's fitting
      duration, and confirm those prefilled dates in the one-step kickoff.
    - If the user gives a year, use it. If they don't, assume {year} (or {next_year}
      if the implied month has already passed this year).
  Call create_trip_plan to initialize the plan. Copy the complete duration-advisor
  JSON into planning_recommendation_json so its evidence and reasoning remain auditable.
  RESUMING SAVED TRIPS: trips are remembered across logins. If the user
  references a place they planned before ("continue my Mumbai trip", "back to
  the Vietnam plan") or asks what they were working on, call resume_trip
  (by destination or trip_id) — or list_past_trips to show the options — so
  they pick up where they left off instead of restarting. create_trip_plan
  itself auto-resumes when the destination AND both dates match a saved trip;
  different dates/duration are kept as a separate, date-tagged trip.
  SWITCHING TO A NEW DESTINATION MID-CHAT: if, while planning one place, the
  user pivots to a DIFFERENT destination ("actually, plan me a trip to Kashmir"),
  treat it exactly like starting a new trip — call create_trip_plan for the new
  place. This opens a fresh trip and a fresh chat for it; portable details the
  user already shared (companions, budget, pace, dietary/accessibility needs,
  interests) carry over automatically, so don't re-ask for them — just confirm
  the new destination's dates and continue.
  If the user states a total budget for THIS trip ("keep it under 1.5 lakh",
  "$3000 max"), persist it immediately:
  update_trip_plan('{{"budget": 150000}}') so the live budget meter in the UI
  can track spend against it. Keep total_cost updated as selections firm up.

STEP 2.5 — SHARE A FIRST-CUT ITINERARY IMMEDIATELY (don't wait for searches)
  The moment you know the destination and rough dates, you MUST do BOTH:
  A) Call update_trip_plan with a day_wise_itinerary array (structured stops
     as shown in STEP 4). This MUST happen in the SAME turn — call the tool
     FIRST, then write the chat reply. A draft itinerary only in chat text
     will NOT appear in the Itinerary panel.
  B) Write a concise chat reply summarising the day plan with the note
     "Draft — I'll refine with real prices and availability next."

  Use your own travel knowledge + loaded preferences to build this first cut.
  Take ownership of the draft: choose sensible defaults for every day instead
  of asking the user to assemble the itinerary. The user can refine any choice
  conversationally after seeing a complete plan.
  Do NOT wait for flight/hotel/activity searches before persisting. The user
  must see something in the panel immediately.

  Minimum required structure for each day:
    {{"day": 1, "date": "YYYY-MM-DD", "title": "Day 1 · Arrival",
      "summary": "Arrive, check in, explore the old town.",
      "stops": [
        {{"name": "Hotel Name", "kind": "hotel"}},
        {{"name": "Attraction Name", "kind": "attraction", "time": "15:00"}}
      ]}}

  Then continue to STEP 3 to validate and enrich with real options.

STEP 3 — PARALLEL SEARCH (do all at once)
  Call these tools in parallel based on preferences:
    a) search_flights_duffel — preferred provider-neutral flight search. It uses
      LiteAPI when configured, otherwise Duffel. Real airlines, times, stops,
      prices, and quote evidence. Before describing a selected LiteAPI offer as
      current, call verify_flight_offer and persist the verified normalized offer
      including provider_ref, quoted_at, expires_at, and status. Only fall back to
      search_flights (Amadeus) if the preferred search returns nothing useful.
  b) search_hotels — real hotels with names, ratings, prices (Amadeus pricing)
  c) search_places_with_reviews — Google ratings/reviews for shortlisted hotels
     and attractions. ALWAYS run this on any hotel before recommending it.
  d) search_activities — sightseeing, tours, attraction tickets with prices
  e) nearby_restaurants — top-rated restaurants near the hotel matching dietary needs
  f) web_search — fresh travel guides, recent reviews, seasonal advice when
     structured APIs don't cover it (e.g. "is Goa safe in monsoon?")

    HOTEL COMPLETION GATE: unless the user explicitly asks to compare hotel
    options before choosing, select the strongest preference-matched real hotel
    from the search results as the default in this same turn. Persist it in
    selected_hotels, including the result's destination/address evidence, and
    replace every placeholder hotel in day_wise_itinerary. The selected hotel's
    location MUST match the active trip destination; never substitute a similarly
    named or more luxurious property in another city or country.
    Never persist "Hotel (TBD)", a generic accommodation label, or an invented
    hotel price as a selected hotel. If update_trip_plan reports "Hotel planning
    incomplete", search, choose, verify, and update again before the final reply.

  Present results in a clean summary:
  ┌──────────────────────────────────────────────┐
  │ ✈️ FLIGHTS: top 3-5 options                  │
  │ 🏨 HOTELS: top 3-5 with Google rating + price│
  │ 🍽️ RESTAURANTS: 5-8 rated 4.0+ near hotel    │
  │ 🎯 ACTIVITIES: top 5-10 options              │
  │ 💰 COST ESTIMATE: total per person           │
  └──────────────────────────────────────────────┘

  Before the final response, persist a SECOND, enriched full-plan update using
  the research results. Replace first-cut assumptions and every placeholder,
  select the strongest verified hotel by default, add concrete activities and
  named meals, and retain useful costs/route context. Do not leave research only
  in chat while the workspace still shows the rough first cut.

STEP 4 — BUILD ITINERARY
  Using the preferences (trip_style, family, dietary needs), build a day-by-day
  itinerary that includes:
  - Morning / afternoon / evening activities
  - Specific restaurant recommendations (matching dietary prefs)
  - RESTAURANT COMPLETION GATE: after nearby_restaurants returns, choose concrete
    named restaurants and persist them as kind "meal" stops in
    day_wise_itinerary. Never leave "TBD", "Lunch stop", "Dinner stop", or a
    generic restaurant placeholder. Every day with 2+ activities needs at least
    one named restaurant unless the user explicitly asks to leave meals open.
    If update_trip_plan reports "Restaurant planning incomplete", correct the
    itinerary and call update_trip_plan again before writing the final reply.
  - Travel time between spots — call compute_route (Google Routes API) for any
    day with 3+ stops so transitions show REAL minutes/km, e.g. "Hotel →
    Louvre: 22m walk, 1.8 km". Don't guess.
  - Use optimize_day_route when the user has a bag of attractions to pack
    into one day and the visit order isn't fixed — it reshuffles intermediate
    stops to minimize total travel time (first + last stay pinned).
  - Opening hours: before pinning any museum / monument / restaurant to a
    specific day & time slot, call check_place_hours(place_id, when_iso) —
    catches "Louvre on Tuesday" or "that bistro is closed Sunday lunch" type
    mistakes. Skip for hotels and open-air spots.
  - Weather & packing: always call get_weather_forecast(destination, start, end)
    once per trip. Use the per-day highs / lows / precipitation to:
      • Swap outdoor plans for indoor on heavy-rain days
      • Build the packing list with REAL numbers ("Goa Jul 12-18 → daily highs
        29-31°C, rain 4/7 days → quick-dry rain jacket + sandals")
    Persist the tool's complete normalized result in update_trip_plan under
    "weather", adding a concise "packing_advice" string list when useful.
    If the source is "seasonal_estimate" (trip > 16 days out), label the
    weather section "typical for this season" rather than "forecast".
    If Open-Meteo fails completely, use your general monthly climate knowledge
    to persist weather with source "agent_climate_estimate", one entry per trip
    date, and a note that live weather was unavailable. Never call that a forecast.
  - Visa & entry rules: for any international trip call
    check_visa_requirements(passport_country, destination_country, purpose,
    days). Surface visa-required / visa-on-arrival / e-visa status, the
    typical processing time, and ALWAYS the official-source link from the
    response. Skip for purely domestic trips.
  - Local events / festivals / holidays: call
    find_local_events(destination, start, end) once per trip. Flag any festival,
    parade, marathon, or public holiday overlapping the trip. Reasons:
      • Holidays may close museums & shift restaurant hours
      • Festivals may surge hotel prices or be the highlight of the trip
      • Marathons / parades can break the day's transit plan
  - Which attraction tickets to pre-book
  - Local transport within the destination
  - Cost per day

  When you write each day's entry in day_wise_itinerary, give it this STRUCTURED
  shape so the UI can pin, route, load photos for, and track booking of each
  place precisely:
    {{"day": 2, "date": "2026-01-12", "title": "Old Goa & beaches",
      "summary": "short prose recap of the day",
      "stops": [
        {{"name": "Taj Exotica Resort", "kind": "hotel",
          "note": "start from the hotel"}},
        {{"name": "Basilica of Bom Jesus", "kind": "attraction",
          "time": "09:30", "duration_min": 90, "note": "go early, fewer crowds"}},
        {{"name": "Taj Exotica Resort", "kind": "hotel",
          "note": "return to the hotel"}}
      ]}}
  - "stops" is an ORDERED list of the specific places visited that day. Each
    stop is an object with: name (REQUIRED, must match the hotels/attractions
    you selected), kind (one of: hotel, attraction, meal, transport, flight,
    other), and optionally time ("HH:MM"), duration_min (int), note (short).
    For a flight, time is the scheduled departure and arrival_time ("HH:MM")
    is required; use the flight's real local airport times and duration_min.
  - Visit times MUST strictly increase in the same order as the stops array and
    leave enough room for each stop's duration plus travel to the next place.
    Never give two visits the same time. After optimize_day_route or any route
    change, recompute every affected time before calling update_trip_plan. If
    update_trip_plan rejects itinerary chronology, resubmit the full corrected
    day_wise_itinerary before replying.
  - Every ordinary sightseeing day MUST start at that night's hotel and end at
    the same hotel. For a stay-transfer day, start at the old hotel and end at
    the new hotel. Do not add a hotel return after an overnight flight, train,
    or bus; preserve the actual overnight endpoint instead.
  - A trip whose origin differs from its destination MUST include the complete
    round trip in day_wise_itinerary. On the arrival day, put the flight or a
    named road, bus, or train stop before destination check-in. On the departure
    day, put the return journey after checkout. For nearby trips such as
    Bangalore to Mysore, choose a sensible ground mode from preferences and name
    both endpoints (for example, "Train: Bangalore to Mysore" and "Train: Mysore
    to Bangalore"). A local taxi or destination transfer does not replace these
    inter-city edges. Name road journeys "Drive: origin to destination", use the
    saved home area as the origin when known, and include realistic snack/rest
    breaks in duration_min using the saved road-break cadence. Persist route
    duration/distance when grounded evidence is available.
  - Keep a "summary" (prose) per day for readability; "title" is a short label.
  - When a stop becomes actually booked (after execute_bookings), set its
    "booked": true so the UI shows it checked off.
  - Plain string stops (["Taj Mahal", "Agra Fort"]) still work but are matched
    less reliably and carry no times — prefer the structured objects above.

  Update the trip plan with update_trip_plan.

  !! MANDATORY — ITINERARY PANEL WILL STAY BLANK OTHERWISE !!
  Presenting the day-by-day plan in chat is NOT enough. You MUST call
  update_trip_plan with the full day_wise_itinerary in the SAME turn you
  describe the plan. Call the tool BEFORE writing the chat reply so the
  panel updates as the user reads your message. Re-send the updated
  day_wise_itinerary whenever the user changes even one day.

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

STEP 7b — POST-TRIP REFLECTION (when user reports back)
  When the user returns and shares feedback ("Goa was great, kids loved the
  beach", "Paris hotel was disappointing", "next time book direct flights"),
  call record_trip_postmortem(destination, rating=1-5, what_worked=...,
  what_didnt=...) so the lesson is captured into BOTH past_trips AND
  learned_notes. Semicolon-separate the bullets ("private guide; rooftop bar"
  / "morning flight; airport hotel"). Future planning sessions will recall
  these via memory_recall and bias suggestions accordingly.

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

TRIP-SCOPED EXCEPTIONS (never pollute durable preferences):
- When the user frames something as a ONE-OFF ("just for this trip", "this
  time", "for now", "I'll make an exception", "only this once"), it is NOT a
  durable preference. Record it via update_trip_plan with a "trip_constraints"
  list entry (e.g. "3-star hotel is fine just this trip" or "OK with one
  connection this time"). NEVER call save_travel_preferences,
  update_user_profile, or add_user_* for a one-off. This keeps the user from
  being permanently tagged (e.g. assuming they always want 3-star hotels).
- Only durable cues ("I always", "I prefer", "as a rule", "generally", "I
  hate") belong in saved preferences.

CONFIRMATION (build trust, allow corrections):
- After extracting, give ONE SHORT acknowledgement at the end of your reply:
  "Got it — I've noted you're in Bengaluru, traveling with Priya and your son."
  Keep it to one line so the user can correct in one breath.

9. ITINERARY PANEL SYNC — every time you write a day-wise itinerary in chat
   you MUST call update_trip_plan with the full day_wise_itinerary in the
   SAME turn. This applies to first drafts (STEP 2.5) AND final plans
   (STEP 4) AND any single-day edit. The tool call must come BEFORE the chat
   reply so the panel is ready when the user reads your message.
   Non-negotiable: if you skip this call, the Itinerary panel stays blank
   regardless of how detailed your chat text is.

SOURCE TAGGING:
- For remember_about_user and record_trip_mention, use source="stated" when
  the user said it explicitly, "inferred" when you deduced it from their
  choices (e.g. they keep rejecting chain hotels → infer "prefers boutique").

═══════════════════════════════════════════════════════════════
CRITICAL RULES:
═══════════════════════════════════════════════════════════════
1. BE PROACTIVE — don't ask 20 questions. For a new trip, present the single
  pre-filled preference-aware kickoff, then use saved preferences + past trips
  to generate a near-final plan immediately. Do not ask follow-up questions in
  direct mode; infer and proceed after the kickoff.
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
8. CURRENCY — pick ONE display currency at the start of the plan and use it
   for EVERY amount in the whole conversation (flights, hotels, activities,
   day costs, final total). Choose it like this:
     • DOMESTIC trip (destination in the user's home country): use the HOME
       currency from profile.home_country (India → INR ₹, USA → USD $,
       UK → GBP £, UAE → AED, etc.; default INR ₹ when unknown).
     • INTERNATIONAL trip: use whichever currency makes the MOST sense for the
       user — typically USD ($) as a universal reference, or the destination's
       local currency when that's clearer (e.g. EUR € for Europe, THB ฿ for
       Thailand, AED for Dubai). Pick the one that's easiest for the user to
       reason about, and you may also show the home-currency equivalent in
       parentheses (e.g. "$1,200 (~₹1,00,000)").
   This is STICKY: once chosen, never silently switch currencies mid-plan or
   between turns. If a search API returns a different currency (e.g. Duffel in
   USD), convert to your chosen display currency and show that as the primary
   figure. State the chosen currency once up front so the user knows.
   Persist it once via update_trip_plan('{{"currency": "USD"}}') (ISO code) so
   every surface — including the budget meter — renders the same symbol.
"""


def build_trip_system_prompt(today: date | None = None) -> SystemMessage:
    """Construct the trip planner system prompt with today's date injected.

    Called per-request from the graph so the LLM always sees the current date.
    """
    today = today or datetime.now(timezone.utc).date()
    default_start = today + timedelta(weeks=4)
    content = _PROMPT_TEMPLATE.format(
        today_iso=today.isoformat(),
        today_human=today.strftime("%A, %d %B %Y"),
        year=today.year,
        next_year=today.year + 1,
        month_name=today.strftime("%B"),
        min_trip_start=(today + timedelta(days=7)).isoformat(),
        default_start=default_start.isoformat(),
    )
    return SystemMessage(content=content)


# Back-compat: importers that still grab TRIP_SYSTEM_PROMPT get a snapshot
# built at import time. Prefer build_trip_system_prompt() for live agents.
TRIP_SYSTEM_PROMPT = build_trip_system_prompt()

# ---------------------------------------------------------------------------
# Tool groups — so the graph can bind only the relevant subset per turn.
# Binding all schemas every call is a large fixed prompt-token tax; the heavy
# search/enrichment tools are dead weight until there's a destination to plan.
# ---------------------------------------------------------------------------

# Always bound: cheap, fire on most turns (preference extraction, memory recall,
# and the plan lifecycle the agent uses to bootstrap a trip).
_CORE_TOOLS = [
    # Preferences
    get_travel_preferences,
    save_travel_preferences,
    record_past_trip,
    record_trip_postmortem,
    remember_about_user,
    # Continuous learning (extract during natural conversation)
    update_user_profile,
    add_family_member,
    add_user_interest,
    add_user_dislike,
    record_trip_mention,
    # One bounded, prefilled clarification for interactive planning mode
    request_trip_input,
    # Explainable trip length and daily-capacity advice before plan creation
    recommend_trip_duration,
    # Semantic-ish recall over the user's persistent memory (BM25-lite, no API)
    recall_relevant_memory,
    # Trip plan management
    create_trip_plan,
    get_trip_plan,
    update_trip_plan,
    finalize_trip,
    execute_bookings,
    list_past_trips,
    resume_trip,
]

# Heavy search / enrichment — only bound once planning is active (a destination
# exists or the user asked to plan). Self-healing: if missed on the turn a plan
# is created, the graph loops back and re-selects with the trip now present.
_SEARCH_TOOLS = [
    # Flights — Duffel preferred, Amadeus kept as fallback (deprecating 2026-07-17)
    search_flights_duffel,
    verify_flight_offer,
    search_flights,
    # Real search (Amadeus — bookable inventory)
    search_hotels,
    search_activities,
    search_points_of_interest,
    # Ratings & reviews (Google Places)
    search_places_with_reviews,
    get_place_reviews,
    nearby_restaurants,
    check_place_hours,
    # Routing & travel time (Google Routes API)
    compute_route,
    optimize_day_route,
    # Weather + packing (Open-Meteo, no key)
    get_weather_forecast,
    # Visa & entry rules (Tavily-backed, prefers .gov / IATA)
    check_visa_requirements,
    # Local events / festivals / public holidays (Tavily news)
    find_local_events,
    # Fresh web content (Tavily)
    web_search,
]

# Full union — kept for back-compat, tests, and the graph's ToolNode (which
# must be able to EXECUTE any tool the model calls, regardless of what was
# bound for schema purposes).
TRIP_TOOLS = _CORE_TOOLS + _SEARCH_TOOLS

_MUTATING_TOOL_NAMES = {
  "create_trip_plan",
  "update_trip_plan",
  "finalize_trip",
  "execute_bookings",
  "resume_trip",
  "save_travel_preferences",
  "record_past_trip",
  "record_trip_postmortem",
  "remember_about_user",
  "update_user_profile",
  "add_family_member",
  "add_user_interest",
  "add_user_dislike",
  "record_trip_mention",
}


def proposal_tools(tools: list) -> list:
  return [tool for tool in tools if tool.name not in _MUTATING_TOOL_NAMES]

# Tool calls that signal a planning session is under way.
_PLANNING_TRIGGER_TOOLS = {
    "create_trip_plan", "get_trip_plan", "update_trip_plan", "finalize_trip",
    "execute_bookings", "resume_trip", "list_past_trips",
    "search_flights_duffel", "verify_flight_offer", "search_flights", "search_hotels",
    "search_activities", "search_points_of_interest",
    "search_places_with_reviews", "get_place_reviews", "nearby_restaurants",
    "check_place_hours", "compute_route", "optimize_day_route",
    "get_weather_forecast", "check_visa_requirements", "find_local_events",
}

_PLANNING_INTENT_RE = re.compile(
    r"\b(plan|trip|travel|holiday|vacation|flight|flights|hotel|hotels|"
    r"itinerary|itineraries|visit|getaway|weekend|honeymoon|tour|fly|stay|book|"
    r"days?\s+in|go\s+to)\b",
    re.I,
)


def _planning_active(messages: list) -> bool:
    """True when the heavy search tools should be bound this turn."""
    # 1. An active trip with a destination already exists (covers cross-turn
    #    sessions where the create_trip_plan call has scrolled out of history).
    try:
        trip = _load_active_trip()
        if isinstance(trip, dict) and trip.get("destination"):
            return True
    except Exception:
        pass
    # 2. A planning/search tool was already called earlier in this exchange.
    for m in messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name in _PLANNING_TRIGGER_TOOLS:
                return True
    # 3. The latest user message expresses planning intent.
    if latest_user_has_planning_intent(messages):
        return True
    return False


def latest_user_has_planning_intent(messages: list) -> bool:
    """Return whether the latest user message expresses trip-planning intent."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return bool(_PLANNING_INTENT_RE.search(str(message.content or "")))
    return False


def select_tools(messages: list, *, proposal_only: bool = False) -> list:
    """Return the tool subset to bind for this turn.

    Core preference/lifecycle tools are always bound; the heavy search tools are
    added only once a planning session is active — cutting per-turn prompt
    tokens during greetings and preference gathering.
    """
    tools = _CORE_TOOLS + _SEARCH_TOOLS if _planning_active(messages) else list(_CORE_TOOLS)
    return proposal_tools(tools) if proposal_only else tools

