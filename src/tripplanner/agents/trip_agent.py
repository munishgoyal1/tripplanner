"""Trip Planner Agent — full-service trip planning with real search, bookings & preferences."""

from __future__ import annotations

import json
import re
from enum import StrEnum

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from tripplanner.chat_interactions import request_trip_input
from tripplanner.prompts import TRIP_SYSTEM_PROMPT, build_trip_system_prompt  # noqa: F401
from tripplanner.tools.activities_search import search_activities, search_points_of_interest
from tripplanner.tools.duffel_flights import search_flights_duffel, verify_flight_offer
from tripplanner.tools.events import find_local_events
from tripplanner.tools.flight_search import search_flights
from tripplanner.tools.google_places import (
    get_place_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from tripplanner.tools.ground_transport import search_coaches, search_ferries, search_trains
from tripplanner.tools.hotel_search import search_hotels
from tripplanner.tools.memory_recall import recall_relevant_memory
from tripplanner.tools.place_hours import check_place_hours
from tripplanner.tools.routing import compute_route, optimize_day_route
from tripplanner.tools.transport_compare import compare_transport_options
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
    prefs.pop("_learning_pending", None)
    prefs.pop("_learning_processed", None)
    prefs.pop("_learning_sequence", None)
    prefs.pop("_learned_field_versions", None)
    prefs.pop("profile_updates", None)
    prefs["configured_preference_fields"] = sorted(
        str(field) for field in prefs.get("_explicit_fields") or []
    )
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
    passport_country: str | None = None,
    age_band: str | None = None,
    occupation: str | None = None,
) -> str:
    """Save basic profile facts about the user.

    Call this as soon as you learn the user's name, city, country, passport,
    age band, or occupation. Pass ONLY the fields you just learned (others stay
    unchanged). Examples:
      - User: "I'm Munish from Bengaluru" → update_user_profile(display_name="Munish", home_city="Bengaluru", home_country="India")
      - User: "I'm a doctor" → update_user_profile(occupation="doctor")
      - User: "I travel on my British passport" → update_user_profile(passport_country="British")

    Args:
        display_name: First name or how the user introduces themselves.
        home_city: City of residence (e.g. "Bengaluru").
        home_country: Country of residence (e.g. "India").
        passport_country: Passport they travel on (e.g. "Indian"). Save this
            ONLY when the user states it — never infer it from where they live.
        age_band: One of "20-30", "30-40", "40-50", "50-60", "60+".
        occupation: Free-form (e.g. "software engineer", "retired teacher").
    """
    update_profile({
        "display_name": display_name,
        "home_city": home_city,
        "home_country": home_country,
        "passport_country": passport_country,
        "age_band": age_band,
        "occupation": occupation,
    })
    saved = {k: v for k, v in {
        "display_name": display_name,
        "home_city": home_city,
        "home_country": home_country,
        "passport_country": passport_country,
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
    # Ground transportation (trains, coaches, ferries)
    search_trains,
    search_coaches,
    search_ferries,
    # Ratings & reviews (Google Places)
    search_places_with_reviews,
    get_place_reviews,
    nearby_restaurants,
    check_place_hours,
    # Routing & travel time (Google Routes API)
    compute_route,
    optimize_day_route,
    # Mode comparison for one intercity hop — records the decision on the trip
    compare_transport_options,
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

class ToolCapability(StrEnum):
  READ = "read"
  TRIP_WRITE = "trip_write"
  PROFILE_WRITE = "profile_write"
  EXTERNAL_WRITE = "external_write"


_READ_TOOLS = [
  get_travel_preferences,
  request_trip_input,
  recommend_trip_duration,
  recall_relevant_memory,
  get_trip_plan,
  list_past_trips,
  *[tool for tool in _SEARCH_TOOLS if tool is not compare_transport_options],
]
_TRIP_WRITE_TOOLS = [
  create_trip_plan,
  update_trip_plan,
  finalize_trip,
  resume_trip,
  compare_transport_options,
]
_PROFILE_WRITE_TOOLS = [
  save_travel_preferences,
  record_past_trip,
  record_trip_postmortem,
  remember_about_user,
  update_user_profile,
  add_family_member,
  add_user_interest,
  add_user_dislike,
  record_trip_mention,
]
_EXTERNAL_WRITE_TOOLS = [execute_bookings]


def _build_tool_capabilities() -> dict[str, ToolCapability]:
  groups = {
    ToolCapability.READ: _READ_TOOLS,
    ToolCapability.TRIP_WRITE: _TRIP_WRITE_TOOLS,
    ToolCapability.PROFILE_WRITE: _PROFILE_WRITE_TOOLS,
    ToolCapability.EXTERNAL_WRITE: _EXTERNAL_WRITE_TOOLS,
  }
  classified: dict[str, ToolCapability] = {}
  for capability, tools in groups.items():
    for candidate in tools:
      if candidate.name in classified:
        raise RuntimeError(f"Tool {candidate.name!r} has more than one capability")
      classified[candidate.name] = capability
  missing = {tool.name for tool in TRIP_TOOLS} - classified.keys()
  extra = classified.keys() - {tool.name for tool in TRIP_TOOLS}
  if missing or extra:
    raise RuntimeError(
      f"Tool capability registry mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
    )
  return classified


TOOL_CAPABILITIES = _build_tool_capabilities()


def tool_capability(tool: object) -> ToolCapability:
  name = str(getattr(tool, "name", ""))
  try:
    return TOOL_CAPABILITIES[name]
  except KeyError as exc:
    raise RuntimeError(f"Tool {name or tool!r} has no declared capability") from exc


def proposal_tools(tools: list) -> list:
    return [tool for tool in tools if tool_capability(tool) is ToolCapability.READ]

# Tool calls that signal a planning session is under way.
_PLANNING_TRIGGER_TOOLS = {
    "create_trip_plan", "get_trip_plan", "update_trip_plan", "finalize_trip",
    "execute_bookings", "resume_trip", "list_past_trips",
    "search_flights_duffel", "verify_flight_offer", "search_flights", "search_hotels",
    "search_activities", "search_points_of_interest",
    "search_trains", "search_coaches", "search_ferries",
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
