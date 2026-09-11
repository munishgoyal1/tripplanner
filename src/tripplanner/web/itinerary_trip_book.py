"""Lab 5 Option B: layered Trip Book HTML composition.

Owned by the itinerary export renderer. Contents and document readiness open
the packet, executable days follow, and confirmations plus optional place
context stay in appendices. Emergency numbers are never invented.
"""

# ruff: noqa: E501

from __future__ import annotations

from html import escape
from typing import Any

from tripplanner.web import places_cache


def _e(value: Any) -> str:
    return escape(str(value or ""), quote=True)
_GENERIC_INSIGHT_TAILS = (
    "is a practical base for nearby sights.",
    "is a convenient meal break near your route.",
    "is a popular stop to include in this day circuit.",
)


def _circuit_labels(pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    visit = 0
    for pid in pin_ids:
        kind = str((pin_by_id.get(pid) or {}).get("kind") or "").strip().lower()
        if kind == "hotel":
            labels.append("H")
            continue
        visit += 1
        labels.append(str(visit))
    return labels


def _selection_label(item: Any, fallback: str) -> str:
    if isinstance(item, str):
        return item.strip() or fallback
    if not isinstance(item, dict):
        return fallback
    for key in ("name", "airline", "title", "label", "hotel_name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return fallback


def _selection_detail(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    parts: list[str] = []
    for key in ("flight_number", "from", "origin", "to", "destination", "date", "check_in", "check_out"):
        value = str(item.get(key) or "").strip()
        if value:
            parts.append(value)
    return " · ".join(parts[:4])


def trip_book_readiness(trip: dict[str, Any]) -> dict[str, Any]:
    from tripplanner.tools import user_preferences as prefs_store
    from tripplanner.web import document_readiness, place_country, travel_documents

    prefs = prefs_store.load_preferences()
    profile = prefs.get("profile") if isinstance(prefs.get("profile"), dict) else {}
    origin_country = place_country.resolve_country(trip.get("origin")) or (
        place_country.resolve_country(profile.get("home_country"))
    )
    return document_readiness.evaluate(
        trip,
        travel_documents.list_documents("traveler"),
        prefs,
        origin_country=origin_country or "",
        destination_country=place_country.resolve_country(trip.get("destination")) or "",
    )


def stay_name(trip: dict[str, Any], itinerary: dict[str, Any]) -> str:
    hotels = trip.get("selected_hotels") or []
    if hotels:
        return _selection_label(hotels[0], "")
    for day in itinerary.get("days") or []:
        for stop in day.get("stops") or []:
            if str(stop.get("kind") or "") == "hotel" and stop.get("name"):
                return str(stop["name"])
    return ""


def _contents(
    *,
    include_map_circuit: bool,
    readiness: dict[str, Any],
    destination: str,
    travelers: str,
    day_count: int,
) -> str:
    items = [
        ("Trip brief", "#trip-brief"),
        ("Daily itinerary", "#daily-plan"),
        ("Essentials and help", "#essentials"),
        ("Travel documents", "#documents"),
        ("Place guide", "#place-guide"),
    ]
    if include_map_circuit:
        items.insert(2, ("Day circuit maps", "#daily-plan"))
    rows = "".join(
        f"<li><a href='{href}'>{_e(label)}</a></li>" for label, href in items
    )
    blockers = int(readiness.get("blockers") or 0)
    warnings = int(readiness.get("warnings") or 0)
    badge = str(readiness.get("badge") or "")
    if blockers or warnings:
        tone = "warn"
        status = badge or (
            f"{blockers + warnings} document item"
            f"{'s' if blockers + warnings != 1 else ''} to review"
        )
    else:
        tone = "ready"
        status = "Document groups on file look ready"
        if not readiness.get("checks") and readiness.get("reason"):
            status = "Document checks are silent for this trip"
    return (
        "<section class='book-cover' id='contents'>"
        "<p class='k'>Your complete travel book</p>"
        f"<h1>{_e(destination or 'Trip')}, ready to go.</h1>"
        "<p class='lede'>"
        f"{day_count} day{'s' if day_count != 1 else ''}"
        f"{', ' + _e(travelers) if travelers else ''}"
        " · one carry-along plan with confirmations and entry paperwork behind the days.</p>"
        f"<ol class='toc'>{rows}</ol>"
        f"<div class='ready-callout {tone}'>{_e(status)}</div>"
        "</section>"
    )


def _brief(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    *,
    origin: str,
    depart: str,
    ret: str,
    travelers: str,
    total_display: str,
    stay: str,
    readiness: dict[str, Any],
) -> str:
    facts = [
        ("Depart", depart or "—"),
        ("Return", ret or "—"),
        ("From", origin or "—"),
        ("Stay", stay or "—"),
        ("Travelers", travelers or "—"),
    ]
    if total_display:
        facts.append(("Budget", total_display))
    fact_html = "".join(
        f"<div><div class='k'>{_e(label)}</div><div class='v'>{_e(value)}</div></div>"
        for label, value in facts
    )
    actions: list[str] = []
    for check in readiness.get("checks") or []:
        if check.get("severity") not in {"blocker", "warning"}:
            continue
        title = str(check.get("title") or "").strip()
        action = str(check.get("action") or check.get("detail") or "").strip()
        if title:
            actions.append(f"{title}" + (f" — {action}" if action else ""))
    pending_stops = 0
    for day in itinerary.get("days") or []:
        pending_stops += sum(
            1
            for stop in (day.get("stops") or [])
            if stop.get("kind") not in {"hotel", "airport", "origin"} and not stop.get("booked")
        )
    if pending_stops:
        actions.append(
            f"{pending_stops} planned stop{'s' if pending_stops != 1 else ''} still pending booking"
        )
    if not actions:
        actions.append("Carry this book on every phone; it matches the live workspace.")
    action_html = "".join(f"<li>{_e(item)}</li>" for item in actions[:6])
    prefs = trip.get("preferences_snapshot") or {}
    style = str(prefs.get("trip_style") or "").strip()
    food = prefs.get("food_preferences") if isinstance(prefs.get("food_preferences"), dict) else {}
    dietary = ", ".join(str(item) for item in (food.get("dietary") or []) if str(item).strip())
    family_bits: list[str] = []
    if style:
        family_bits.append(f"Saved trip style: {style.replace('_', ' ')}.")
    if dietary:
        family_bits.append(f"Saved dietary notes: {dietary}.")
    family_html = ""
    if family_bits:
        family_html = (
            "<aside class='family-note'><p class='k'>For this traveller</p>"
            f"<p>{_e(' '.join(family_bits))}</p>"
            "<p class='source'>Saved preference snapshot for this trip</p></aside>"
        )
    return (
        "<section class='trip-brief' id='trip-brief'>"
        "<p class='k'>At a glance</p>"
        "<h2>Everything needed before departure</h2>"
        f"<div class='grid'>{fact_html}</div>"
        "<div class='brief-split'>"
        "<div><h3>Before you leave</h3>"
        f"<ol class='actions'>{action_html}</ol></div>"
        f"{family_html}</div></section>"
    )


def _stop_row(
    stop: dict[str, Any],
    *,
    marker: str,
    is_first: bool,
    is_last: bool,
    circuit_return: bool,
    include_photos: bool,
    include_budgets: bool,
    destination: str,
    seen_photos: set[str],
) -> str:
    from tripplanner.web import itinerary_export

    return itinerary_export.export_stop_html(
        stop,
        marker=marker,
        is_first=is_first,
        is_last=is_last,
        circuit_return=circuit_return,
        include_photos=include_photos,
        include_budgets=include_budgets,
        destination=destination,
        seen_photos=seen_photos,
    )


def _day_sections(
    itinerary: dict[str, Any],
    *,
    include_photos: bool,
    include_map_circuit: bool,
    include_budgets: bool,
    pin_by_id: dict[str, dict[str, Any]],
    route_by_day: dict[int, dict[str, Any]],
    destination: str,
    seen_photos: set[str],
) -> str:
    from tripplanner.web import itinerary_export

    blocks: list[str] = []
    for day in itinerary.get("days") or []:
        day_num = int(day.get("day") or 0)
        route = route_by_day.get(day_num) if include_map_circuit else None
        maps_url = str(day.get("google_maps_url") or "")
        schedule = day.get("schedule") or {}
        weather = day.get("weather") or {}
        visit = 0
        stops = [s for s in (day.get("stops") or []) if isinstance(s, dict)]
        last = stops[-1] if stops else None
        circuit_return_index = (
            len(stops) - 1
            if last and str(last.get("kind") or "") == "hotel" and any(
                str(item.get("kind") or "") == "hotel"
                and str(item.get("name") or "") == str(last.get("name") or "")
                for item in stops[:-1]
            )
            else -1
        )
        stops_html: list[str] = []
        for index, stop in enumerate(stops):
            kind = str(stop.get("kind") or "")
            if kind == "hotel":
                marker = "H"
            elif kind == "airport":
                marker = "A"
            elif kind in {"attraction", "meal", "restaurant"}:
                visit += 1
                marker = str(visit)
            else:
                marker = ""
            stops_html.append(
                _stop_row(
                    stop,
                    marker=marker,
                    is_first=index == 0,
                    is_last=index == len(stops) - 1,
                    circuit_return=index == circuit_return_index,
                    include_photos=include_photos,
                    include_budgets=include_budgets,
                    destination=destination,
                    seen_photos=seen_photos,
                )
            )
        circuit_html = ""
        if include_map_circuit and route:
            pin_ids = list(route.get("pin_ids") or [])
            pin_names = [str(pin_by_id.get(pid, {}).get("name") or pid) for pid in pin_ids]
            if pin_names:
                circuit = " -> ".join(_e(n) for n in pin_names)
                stats = route.get("route") or day.get("route") or {}
                from tripplanner.web import itinerary_export

                snippet = itinerary_export._route_snippet_svg(
                    itinerary_export._route_points(pin_ids, pin_by_id),
                    _circuit_labels(pin_ids, pin_by_id),
                )
                static_map = itinerary_export._static_map_data_uri(pin_ids, pin_by_id)
                map_visual = (
                    f"<img class='route-map' src='{static_map}' alt='Day {day_num} route map' />"
                    if static_map
                    else snippet
                )
                maps_link_html = (
                    f"<a class='maps-link' href='{_e(maps_url)}' target='_blank' rel='noreferrer'>"
                    "Open this day route in Google Maps ↗</a>"
                    if maps_url
                    else ""
                )
                qr_html = (
                    "<div class='qr-wrap'><img class='qr' src='"
                    + _e(itinerary_export._qr_image_url(maps_url))
                    + "' alt='QR for day map route' /><div class='qr-cap'>Scan route</div></div>"
                    if maps_url
                    else ""
                )
                stats_html = " · ".join(
                    _e(stats.get(key) or "")
                    for key in ("distance_display", "duration_display", "mode")
                )
                circuit_html = (
                    "<div class='circuit'>"
                    "<div class='circuit-title'>Day circuit inset</div>"
                    f"{map_visual}"
                    f"<div class='circuit-line'>{circuit}</div>"
                    f"<div class='circuit-stats'>{stats_html}</div>"
                    "<p class='circuit-key'><strong>H</strong> hotel · numbers follow the agenda order</p>"
                    f"<div class='circuit-actions'>{maps_link_html}{qr_html}</div>"
                    "</div>"
                )
        weather_bits: list[str] = []
        if isinstance(weather, dict):
            high = weather.get("high_c")
            low = weather.get("low_c")
            if isinstance(high, (int, float)) and isinstance(low, (int, float)):
                weather_bits.append(f"{low:.0f}–{high:.0f}°C")
            summary = str(weather.get("summary") or weather.get("condition") or "").strip()
            if summary:
                weather_bits.append(summary)
        spend_bits = [
            str(stop.get("cost_display") or "").strip()
            for stop in (day.get("stops") or [])
            if include_budgets and str(stop.get("cost_display") or "").strip()
        ]
        footer_bits = []
        if weather_bits:
            footer_bits.append(" · ".join(weather_bits))
        if spend_bits:
            footer_bits.append("On-day spend hints: " + " · ".join(spend_bits[:4]))
        footer_html = (
            f"<div class='day-foot'>{_e(' · '.join(footer_bits))}</div>" if footer_bits else ""
        )
        span = ""
        if schedule.get("start") or schedule.get("end"):
            span = f"{schedule.get('start') or '—'}–{schedule.get('end') or '—'}"
        travel = str(schedule.get("travel_duration_display") or "")
        route_stats = day.get("route") or {}
        distance = str(route_stats.get("distance_display") or "")
        timing = " · ".join(part for part in (span, travel, distance) if part)
        blocks.append(
            """
            <section class='day' id='day-{day_num}'>
              <div class='day-head'>
                <h2>Day {day_num}: {title}</h2>
                <div class='day-date'>{date}{timing}</div>
              </div>
              {summary}
              <div class='day-spread'>
                <ol class='stops'>{stops}</ol>
                {circuit}
              </div>
              {footer}
            </section>
            """.format(
                day_num=day_num,
                title=_e(day.get("title") or f"Day {day_num}"),
                date=_e(
                    itinerary_export.format_export_day_date(str(day.get("date") or ""))
                ),
                timing=f" · {_e(timing)}" if timing else "",
                summary=(
                    f"<p class='summary'>{_e(day.get('summary') or '')}</p>"
                    if day.get("summary")
                    else ""
                ),
                stops="".join(stops_html),
                circuit=circuit_html,
                footer=footer_html,
            )
        )
    return "<div id='daily-plan'>" + "".join(blocks) + "</div>"


def _essentials(
    trip: dict[str, Any],
    itinerary: dict[str, Any],
    stay: str,
    *,
    include_budgets: bool,
) -> str:
    from tripplanner.web import itinerary_export

    weather_budget = itinerary_export._essentials_section(trip, include_budgets=include_budgets)
    help_rows: list[str] = []
    if stay:
        place = places_cache.get_details(stay, str(trip.get("destination") or "")) or {}
        phone = str(place.get("phone") or place.get("internationalPhoneNumber") or "").strip()
        address = str(place.get("address") or "").strip()
        if phone or address:
            help_rows.append(
                "<div class='essential'><div class='k'>Hotel</div>"
                f"<div class='v'>{_e(stay)}</div>"
                + (f"<div class='note'>{_e(phone)}</div>" if phone else "")
                + (f"<div class='note'>{_e(address)}</div>" if address else "")
                + "</div>"
            )
    travelers = str(trip.get("travelers") or "").strip()
    if travelers:
        help_rows.append(
            "<div class='essential'><div class='k'>Travelling party</div>"
            f"<div class='v'>{_e(travelers)}</div>"
            "<div class='note'>Passport and card numbers stay out of this file by design.</div></div>"
        )
    days = itinerary.get("days") or []
    last = days[-1] if days else {}
    return_bits = [
        part
        for part in (
            str(trip.get("return_date") or "").strip(),
            stay and f"Check out from {stay}",
            str(last.get("title") or "").strip(),
        )
        if part
    ]
    if return_bits:
        help_rows.append(
            "<div class='essential'><div class='k'>Getting home</div>"
            f"<div class='v'>{_e(' · '.join(return_bits))}</div></div>"
        )
    extra = "".join(help_rows)
    if not weather_budget and not extra:
        return ""
    if weather_budget:
        body = weather_budget.replace("<section class='essentials'>", "").replace("</section>", "")
        heading = body.replace("<h2>Trip essentials</h2>", "<h2>Essentials and help</h2>", 1)
        return f"<section class='essentials' id='essentials'>{heading}{extra}</section>"
    return f"<section class='essentials' id='essentials'><h2>Essentials and help</h2>{extra}</section>"


def _documents(trip: dict[str, Any], readiness: dict[str, Any]) -> str:
    from tripplanner.web import itinerary_export

    wallet = itinerary_export._documents_wallet_section(trip)
    rows: list[str] = []
    for item in trip.get("selected_flights") or []:
        rows.append(
            "<li class='doc-row'><span class='doc-type'>Flight</span>"
            f"<span class='doc-holder'>{_e(_selection_label(item, 'Flight'))}</span>"
            f"<span class='doc-summary'>{_e(_selection_detail(item) or 'Selected')}</span></li>"
        )
    for item in trip.get("selected_hotels") or []:
        rows.append(
            "<li class='doc-row'><span class='doc-type'>Stay</span>"
            f"<span class='doc-holder'>{_e(_selection_label(item, 'Hotel'))}</span>"
            f"<span class='doc-summary'>{_e(_selection_detail(item) or 'Selected')}</span></li>"
        )
    visa = trip.get("visa") if isinstance(trip.get("visa"), dict) else {}
    visa_note = str(visa.get("summary") or visa.get("note") or "").strip()
    if visa_note:
        rows.append(
            "<li class='doc-row'><span class='doc-type'>Entry</span>"
            f"<span class='doc-holder'>{_e(str(trip.get('destination') or 'Destination'))}</span>"
            f"<span class='doc-summary'>{_e(visa_note)}</span></li>"
        )
    gaps = "".join(
        "<li class='doc-row gap'><span class='doc-type'>Action needed</span>"
        f"<span class='doc-holder'>{_e(str(check.get('title') or ''))}</span>"
        f"<span class='doc-summary'>{_e(str(check.get('detail') or ''))}</span></li>"
        for check in (readiness.get("checks") or [])
        if check.get("severity") in {"blocker", "warning"}
    )
    extra = "".join(rows)
    if wallet:
        inner = wallet.replace("<section class='documents'>", "").replace("</section>", "")
        heading = inner.replace(
            "<h2>Travel documents on file</h2>",
            "<h2>Confirmations and entry</h2>",
            1,
        )
        return (
            "<section class='documents' id='documents'>"
            + heading
            + (f"<ul class='doc-list'>{extra}{gaps}</ul>" if extra or gaps else "")
            + "</section>"
        )
    if not extra and not gaps:
        return (
            "<section class='documents' id='documents'><h2>Travel documents</h2>"
            "<p class='doc-note'>No confirmations or saved documents are attached yet. "
            "Identity numbers stay out of this file by design.</p></section>"
        )
    return (
        "<section class='documents' id='documents'><h2>Confirmations and entry</h2>"
        f"<ul class='doc-list'>{extra}{gaps}</ul>"
        "<p class='doc-note'>Reference numbers are kept out of this file by design.</p></section>"
    )


def _guide(itinerary: dict[str, Any]) -> str:
    cards: list[str] = []
    seen: set[str] = set()
    for day in itinerary.get("days") or []:
        for stop in day.get("stops") or []:
            insight = str(stop.get("insight") or "").strip()
            name = str(stop.get("name") or "").strip()
            if not insight or not name or name.casefold() in seen:
                continue
            if any(insight.endswith(tail) for tail in _GENERIC_INSIGHT_TAILS):
                continue
            seen.add(name.casefold())
            cards.append(
                "<div class='guide-card'>"
                f"<h3>{_e(name)}</h3>"
                f"<p>{_e(insight)}</p>"
                "<p class='source'>Place facts on file · not a guidebook page</p>"
                "</div>"
            )
            if len(cards) >= 3:
                break
        if len(cards) >= 3:
            break
    if not cards:
        return ""
    return (
        "<section class='place-guide' id='place-guide'>"
        "<p class='k'>Optional reference</p>"
        "<h2>Place context, kept last</h2>"
        "<p class='lede'>Useful in the moment, never ahead of today’s plan or a named confirmation.</p>"
        f"<div class='guide-grid'>{''.join(cards)}</div></section>"
    )


def render_layered_trip_book(
    trip: dict[str, Any],
    *,
    include_photos: bool,
    include_map_circuit: bool,
    include_budgets: bool,
    auto_print: bool,
    share_url: str,
    itinerary: dict[str, Any],
    pin_by_id: dict[str, dict[str, Any]],
    route_by_day: dict[int, dict[str, Any]],
    destination: str,
    origin: str,
    depart: str,
    ret: str,
    travelers: str,
    total_display: str,
    seen_photos: set[str],
) -> str:
    from tripplanner.web import itinerary_export

    readiness = trip_book_readiness(trip)
    stay = stay_name(trip, itinerary)
    contents = _contents(
        include_map_circuit=include_map_circuit,
        readiness=readiness,
        destination=destination,
        travelers=travelers,
        day_count=len(itinerary.get("days") or []),
    )
    brief = _brief(
        trip,
        itinerary,
        origin=origin,
        depart=depart,
        ret=ret,
        travelers=travelers,
        total_display=total_display,
        stay=stay,
        readiness=readiness,
    )
    days = _day_sections(
        itinerary,
        include_photos=include_photos,
        include_map_circuit=include_map_circuit,
        include_budgets=include_budgets,
        pin_by_id=pin_by_id,
        route_by_day=route_by_day,
        destination=destination,
        seen_photos=seen_photos,
    )
    essentials = _essentials(trip, itinerary, stay, include_budgets=include_budgets)
    documents = _documents(trip, readiness)
    guide = _guide(itinerary)
    decisions = itinerary_export._decisions_section(trip)
    auto = "<script>window.addEventListener('load',()=>window.print());</script>" if auto_print else ""
    if share_url:
        share_section = (
            f"<div style='margin-top:18px;padding:14px 18px;border-radius:14px;"
            f"background:linear-gradient(135deg,#ecfeff,#f0fdf4);"
            f"border:1px solid #a7f3d0;text-align:center;'>"
            f"<p style='margin:0 0 8px;font-size:14px;font-weight:600;color:#064e3b;'>"
            f"Continue planning or share this trip</p>"
            f"<a href='{_e(share_url)}' "
            f"style='display:inline-block;padding:9px 22px;border-radius:999px;"
            f"background:#0d9488;color:#fff;font-size:14px;font-weight:700;"
            f"text-decoration:none;'>Open in Trip Planner &rarr;</a>"
            f"<p style='margin:8px 0 0;font-size:11px;color:#6b7280;'>"
            f"{_e(share_url)}</p>"
            f"</div>"
        )
    else:
        share_section = ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{_e(destination or 'Trip')} · Trip Book</title>
  <style>
    :root {{ --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --soft:#f8fafc; --accent:#0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: "Segoe UI", "Inter", sans-serif; color:var(--ink); background:#fff; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .k {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }}
    .v {{ font-weight:600; }}
    .lede {{ color:#475569; max-width:40rem; }}
    .book-cover, .trip-brief, .day, .essentials, .documents, .place-guide, .why {{
      margin-top:20px; border:1px solid var(--line); border-radius:14px; padding:18px; page-break-inside:avoid;
    }}
    .book-cover {{ border-top:6px solid var(--accent); }}
    .book-cover h1, .trip-brief h2, .place-guide h2 {{ margin:6px 0 10px; font-size:28px; }}
    .toc {{ margin:16px 0; padding-left:18px; }}
    .toc a {{ color:var(--accent); font-weight:600; text-decoration:none; }}
    .ready-callout {{ border-left:3px solid #059669; background:#ecfdf5; padding:10px 12px; font-weight:600; }}
    .ready-callout.warn {{ border-left-color:#d97706; background:#fffbeb; }}
    .grid {{ display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .brief-split {{ display:grid; grid-template-columns: 1.2fr .8fr; gap:16px; margin-top:16px; }}
    .actions {{ margin:8px 0 0; padding-left:18px; }}
    .family-note {{ background:#f0fdfa; padding:12px; border-radius:10px; }}
    .family-note .source, .guide-card .source {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
    .day-head {{ display:flex; justify-content:space-between; gap:10px; align-items:baseline; }}
    .day h2 {{ margin:0; font-size:20px; }}
    .day-date {{ color:var(--muted); font-size:13px; }}
    .summary {{ margin:10px 0 8px; color:#334155; }}
    .day-spread {{ display:grid; grid-template-columns: 1.15fr .85fr; gap:16px; align-items:start; }}
    .circuit {{ margin:0; background:#ecfeff; border:1px solid #bae6fd; border-radius:10px; padding:10px; }}
    .circuit-title {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:#0c4a6e; }}
    .circuit-key {{ margin:6px 0 0; font-size:11px; color:#0369a1; }}
    .route-svg {{ margin-top:8px; width:100%; max-width:330px; height:auto; }}
    .route-map {{ display:block; margin-top:8px; width:100%; max-width:640px; height:auto; border-radius:10px; border:1px solid #bae6fd; }}
    .circuit-line {{ margin-top:5px; font-size:14px; color:#0f172a; }}
    .circuit-stats {{ margin-top:5px; font-size:12px; color:#0369a1; }}
    .circuit-actions {{ margin-top:8px; display:flex; align-items:center; gap:10px; }}
    .maps-link {{ color:#0f766e; font-size:12px; font-weight:600; text-decoration:none; }}
    .qr-wrap {{ display:flex; align-items:center; gap:6px; margin-left:auto; }}
    .qr {{ width:54px; height:54px; border-radius:8px; border:1px solid #bae6fd; background:#fff; }}
    .qr-cap {{ color:#0369a1; font-size:11px; }}
    .stops {{ margin:0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:8px; }}
    .stop {{ display:flex; flex-direction:column; gap:4px; border-bottom:1px solid var(--line); padding:8px 0; }}
    .stop-card {{ display:flex; gap:12px; justify-content:space-between; }}
    .stop.hotel .ord {{ background:#334155; }}
    .stop-main {{ min-width:0; flex:1; }}
    .stop-line {{ display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }}
    .ord {{ display:inline-grid; place-items:center; width:22px; height:22px; border-radius:999px; background:var(--accent); color:#fff; font-size:11px; font-weight:700; }}
    .ord.ghost {{ background:#e2e8f0; color:transparent; }}
    .when {{ min-width:4.5rem; font-size:12px; color:var(--muted); }}
    .name {{ font-weight:700; flex:1; }}
    .state {{ margin-left:auto; font-size:11px; font-weight:700; color:#92400e; }}
    .meta {{ margin-top:4px; color:var(--muted); font-size:12px; }}
    .place-meta, .note, .ref {{ margin-top:4px; font-size:12px; color:#475569; }}
    .travel {{ margin:0 0 2px 4px; color:#0f766e; font-size:12px; font-weight:600; }}
    .travel-extra {{ margin-top:2px; font-weight:400; color:var(--muted); }}
    .concern {{ margin-top:4px; color:#be123c; font-size:12px; font-weight:600; }}
    .chips {{ margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-size:11px; color:#334155; background:#fff; }}
    .stop-photo-wrap {{ width:120px; flex-shrink:0; }}
    .stop-photo {{ width:120px; height:84px; object-fit:cover; border-radius:8px; border:1px solid var(--line); }}
    .day-foot {{ margin-top:10px; color:var(--muted); font-size:12px; }}
    .essential {{ margin-top:8px; }}
    .doc-list {{ margin:0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:8px; }}
    .doc-row {{ display:flex; flex-wrap:wrap; gap:10px; align-items:baseline; border:1px solid var(--line); border-radius:10px; padding:8px 10px; background:var(--soft); font-size:13px; }}
    .doc-row.gap {{ background:#fffbeb; border-color:#fcd34d; }}
    .doc-type {{ font-weight:700; min-width:140px; }}
    .doc-holder {{ color:var(--muted); }}
    .doc-summary {{ margin-left:auto; color:#334155; font-size:12px; }}
    .doc-note {{ margin:10px 0 0; color:var(--muted); font-size:11px; }}
    .guide-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:12px; }}
    .guide-card {{ background:var(--soft); padding:12px; border-radius:10px; }}
    .foot {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    .why h2 {{ margin:0 0 4px; font-size:18px; }}
    .why-item {{ margin-top:12px; }}
    .why-subject {{ font-weight:700; }}
    .why-rule {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .opts {{ margin:8px 0 0; padding-left:0; list-style:none; }}
    .opt {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:space-between; border:1px solid var(--line); border-radius:10px; padding:8px 10px; background:var(--soft); font-size:13px; }}
    .opt.chosen {{ border-color:var(--accent); background:#fff; font-weight:600; }}
    .opt-reason {{ flex-basis:100%; color:var(--muted); font-size:12px; font-weight:400; }}
    .checks {{ margin:12px 0 0; padding-left:0; list-style:none; font-size:12px; color:var(--muted); }}
    @media (max-width: 720px) {{
      .grid, .brief-split, .day-spread, .guide-grid {{ grid-template-columns:1fr; }}
    }}
    @media print {{
      .wrap {{ max-width:none; padding:10mm; }}
      .day, .essentials, .documents, .trip-brief, .book-cover, .place-guide {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class='wrap'>
    {contents}
    {brief}
    {days}
    {essentials}
    {documents}
    {guide}
    {decisions}
    <p class='foot'>Generated by AI Trip Planner (Layered Trip Book). Preview and PDF share this layout.</p>
    {share_section}
  </div>
  {auto}
</body>
</html>"""
