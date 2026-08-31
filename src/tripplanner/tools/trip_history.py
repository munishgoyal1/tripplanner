"""Active and saved-trip persistence for the planner."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tripplanner import debug_store, storage_cosmos
from tripplanner.json_store import atomic_write_json
from tripplanner.user_context import get_user_id

_TRIPS_DIR = Path.home() / ".tripplanner"
_ACTIVE_TRIP_FILE = _TRIPS_DIR / "active_trip.json"
_TRIP_HISTORY_DIR = _TRIPS_DIR / "trips"

_COSMOS_USERS_CONTAINER = "users"
_COSMOS_TRIPS_CONTAINER = "trips"
_ACTIVE_TRIP_DOC_ID = "active_trip"


def compute_trip_id(plan: dict[str, Any]) -> str:
    """Return the stable destination and date-range identifier for a trip."""
    destination = str(plan.get("destination") or "trip")
    slug = re.sub(r"[^a-z0-9]+", "_", destination.lower()).strip("_") or "trip"
    departure = str(plan.get("departure_date") or "").strip() or "nodate"
    return_date = str(plan.get("return_date") or "").strip() or "nodate"
    return f"{slug}_{departure}_{return_date}"


def resolve_active_trip_path() -> Path:
    user_id = get_user_id()
    if user_id == "local":
        return _ACTIVE_TRIP_FILE
    return _TRIPS_DIR / "users" / user_id / "active_trip.json"


def resolve_trip_history_dir() -> Path:
    user_id = get_user_id()
    if user_id == "local":
        return _TRIP_HISTORY_DIR
    return _TRIPS_DIR / "users" / user_id / "trips"


def ensure_dirs() -> None:
    resolve_active_trip_path().parent.mkdir(parents=True, exist_ok=True)
    resolve_trip_history_dir().mkdir(parents=True, exist_ok=True)


def load_active_trip() -> dict[str, Any] | None:
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
    path = resolve_active_trip_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def delete_active_trip() -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID
        )
        return
    resolve_active_trip_path().unlink(missing_ok=True)


def persist_active_trip(plan: dict[str, Any]) -> None:
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_USERS_CONTAINER, get_user_id(), _ACTIVE_TRIP_DOC_ID, plan
        )
    else:
        ensure_dirs()
        atomic_write_json(resolve_active_trip_path(), plan, indent=2)
    mirror_to_history(plan)


def mirror_to_history(plan: dict[str, Any]) -> None:
    """Persist a plan in the current user's saved-trip collection."""
    trip_id = plan.get("trip_id")
    if not trip_id:
        return
    if storage_cosmos.is_enabled():
        storage_cosmos.upsert_doc(
            _COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id, plan
        )
    else:
        ensure_dirs()
        atomic_write_json(resolve_trip_history_dir() / f"{trip_id}.json", plan, indent=2)
    debug_store.record_trip(plan, get_user_id())


def load_history_trip(trip_id: str) -> dict[str, Any] | None:
    if not trip_id:
        return None
    if storage_cosmos.is_enabled():
        return storage_cosmos.read_doc(
            _COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id
        )
    path = resolve_trip_history_dir() / f"{trip_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def all_history_trips() -> list[dict[str, Any]]:
    if storage_cosmos.is_enabled():
        return storage_cosmos.query_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())
    history_dir = resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    plans: list[dict[str, Any]] = []
    for path in history_dir.glob("*.json"):
        try:
            plans.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return plans


def _trip_summary(plan: dict[str, Any], active_id: str | None) -> dict[str, Any]:
    trip_id = plan.get("trip_id") or compute_trip_id(plan)
    return {
        "trip_id": trip_id,
        "trip_number": int(plan.get("trip_number") or 0),
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
        "created_at": str(plan.get("created_at") or ""),
        "updated_at": str(plan.get("updated_at") or plan.get("created_at") or ""),
        "is_active": bool(active_id) and trip_id == active_id,
    }


def _next_trip_number(plans: list[dict[str, Any]] | None = None) -> int:
    try:
        known = plans if plans is not None else all_history_trips()
    except Exception:  # noqa: BLE001
        return 0
    return max((int(plan.get("trip_number") or 0) for plan in known), default=0) + 1


def _ensure_trip_numbers(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = [plan for plan in plans if not plan.get("trip_number")]
    if not missing:
        return plans
    following = _next_trip_number(plans)
    for plan in sorted(missing, key=lambda value: str(value.get("created_at") or "")):
        plan["trip_number"] = following
        current = load_history_trip(str(plan.get("trip_id") or ""))
        if current and not current.get("trip_number"):
            current["trip_number"] = following
            mirror_to_history(current)
        following += 1
    return plans


def list_saved_trips() -> list[dict[str, Any]]:
    active = load_active_trip()
    active_id = (active or {}).get("trip_id") if active else None
    summaries = [
        _trip_summary(plan, active_id)
        for plan in _ensure_trip_numbers(all_history_trips())
    ]
    summaries.sort(key=lambda trip: trip["updated_at"], reverse=True)
    return summaries


def saved_trip_destination(trip_id: str) -> str:
    plan = load_history_trip(trip_id)
    return str((plan or {}).get("destination") or "") if plan else ""


def delete_saved_trip(trip_id: str) -> bool:
    if not trip_id:
        return False
    if storage_cosmos.is_enabled():
        storage_cosmos.delete_doc(_COSMOS_TRIPS_CONTAINER, get_user_id(), trip_id)
    else:
        (resolve_trip_history_dir() / f"{trip_id}.json").unlink(missing_ok=True)
    return True


def clear_all_trip_history() -> int:
    if storage_cosmos.is_enabled():
        return storage_cosmos.delete_docs(_COSMOS_TRIPS_CONTAINER, get_user_id())

    deleted = 0
    history_dir = resolve_trip_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    for path in history_dir.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted
