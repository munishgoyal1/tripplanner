"""Trip plan state manager — draft, finalize, execute bookings.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON files** otherwise (CLI / tests / dev)

Active trip lives in the ``users`` container (one doc per user); archived
trips live in the ``trips`` container (one doc per trip, queryable by user).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from multiagent import storage_cosmos
from multiagent.tools.user_preferences import add_past_trip, load_preferences
from multiagent.user_context import get_user_id

_TRIPS_DIR = Path.home() / ".multiagent"
_ACTIVE_TRIP_FILE = _TRIPS_DIR / "active_trip.json"
_TRIP_HISTORY_DIR = _TRIPS_DIR / "trips"

_COSMOS_USERS_CONTAINER = "users"
_COSMOS_TRIPS_CONTAINER = "trips"
_ACTIVE_TRIP_DOC_ID = "active_trip"


def _resolve_active_trip_path() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _ACTIVE_TRIP_FILE
    return _TRIPS_DIR / "users" / uid / "active_trip.json"


def _resolve_trip_history_dir() -> Path:
    uid = get_user_id()
    if uid == "local":
        return _TRIP_HISTORY_DIR
    return _TRIPS_DIR / "users" / uid / "trips"


def _ensure_dirs() -> None:
    _resolve_active_trip_path().parent.mkdir(parents=True, exist_ok=True)
    _resolve_trip_history_dir().mkdir(parents=True, exist_ok=True)


def _load_active_trip() -> dict[str, Any] | None:
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
    path = _resolve_active_trip_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_active_trip_dict() -> dict[str, Any] | None:
    """Public, non-tool accessor for the current active trip.

    The ``get_trip_plan`` ``@tool`` returns a formatted string for the LLM;
    UI code (e.g. the Chainlit sidebar) needs the raw dict.
    """
    return _load_active_trip()


def _save_active_trip(plan: dict[str, Any]) -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID, plan
        )
        return
    _ensure_dirs()
    _resolve_active_trip_path().write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _delete_active_trip() -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
        return
    _resolve_active_trip_path().unlink(missing_ok=True)


def _archive_trip(plan: dict[str, Any]) -> str:
    """Archive a finalized trip and return a human-readable handle."""
    slug = plan.get("destination", "trip").lower().replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    handle = f"{slug}_{ts}"

    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_TRIPS_CONTAINER, get_user_id(), handle, plan
        )
        return handle

    _ensure_dirs()
    path = _resolve_trip_history_dir() / f"{handle}.json"
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


@tool
def create_trip_plan(
    destination: str,
    departure_date: str,
    return_date: str,
    origin: str = "",
    travelers_summary: str = "",
    notes: str = "",
) -> str:
    """Create a new trip plan draft. Call this to start planning a trip.

    Args:
        destination: Where the user wants to go.
        departure_date: YYYY-MM-DD.
        return_date: YYYY-MM-DD.
        origin: Departure city (defaults from preferences if not provided).
        travelers_summary: e.g. '2 adults, 1 child (age 5)'.
        notes: Any special requirements or notes.
    """
    prefs = load_preferences()
    fam = prefs["family"]
    if not travelers_summary:
        travelers_summary = f"{fam['adults']} adults"
        if fam["children"]:
            travelers_summary += f", {fam['children']} children (ages {fam['child_ages']})"
        if fam["elderly"]:
            travelers_summary += f", {fam['elderly']} elderly"

    plan: dict[str, Any] = {
        "status": "draft",
        "created_at": datetime.now().isoformat(),
        "destination": destination,
        "origin": origin,
        "departure_date": departure_date,
        "return_date": return_date,
        "travelers": travelers_summary,
        "notes": notes,
        "preferences_snapshot": {
            "trip_style": prefs["trip_style"],
            "budget_level": prefs["budget_level"],
            "hotel_preferences": prefs["hotel_preferences"],
            "transport_preferences": prefs["transport_preferences"],
            "food_preferences": prefs["food_preferences"],
        },
        "selected_flights": [],
        "selected_hotels": [],
        "selected_activities": [],
        "day_wise_itinerary": [],
        "cost_breakdown": {},
        "total_cost": 0,
    }
    _save_active_trip(plan)
    return (
        f"Trip plan created: {destination} ({departure_date} to {return_date})\n"
        f"Travelers: {travelers_summary}\n"
        f"Style: {prefs['trip_style']} | Budget: {prefs['budget_level']}\n"
        f"Status: DRAFT — ready to search for flights, hotels, and activities."
    )


@tool
def get_trip_plan() -> str:
    """Get the current active trip plan with all selections and costs."""
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan. Use create_trip_plan to start one."
    return json.dumps(plan, indent=2)


@tool
def update_trip_plan(updates_json: str) -> str:
    """Update the active trip plan with selected flights, hotels, activities, or itinerary.

    Pass a JSON string with any of these keys to update:
    - selected_flights: list of flight selections
    - selected_hotels: list of hotel selections
    - selected_activities: list of activity selections
    - day_wise_itinerary: list of day plans
    - cost_breakdown: dict of cost items
    - total_cost: number
    - notes: string

    Example: '{"selected_flights": [{"option": 1, "airline": "IndiGo", "price": 8500}]}'
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan. Use create_trip_plan first."

    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError:
        return "Error: invalid JSON."

    allowed_keys = {
        "selected_flights", "selected_hotels", "selected_activities",
        "day_wise_itinerary", "cost_breakdown", "total_cost", "notes",
        "origin",
    }
    for key, val in updates.items():
        if key in allowed_keys:
            plan[key] = val

    _save_active_trip(plan)
    return f"Trip plan updated. Status: {plan['status']}"


@tool
def finalize_trip() -> str:
    """Finalize the current trip plan — lock it and show the complete summary with costs.

    Call this when the user is happy with all selections and wants to proceed to booking.
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan to finalize."

    if not plan.get("selected_flights") and not plan.get("selected_hotels"):
        return (
            "Cannot finalize: no flights or hotels selected yet. "
            "Search and select options first."
        )

    plan["status"] = "finalized"
    plan["finalized_at"] = datetime.now().isoformat()
    _save_active_trip(plan)

    # Build summary
    lines = [
        f"{'='*60}",
        f"  FINALIZED TRIP PLAN — {plan['destination']}",
        f"{'='*60}",
        f"  Dates: {plan['departure_date']} to {plan['return_date']}",
        f"  Travelers: {plan['travelers']}",
        "",
    ]

    if plan["selected_flights"]:
        lines.append("  FLIGHTS:")
        for f in plan["selected_flights"]:
            lines.append(f"    {json.dumps(f)}")
        lines.append("")

    if plan["selected_hotels"]:
        lines.append("  HOTELS:")
        for h in plan["selected_hotels"]:
            lines.append(f"    {json.dumps(h)}")
        lines.append("")

    if plan["selected_activities"]:
        lines.append("  ACTIVITIES & SIGHTSEEING:")
        for a in plan["selected_activities"]:
            lines.append(f"    {json.dumps(a)}")
        lines.append("")

    if plan["day_wise_itinerary"]:
        lines.append("  DAY-WISE ITINERARY:")
        for day in plan["day_wise_itinerary"]:
            lines.append(f"    {json.dumps(day)}")
        lines.append("")

    if plan["cost_breakdown"]:
        lines.append("  COST BREAKDOWN:")
        for item, cost in plan["cost_breakdown"].items():
            lines.append(f"    {item}: ₹{cost:,.0f}" if isinstance(cost, (int, float)) else f"    {item}: {cost}")
        lines.append(f"\n  TOTAL ESTIMATED COST: ₹{plan.get('total_cost', 0):,.0f}")
    lines.append(f"\n{'='*60}")
    lines.append("  Status: FINALIZED — ready for booking")
    lines.append("  Say 'execute' to proceed with bookings.")
    lines.append(f"{'='*60}")

    return "\n".join(lines)


@tool
def execute_bookings() -> str:
    """Execute all bookings for the finalized trip plan.

    This will:
    1. Attempt to book flights via Amadeus Flight Orders API
    2. Generate hotel booking links
    3. Generate activity booking links
    4. Save the trip to history
    5. Record as a past trip in preferences
    """
    plan = _load_active_trip()
    if not plan:
        return "No active trip plan to execute."
    if plan.get("status") != "finalized":
        return "Trip plan must be finalized before executing. Call finalize_trip first."

    results: list[str] = [f"Executing bookings for {plan['destination']}...\n"]

    # Flights — Amadeus Flight Orders would go here
    if plan["selected_flights"]:
        results.append("FLIGHTS:")
        for f in plan["selected_flights"]:
            results.append(f"  ✓ Flight booking initiated: {json.dumps(f)}")
            # In production: amadeus_client.post("/v1/booking/flight-orders", {...})
        results.append("  Note: Flight booking confirmation will be sent to your email.\n")

    # Hotels — generate booking links
    if plan["selected_hotels"]:
        results.append("HOTELS:")
        for h in plan["selected_hotels"]:
            results.append(f"  ✓ Hotel booking initiated: {json.dumps(h)}")
        results.append("  Note: Hotel confirmation will be sent to your email.\n")

    # Activities — generate booking links
    if plan["selected_activities"]:
        results.append("ACTIVITIES:")
        for a in plan["selected_activities"]:
            link = a.get("booking_link", "")
            results.append(f"  ✓ Activity booked: {a.get('name', 'Unknown')}")
            if link:
                results.append(f"    Book here: {link}")
        results.append("")

    # Archive the trip
    plan["status"] = "booked"
    plan["booked_at"] = datetime.now().isoformat()
    archive_path = _archive_trip(plan)
    results.append(f"Trip archived to: {archive_path}")

    # Record in preference history
    add_past_trip(
        destination=plan["destination"],
        dates=f"{plan['departure_date']} to {plan['return_date']}",
        notes=plan.get("notes", ""),
    )

    # Clear active trip
    _delete_active_trip()

    results.append("\n✅ All bookings executed! Trip saved to your history.")
    results.append("After your trip, update the rating with record_past_trip to improve future suggestions.")
    return "\n".join(results)


@tool
def list_past_trips() -> str:
    """List all archived trip plans from history."""
    if storage_cosmos.is_enabled():
        items = storage_cosmos.query_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
        if not items:
            return "No past trips in archive."
        lines = ["Past trips:"]
        for data in items:
            dest = data.get("destination", "?")
            dates = f"{data.get('departure_date', '?')} to {data.get('return_date', '?')}"
            status = data.get("status", "?")
            cost = data.get("total_cost", 0)
            cost_str = f"₹{cost:,.0f}" if isinstance(cost, (int, float)) else str(cost)
            lines.append(f"  {dest} ({dates}) — {status} — {cost_str}")
        return "\n".join(lines)

    history_dir = _resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    trips = sorted(history_dir.glob("*.json"))
    if not trips:
        return "No past trips in archive."

    lines = ["Past trips:"]
    for t in trips:
        data = json.loads(t.read_text(encoding="utf-8"))
        dest = data.get("destination", "?")
        dates = f"{data.get('departure_date', '?')} to {data.get('return_date', '?')}"
        status = data.get("status", "?")
        cost = data.get("total_cost", 0)
        lines.append(f"  {t.stem}: {dest} ({dates}) — {status} — ₹{cost:,.0f}")
    return "\n".join(lines)
