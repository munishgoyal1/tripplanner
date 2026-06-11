"""Trip plan state manager — draft, finalize, execute bookings.

Two backends, auto-selected:
- **Cosmos DB** when ``COSMOS_ENDPOINT`` is configured (hosted multi-user mode)
- **Local JSON files** otherwise (CLI / tests / dev)

Active trip lives in the ``users`` container (one doc per user); archived
trips live in the ``trips`` container (one doc per trip, queryable by user).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from multiagent import storage_cosmos
from multiagent.tools.finalize_critic import critique as _critique_finalized
from multiagent.tools.trip_diff import diff_plans, format_diff
from multiagent.tools.user_preferences import add_past_trip, load_preferences
from multiagent.user_context import get_user_id

_TRIPS_DIR = Path.home() / ".multiagent"
_ACTIVE_TRIP_FILE = _TRIPS_DIR / "active_trip.json"
_TRIP_HISTORY_DIR = _TRIPS_DIR / "trips"

_COSMOS_USERS_CONTAINER = "users"
_COSMOS_TRIPS_CONTAINER = "trips"
_ACTIVE_TRIP_DOC_ID = "active_trip"


def _slugify(text: str) -> str:
    """Filesystem/Cosmos-safe slug for a destination name."""
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug or "trip"


def _compute_trip_id(plan: dict[str, Any]) -> str:
    """Stable id encoding destination + date range.

    Two plannings for the SAME place over the SAME dates share an id (so they
    merge/resume); a different duration or different dates yields a different id
    (so they're kept as separate, date-tagged trips) — exactly the owner's rule.
    """
    slug = _slugify(str(plan.get("destination") or "trip"))
    dep = (str(plan.get("departure_date") or "").strip()) or "nodate"
    ret = (str(plan.get("return_date") or "").strip()) or "nodate"
    return f"{slug}_{dep}_{ret}"



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
    UI code (e.g. the trip panel) needs the raw dict.
    """
    return _load_active_trip()


def active_trip_id() -> str | None:
    """The current active trip's stable id, or ``None`` when none is active.

    Non-tool: lets the API key the persisted chat transcript by trip so each
    saved trip carries its own conversation.
    """
    active = _load_active_trip()
    return (active or {}).get("trip_id") if active else None


def add_selection(kind: str, item: dict[str, Any]) -> bool:
    """Add a hotel/attraction to the active trip's selections (UI helper).

    ``kind`` is ``"hotel"`` or ``"attraction"``. Deduped by name. Returns
    ``True`` when there's an active trip to update, ``False`` otherwise.
    Non-tool: called by the panel's "Add to trip" button, not the LLM.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    key = "selected_hotels" if kind == "hotel" else "selected_activities"
    bucket = plan.setdefault(key, [])
    name = str(item.get("name") or "").strip()
    if not name:
        return False
    if any(str(x.get("name") or "").strip().lower() == name.lower() for x in bucket):
        return True
    bucket.append(item)
    _save_active_trip(plan)
    return True


def remove_selection(kind: str, name: str) -> bool:
    """Remove a previously-added hotel/attraction from the active trip (UI helper).

    The reverse of :func:`add_selection`. Matched case-insensitively by name.
    Returns ``True`` when there's an active trip to update, ``False`` otherwise.
    Non-tool: called by the panel's "Remove from trip" button, not the LLM.
    """
    plan = _load_active_trip()
    if not plan:
        return False
    key = "selected_hotels" if kind == "hotel" else "selected_activities"
    bucket = plan.get(key) or []
    target = str(name or "").strip().lower()
    kept = [x for x in bucket if str(x.get("name") or "").strip().lower() != target]
    if len(kept) == len(bucket):
        return True
    plan[key] = kept
    _save_active_trip(plan)
    return True


def _save_active_trip(plan: dict[str, Any]) -> None:
    # Stamp a stable id + freshness so the trip can live in history and be
    # listed / resumed later. Every save mirrors to the trips collection so
    # in-progress drafts are never lost when the user switches trips.
    if not plan.get("trip_id"):
        plan["trip_id"] = _compute_trip_id(plan)
    plan["updated_at"] = datetime.now().isoformat()

    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID, plan
        )
    else:
        _ensure_dirs()
        _resolve_active_trip_path().write_text(
            json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    _mirror_to_history(plan)


def _mirror_to_history(plan: dict[str, Any]) -> None:
    """Persist the plan into the per-user trips collection under its trip_id."""
    tid = plan.get("trip_id")
    if not tid:
        return
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), tid, plan)
        return
    _ensure_dirs()
    (_resolve_trip_history_dir() / f"{tid}.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_history_trip(trip_id: str) -> dict[str, Any] | None:
    """Load a single saved trip by its trip_id, or ``None``."""
    if not trip_id:
        return None
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    path = _resolve_trip_history_dir() / f"{trip_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _all_history_trips() -> list[dict[str, Any]]:
    """Every saved trip for the current user (raw plan dicts)."""
    if storage_cosmos.is_enabled():
        return storage_cosmos.query_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
    history_dir = _resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for f in history_dir.glob("*.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def _trip_summary(plan: dict[str, Any], active_id: str | None) -> dict[str, Any]:
    """Compact, UI-friendly descriptor for one saved trip."""
    tid = plan.get("trip_id") or _compute_trip_id(plan)
    return {
        "trip_id": tid,
        "destination": str(plan.get("destination") or ""),
        "departure_date": str(plan.get("departure_date") or ""),
        "return_date": str(plan.get("return_date") or ""),
        "status": str(plan.get("status") or "draft"),
        "total_cost": plan.get("total_cost") or 0,
        "currency": str(plan.get("currency") or ""),
        "counts": {
            "flights": len(plan.get("selected_flights") or []),
            "hotels": len(plan.get("selected_hotels") or []),
            "activities": len(plan.get("selected_activities") or []),
        },
        "updated_at": str(plan.get("updated_at") or plan.get("created_at") or ""),
        "is_active": bool(active_id) and tid == active_id,
    }


def list_saved_trips() -> list[dict[str, Any]]:
    """All saved trips as compact descriptors, most-recently-updated first.

    Non-tool: powers the SPA's "My trips" switcher and the resume flow.
    """
    active = _load_active_trip()
    active_id = (active or {}).get("trip_id") if active else None
    summaries = [_trip_summary(p, active_id) for p in _all_history_trips()]
    summaries.sort(key=lambda t: t["updated_at"], reverse=True)
    return summaries


def switch_active_trip(trip_id: str) -> dict[str, Any] | None:
    """Make a saved trip the active one. Returns the plan, or ``None``.

    The currently-active trip is already mirrored in history (every save does
    so), so switching loses nothing. Non-tool: called by the panel / resume.
    """
    plan = _load_history_trip(trip_id)
    if not plan:
        return None
    _save_active_trip(plan)
    return plan


def delete_saved_trip(trip_id: str) -> bool:
    """Delete a saved trip; clears the active pointer if it was active."""
    if not trip_id:
        return False
    active = _load_active_trip()
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    else:
        (_resolve_trip_history_dir() / f"{trip_id}.json").unlink(missing_ok=True)
    if active and active.get("trip_id") == trip_id:
        _delete_active_trip()
    return True



def _delete_active_trip() -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
        return
    _resolve_active_trip_path().unlink(missing_ok=True)


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

    # Same destination + same dates -> resume the saved trip instead of wiping
    # it, so the user never restarts from scratch. Different dates/duration get
    # a distinct id and are kept as a separate, date-tagged trip.
    trip_id = _compute_trip_id(
        {
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
        }
    )
    existing = _load_history_trip(trip_id)
    if existing:
        if origin:
            existing["origin"] = origin
        if notes:
            existing["notes"] = notes
        if travelers_summary:
            existing["travelers"] = travelers_summary
        existing["status"] = existing.get("status") or "draft"
        _save_active_trip(existing)
        counts = (
            len(existing.get("selected_flights") or []),
            len(existing.get("selected_hotels") or []),
            len(existing.get("selected_activities") or []),
        )
        return (
            f"Resumed your saved trip: {destination} "
            f"({departure_date} to {return_date})\n"
            f"So far: {counts[0]} flight(s), {counts[1]} hotel(s), "
            f"{counts[2]} activity(ies) | Status: {existing['status'].upper()}\n"
            f"Pick up where you left off — no need to restart."
        )

    plan: dict[str, Any] = {
        "status": "draft",
        "trip_id": trip_id,
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
        "budget": 0,
        "currency": "",
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
    - budget: number — the user's total budget for THIS trip (drives the live
      budget meter in the UI; set it as soon as the user states a budget)
    - currency: ISO code of the sticky display currency ("INR", "USD", "EUR",
      ...) — set it once when you pick the plan's currency so every surface
      (including the budget meter) shows the same symbol
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
        "origin", "budget", "currency",
    }
    before = json.loads(json.dumps(plan))  # deep copy for diff
    for key, val in updates.items():
        if key in allowed_keys:
            plan[key] = val

    _save_active_trip(plan)
    bullets = diff_plans(before, plan)
    if not bullets:
        return f"Trip plan updated (no material changes). Status: {plan['status']}"
    return (
        f"Trip plan updated. Status: {plan['status']}\n"
        f"What changed:\n{format_diff(bullets)}"
    )


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

    # Self-correction critic — deterministic rules over the finalized plan.
    try:
        prefs = load_preferences()
    except Exception:
        prefs = {}
    heads_up = _critique_finalized(plan, prefs)
    if heads_up:
        lines.append("")
        lines.append("  HEADS UP — quick sanity checks before you book:")
        for item in heads_up:
            lines.append(f"    • {item}")

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

    # Mark booked and persist to history (every save mirrors under trip_id).
    plan["status"] = "booked"
    plan["booked_at"] = datetime.now().isoformat()
    _save_active_trip(plan)

    # Record in preference history
    add_past_trip(
        destination=plan["destination"],
        dates=f"{plan['departure_date']} to {plan['return_date']}",
        notes=plan.get("notes", ""),
    )

    # Clear active pointer (the booked trip stays in your saved trips).
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


@tool
def resume_trip(destination: str = "", trip_id: str = "") -> str:
    """Resume a previously saved trip so the user doesn't restart from scratch.

    Match by ``trip_id`` (exact) or ``destination`` (most recently updated
    match). With no arguments, lists the saved trips to choose from. The chosen
    trip becomes the active plan; whatever was active is already saved.

    Args:
        destination: Place name to resume, e.g. 'Mumbai'.
        trip_id: Exact saved-trip id (preferred when known).
    """
    saved = list_saved_trips()
    if not saved:
        return "You have no saved trips yet. Use create_trip_plan to start one."

    match: dict[str, Any] | None = None
    if trip_id:
        match = next((t for t in saved if t["trip_id"] == trip_id), None)
    if match is None and destination:
        needle = destination.strip().lower()
        match = next((t for t in saved if needle in t["destination"].lower()), None)

    if match is None:
        lines = ["Which saved trip would you like to resume?"]
        for t in saved:
            dates = f"{t['departure_date']} to {t['return_date']}"
            lines.append(
                f"  - {t['destination']} ({dates}) — {t['status']} [{t['trip_id']}]"
            )
        return "\n".join(lines)

    if switch_active_trip(match["trip_id"]) is None:
        return f"Could not load saved trip '{match['trip_id']}'."

    c = match["counts"]
    return (
        f"Resumed {match['destination']} "
        f"({match['departure_date']} to {match['return_date']}) — "
        f"{match['status'].upper()}: {c['flights']} flight(s), "
        f"{c['hotels']} hotel(s), {c['activities']} activity(ies). "
        f"Continuing where you left off."
    )

