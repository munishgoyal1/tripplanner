"""Local-only archive of real trips, committed alongside the repo.

Every locally saved trip lands here so a bug can be investigated -- and restored
into any emulator -- without walking the planning flow again. One file per
planning run keeps the archive merge-safe when several sandboxes capture at
once, so no lane ever edits a file another lane is writing.

The archive is deliberately raw and unredacted: it is single-owner local
debugging data. It is never written in a hosted environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from tripplanner.json_store import atomic_write_json

SCHEMA_VERSION = 1

# Mirrors request_identity.is_hosted without importing the FastAPI request
# layer into the tool path.
_HOSTED_ENVIRONMENTS = {"canary", "prod", "production"}

# A long planning session saves often; keeping the newest slice bounds a single
# run's file without losing the shape of how the trip evolved.
MAX_REVISIONS = 50
MAX_KEYWORDS = 60
MAX_PLACE_ENTRIES = 200

# Fields that decide whether a save is a meaningful change or just a re-write.
_MEANINGFUL_FIELDS = (
    "destination",
    "departure_date",
    "return_date",
    "status",
    "travelers",
    "budget",
    "total_cost",
    "currency",
    "selected_flights",
    "selected_hotels",
    "selected_activities",
    "selected_restaurants",
    "itinerary",
    "stops",
)

# Keys whose string values name something a person would say out loud when
# referring to a trip ("the one with Wailea Beach").
_NAME_KEYS = {
    "airline",
    "city",
    "destination",
    "hotel",
    "hotel_name",
    "name",
    "place",
    "place_name",
    "restaurant",
    "title",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def store_root() -> Path:
    override = os.getenv("TRIPPLANNER_DEBUG_STORE_DIR", "").strip()
    return Path(override) if override else repo_root() / "debug-store"


def users_root() -> Path:
    return store_root() / "users"


def is_hosted_environment() -> bool:
    environment = os.getenv("TRIPPLANNER_ENVIRONMENT", "local").strip().lower()
    return environment in _HOSTED_ENVIRONMENTS


def is_enabled() -> bool:
    if is_hosted_environment():
        return False
    return os.getenv("TRIPPLANNER_DEBUG_STORE", "1").strip() != "0"


# ---------------------------------------------------------------------------
# Pure description helpers
# ---------------------------------------------------------------------------


def slugify(text: str, fallback: str = "trip") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or fallback


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def nights_between(departure: str, return_date: str) -> int | None:
    start, end = _parse_date(departure), _parse_date(return_date)
    if start is None or end is None:
        return None
    span = (end - start).days
    return span if span >= 0 else None


def month_year(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%b %Y") if parsed else ""


def collect_keywords(plan: dict[str, Any]) -> list[str]:
    """Named entities anywhere in the plan, so loose references still resolve."""
    found: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, child_key)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str) and key.lower() in _NAME_KEYS:
            text = node.strip()
            if text:
                found.append(text)

    walk(plan)
    seen: set[str] = set()
    unique: list[str] = []
    for entry in found:
        fingerprint = entry.lower()
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(entry)
    return unique[:MAX_KEYWORDS]


def _counts(plan: dict[str, Any]) -> dict[str, int]:
    return {
        "flights": len(plan.get("selected_flights") or []),
        "hotels": len(plan.get("selected_hotels") or []),
        "activities": len(plan.get("selected_activities") or []),
        "days": len(plan.get("itinerary") or []),
    }


def summarize(plan: dict[str, Any]) -> str:
    """One line a person can scan, e.g. '5-night Maui, Jul 2026, 2 hotels'."""
    destination = str(plan.get("destination") or "").strip() or "Unknown destination"
    nights = nights_between(
        str(plan.get("departure_date") or ""), str(plan.get("return_date") or "")
    )
    head = f"{nights}-night {destination}" if nights else destination
    parts = [head]
    when = month_year(str(plan.get("departure_date") or ""))
    if when:
        parts.append(when)
    counts = _counts(plan)
    for label in ("hotels", "activities", "flights"):
        if counts[label]:
            parts.append(f"{counts[label]} {label}")
    return ", ".join(parts)


def describe(plan: dict[str, Any]) -> dict[str, Any]:
    departure = str(plan.get("departure_date") or "").strip()
    return_date = str(plan.get("return_date") or "").strip()
    return {
        "destination": str(plan.get("destination") or "").strip(),
        "departure_date": departure,
        "return_date": return_date,
        "nights": nights_between(departure, return_date),
        "month_year": month_year(departure),
        "status": str(plan.get("status") or "draft"),
        "counts": _counts(plan),
        "keywords": collect_keywords(plan),
        "auto_summary": summarize(plan),
    }


def content_hash(plan: dict[str, Any]) -> str:
    """Fingerprint of the fields that make a save meaningfully different."""
    material = {field: plan.get(field) for field in _MEANINGFUL_FIELDS}
    encoded = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def created_date(plan: dict[str, Any]) -> str:
    """The day this planning run started; separates replans of the same trip."""
    raw = str(plan.get("created_at") or "").strip()[:10]
    return raw if _parse_date(raw) else date.today().isoformat()


# ---------------------------------------------------------------------------
# File identity
# ---------------------------------------------------------------------------


def run_key(trip_id: str, day: str) -> str:
    return f"{slugify(trip_id)}__{day}"


def file_name(archive_no: int, trip_id: str, day: str) -> str:
    return f"{archive_no:04d}__{run_key(trip_id, day)}.json"


def _archive_no_of(path: Path) -> int:
    head = path.name.split("__", 1)[0]
    return int(head) if head.isdigit() else 0


def next_archive_no(root: Path) -> int:
    """One past the highest number ever used, read from file names only."""
    existing = [_archive_no_of(path) for path in root.glob("*/*.json")]
    return max(existing, default=0) + 1


def user_slug(user_id: str) -> str:
    return slugify(user_id, fallback="local")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _current_branch(root: Path) -> str:
    """Branch name straight from .git, avoiding a subprocess on every save."""
    marker = root / ".git"
    try:
        if marker.is_file():
            pointer = marker.read_text(encoding="utf-8").strip()
            git_dir = Path(pointer.split(":", 1)[1].strip()) if ":" in pointer else None
        else:
            git_dir = marker
        if git_dir is None:
            return ""
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return head.split("refs/heads/", 1)[1] if "refs/heads/" in head else head[:12]


def provenance() -> dict[str, str]:
    root = repo_root()
    return {
        "workspace": root.name,
        "branch": _current_branch(root),
        "database": os.getenv("COSMOS_DATABASE", "").strip(),
        "at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def load_record(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def iter_records(root: Path | None = None) -> list[tuple[Path, dict[str, Any]]]:
    base = root if root is not None else users_root()
    if not base.exists():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*/*.json")):
        record = load_record(path)
        if record is not None:
            found.append((path, record))
    return found


def merge_revision(
    record: dict[str, Any],
    plan: dict[str, Any],
    where: dict[str, str],
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fold one save into a run record, adding a revision only on real change."""
    revisions = list(record.get("revisions") or [])
    fingerprint = content_hash(plan)
    if not revisions or revisions[-1].get("content_hash") != fingerprint:
        revisions.append({"at": where["at"], "content_hash": fingerprint, "plan": plan})
    else:
        revisions[-1] = {"at": where["at"], "content_hash": fingerprint, "plan": plan}
    record["revisions"] = revisions[-MAX_REVISIONS:]
    if bundle is not None:
        record["bundle"] = bundle
    record["descriptor"] = {
        **describe(plan),
        "label": str((record.get("descriptor") or {}).get("label") or ""),
        "notes": list((record.get("descriptor") or {}).get("notes") or []),
    }
    record["last_seen_at"] = where["at"]
    record["schema_version"] = SCHEMA_VERSION
    seen_in = [dict(entry) for entry in (record.get("seen_in") or [])]
    signature = (where.get("workspace"), where.get("branch"))
    if signature not in {(entry.get("workspace"), entry.get("branch")) for entry in seen_in}:
        seen_in.append(where)
    record["seen_in"] = seen_in
    return record


# ---------------------------------------------------------------------------
# Offline-render bundle
# ---------------------------------------------------------------------------


def _safe(producer: Any) -> Any:
    try:
        return producer()
    except Exception:  # noqa: BLE001 - a missing side store must not lose the trip
        return None


def referenced_places(plan: dict[str, Any]) -> dict[str, Any]:
    """Cached place entries this trip renders from, keyed ``name|city``."""
    from tripplanner.web import places_cache

    names = {word.lower() for word in collect_keywords(plan)}
    destination = str(plan.get("destination") or "").strip().lower()
    with places_cache._CACHE_LOCK:  # noqa: SLF001 - read-only debug snapshot
        snapshot = places_cache._live_snapshot()  # noqa: SLF001
    wanted: dict[str, Any] = {}
    for key, entry in snapshot.items():
        name, _, city = key.partition("|")
        if name in names or (destination and city == destination):
            wanted[key] = entry
        if len(wanted) >= MAX_PLACE_ENTRIES:
            break
    return wanted


def collect_bundle(plan: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Everything besides the trip needed to re-render it without providers."""
    from tripplanner.tools import user_preferences
    from tripplanner.web import chat_store

    trip_id = str(plan.get("trip_id") or "")
    return {
        "captured_at": _now_iso(),
        "user_id": user_id,
        "chat": _safe(lambda: chat_store.export_state([trip_id])),
        "preferences": _safe(user_preferences.load_preferences),
        "places": _safe(lambda: referenced_places(plan)),
    }


def capture_trip(plan: dict[str, Any], user_id: str) -> Path | None:
    """Archive one saved trip. Returns the file written, or None when disabled."""
    if not is_enabled():
        return None
    trip_id = str(plan.get("trip_id") or "").strip()
    if not trip_id:
        return None
    directory = users_root() / user_slug(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    day = created_date(plan)
    matches = sorted(directory.glob(f"*__{run_key(trip_id, day)}.json"))
    if matches:
        path = matches[0]
        record = load_record(path) or {}
    else:
        archive_no = next_archive_no(users_root())
        path = directory / file_name(archive_no, trip_id, day)
        record = {
            "archive_no": archive_no,
            "trip_id": trip_id,
            "user_id": user_id,
            "created_date": day,
            "first_captured_at": _now_iso(),
        }
    record.setdefault("archive_no", _archive_no_of(path))
    record.setdefault("trip_id", trip_id)
    record.setdefault("user_id", user_id)
    record.setdefault("created_date", day)
    record.setdefault("first_captured_at", _now_iso())
    revisions = record.get("revisions") or []
    changed = not revisions or revisions[-1].get("content_hash") != content_hash(plan)
    bundle = collect_bundle(plan, user_id) if changed else None
    atomic_write_json(path, merge_revision(record, plan, provenance(), bundle), indent=2)
    return path


def record_trip(plan: dict[str, Any], user_id: str) -> None:
    """Non-fatal capture: a debugging archive must never break a trip save."""
    try:
        capture_trip(plan, user_id)
    except Exception:  # noqa: BLE001 - archiving is best-effort by design
        pass
