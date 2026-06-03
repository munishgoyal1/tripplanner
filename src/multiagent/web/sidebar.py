"""Right-rail sidebar for the Chainlit chat UI.

Plugin-style: each panel is a function ``render(ctx) -> list[cl.Element]``
listed in ``PANELS``. The orchestrator calls them in order and pushes the
combined elements into ``cl.ElementSidebar``.

How to add a panel:
    1. Write a function ``def panel_foo(ctx: SidebarContext) -> list[cl.Element]``.
    2. Append it to ``PANELS``.
That's it — no other edits needed. Reorder or comment out to hide.

The three v1 panels are:
    * Overview — destination, dates, party, selection counts, total cost.
    * Photo gallery — Google Places photos for hotels & attractions.
    * Reviews & descriptions — editorial summary + top reviews per item.

A focus dict (``{"kind": "hotel"|"attraction", "name": "..."}``) zooms every
panel onto a single item; ``None`` shows the whole trip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import chainlit as cl
from chainlit.element import Element

from multiagent.web import places_cache

log = logging.getLogger(__name__)

_MAX_GALLERY_ITEMS = 6
_MAX_REVIEW_ITEMS = 4
_MAX_FOCUS_ACTIONS = 10


@dataclass
class SidebarContext:
    trip: dict[str, Any] | None
    focus: dict[str, Any] | None
    user_id: str


PanelFn = Callable[[SidebarContext], list[Element]]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _itinerary_items(
    trip: dict[str, Any] | None, focus: dict[str, Any] | None
) -> list[dict[str, str]]:
    """Return ``[{kind, name}, ...]`` for the things we'd show in the sidebar.

    If focus is set, returns just that one item. Otherwise enumerates all
    selected hotels followed by all selected activities.
    """
    if focus and focus.get("name"):
        return [{"kind": focus.get("kind", "place"), "name": focus["name"]}]
    if not trip:
        return []
    items: list[dict[str, str]] = []
    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            items.append({"kind": "hotel", "name": str(h["name"])})
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            items.append({"kind": "attraction", "name": str(a["name"])})
    return items


def _fmt_money(value: Any) -> str:
    if isinstance(value, (int, float)) and value:
        return f"₹{value:,.0f}"
    return "—"


# ---------------------------------------------------------------------------
# panels
# ---------------------------------------------------------------------------


def panel_overview(ctx: SidebarContext) -> list[Element]:
    trip = ctx.trip
    if not trip:
        return [
            cl.Text(
                name="Trip planner",
                content=(
                    "_No active trip yet._\n\n"
                    "Tell the agent where you want to go (e.g. *plan a 5-day "
                    "trip to Goa in December for 2 adults*) and this panel "
                    "will fill in with your itinerary, photos and reviews."
                ),
                display="side",
            )
        ]

    dest = trip.get("destination", "—")
    lines = [
        f"## ✈️ {dest}",
        "",
        f"**Dates:** {trip.get('departure_date', '?')} → {trip.get('return_date', '?')}",
        f"**Travelers:** {trip.get('travelers', '?')}",
        f"**Origin:** {trip.get('origin') or '—'}",
        f"**Status:** {str(trip.get('status', 'draft')).title()}",
    ]
    notes = trip.get("notes")
    if notes:
        lines.extend(["", f"_{notes}_"])

    counts = {
        "Flights": len(trip.get("selected_flights") or []),
        "Hotels": len(trip.get("selected_hotels") or []),
        "Activities": len(trip.get("selected_activities") or []),
        "Day plans": len(trip.get("day_wise_itinerary") or []),
    }
    lines.append("")
    lines.append("**Selections so far:**")
    for label, n in counts.items():
        lines.append(f"- {label}: {n}")

    total = trip.get("total_cost")
    if total:
        lines.append("")
        lines.append(f"**Total estimate:** {_fmt_money(total)}")

    if ctx.focus and ctx.focus.get("name"):
        lines.append("")
        lines.append(
            f"🔍 _Focused on **{ctx.focus['name']}** — click *Whole trip* "
            "below to zoom back out._"
        )

    return [cl.Text(name="Overview", content="\n".join(lines), display="side")]


def panel_gallery(ctx: SidebarContext) -> list[Element]:
    items = _itinerary_items(ctx.trip, ctx.focus)
    if not items:
        return []

    destination = (ctx.trip or {}).get("destination", "")
    elements: list[Element] = []
    for item in items[:_MAX_GALLERY_ITEMS]:
        urls = places_cache.get_photos(item["name"], destination, max_photos=3)
        for i, url in enumerate(urls):
            elements.append(
                cl.Image(
                    url=url,
                    name=f"{item['name']} #{i + 1}",
                    display="side",
                )
            )
    return elements


def panel_reviews(ctx: SidebarContext) -> list[Element]:
    items = _itinerary_items(ctx.trip, ctx.focus)
    if not items:
        return []

    destination = (ctx.trip or {}).get("destination", "")
    blocks: list[str] = []
    for item in items[:_MAX_REVIEW_ITEMS]:
        info = places_cache.get_summary(item["name"], destination)
        if not info:
            continue
        kind = item["kind"].title() if item["kind"] != "attraction" else "Attraction"
        header_meta = []
        if info.get("rating"):
            header_meta.append(f"⭐ {info['rating']}")
        if info.get("review_count"):
            header_meta.append(f"({info['review_count']:,} reviews)")
        meta_str = " ".join(header_meta)
        header = f"### {kind}: {info.get('name') or item['name']}"
        if meta_str:
            header += f"  \n_{meta_str}_"
        blocks.append(header)
        if info.get("editorial_summary"):
            blocks.append(info["editorial_summary"])
        for r in (info.get("reviews") or [])[:2]:
            text = (r.get("text") or "").strip()
            if not text:
                continue
            stars = "⭐" * int(r.get("rating") or 0)
            author = r.get("author") or "Guest"
            blocks.append(f"> {stars} _{author}_: {text}")
        if info.get("website"):
            blocks.append(f"[Website ↗]({info['website']})")
        blocks.append("")

    if not blocks:
        return []
    return [
        cl.Text(
            name="Reviews & descriptions",
            content="\n".join(blocks),
            display="side",
        )
    ]


PANELS: list[PanelFn] = [panel_overview, panel_gallery, panel_reviews]


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


async def render_sidebar(
    trip: dict[str, Any] | None,
    focus: dict[str, Any] | None,
    user_id: str,
) -> None:
    """Re-render every panel and push the result to ``cl.ElementSidebar``."""
    ctx = SidebarContext(trip=trip, focus=focus, user_id=user_id)
    elements: list[Element] = []
    for panel in PANELS:
        try:
            elements.extend(panel(ctx))
        except Exception:  # one bad panel must not break the rail
            log.exception("sidebar panel %s failed", panel.__name__)

    title = "Trip planner"
    if trip and trip.get("destination"):
        title = f"✈️ {trip['destination']}"
        if focus and focus.get("name"):
            title = f"{title} — {focus['name']}"

    try:
        await cl.ElementSidebar.set_title(title)
        await cl.ElementSidebar.set_elements(elements)
    except Exception:
        log.exception("sidebar emit failed")


def build_focus_actions(trip: dict[str, Any] | None) -> list[cl.Action]:
    """One ``cl.Action`` per hotel/attraction, plus a *Whole trip* reset.

    The agent's reply message attaches these so the user can zoom the
    sidebar onto a specific item with one click.
    """
    actions: list[cl.Action] = []
    if not trip:
        return actions
    for h in trip.get("selected_hotels") or []:
        if isinstance(h, dict) and h.get("name"):
            name = str(h["name"])
            actions.append(
                cl.Action(
                    name="focus_item",
                    payload={"kind": "hotel", "name": name},
                    label=f"🏨 {name}",
                    tooltip=f"Show photos and reviews for {name}",
                )
            )
    for a in trip.get("selected_activities") or []:
        if isinstance(a, dict) and a.get("name"):
            name = str(a["name"])
            actions.append(
                cl.Action(
                    name="focus_item",
                    payload={"kind": "attraction", "name": name},
                    label=f"🎯 {name}",
                    tooltip=f"Show photos and reviews for {name}",
                )
            )
    if not actions:
        return actions
    # cap before adding the reset so we don't push it off the visible row
    actions = actions[:_MAX_FOCUS_ACTIONS]
    actions.append(
        cl.Action(
            name="focus_item",
            payload={"kind": "overview", "name": ""},
            label="🌐 Whole trip",
            tooltip="Show the whole trip in the side panel again",
        )
    )
    return actions
