"""Refresh itinerary place facts and report what changed since the last check."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from tripplanner import place_facts
from tripplanner.tools import trip_guard, web_search
from tripplanner.tools.trip_common import _stop_kind, _stop_name
from tripplanner.web import places_cache

_CHECKABLE_KINDS = frozenset({"attraction", "meal", "hotel"})
_MAX_PARALLEL_CHECKS = 8
_CLOSURE_RE = re.compile(
    r"\b(closed|closure|renovation|rehabilitation|seasonal|suspended|reopening)\b",
    re.I,
)


def _places(plan: dict[str, Any]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for day, _entry, stops in trip_guard.days_of(plan):
        for stop in stops:
            name = _stop_name(stop)
            if not name or _stop_kind(stop) not in _CHECKABLE_KINDS:
                continue
            key = name.casefold()
            row = by_key.setdefault(key, {"name": name, "days": []})
            if day not in row["days"]:
                row["days"].append(day)
    return list(by_key.values())


def refresh(plan: dict[str, Any]) -> dict[str, Any]:
    """Force-refresh checkable stops and update the trip's fact snapshots."""
    destination = str(plan.get("destination") or "").strip()
    places = _places(plan)
    previous = plan.get("place_fact_snapshots")
    snapshots = dict(previous) if isinstance(previous, dict) else {}
    comparison_available = bool(snapshots)

    def check(row: dict[str, Any]) -> tuple[str, tuple[dict[str, Any] | None, bool]]:
        key = row["name"].casefold()
        try:
            result = places_cache.refresh_details(row["name"], destination)
        except Exception:  # provider failure is reported per place
            result = (None, False)
        return key, result

    with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_CHECKS, len(places) or 1)) as pool:
        results = dict(pool.map(check, places))
    changes: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    checked = 0
    rows_by_key = {row["name"].casefold(): row for row in places}
    for key, result in results.items():
        row = rows_by_key[key]
        if result is None:
            failed.append(row)
            continue
        summary, succeeded = result
        if not succeeded or not summary:
            failed.append(row)
            continue
        checked += 1
        snapshot = place_facts.snapshot_from_summary(summary)
        changed = place_facts.changed_facts(snapshots.get(key), snapshot)
        if snapshots.get(key) and changed:
            changes.append({**row, "changed": changed})
        snapshots[key] = snapshot

    checked_at = datetime.now(UTC).isoformat()
    closure_watch = _closure_watch(plan, places)
    plan["place_fact_snapshots"] = snapshots
    plan["place_facts_checked_at"] = checked_at
    summary = {
        "checked_at": checked_at,
        "checked": checked,
        "total": len(places),
        "comparison_available": comparison_available,
        "changes": changes,
        "failed": failed,
        "closure_watch": closure_watch,
    }
    plan["place_facts_refresh"] = summary
    return {"plan": plan, **summary}


def _closure_watch(plan: dict[str, Any], places: list[dict[str, Any]]) -> dict[str, Any]:
    """Find source-linked unusual closure mentions; never decides a contradiction."""
    if not web_search.is_configured():
        return {"status": "unavailable", "advisories": []}
    destination = str(plan.get("destination") or "").strip()
    dates = " ".join(
        value
        for value in (
            str(plan.get("departure_date") or "").strip(),
            str(plan.get("return_date") or "").strip(),
        )
        if value
    )
    query = (
        f"{destination} {dates} attraction closures renovation rehabilitation "
        "seasonal closure official"
    ).strip()
    try:
        result = web_search.search_raw(query, max_results=5, search_depth="advanced")
    except Exception:
        return {"status": "failed", "advisories": []}

    advisories: list[dict[str, Any]] = []
    for source in result.get("results") or []:
        title = str(source.get("title") or "").strip()
        content = str(source.get("content") or "").strip()
        text = f"{title} {content}"
        if not _CLOSURE_RE.search(text):
            continue
        folded = text.casefold()
        for place in places:
            if place["name"].casefold() not in folded:
                continue
            url = str(source.get("url") or "")
            if urlparse(url).scheme not in {"http", "https"}:
                continue
            advisories.append(
                {
                    **place,
                    "title": title,
                    "url": url,
                    "snippet": content,
                }
            )
            break
    return {"status": "checked", "advisories": advisories}
