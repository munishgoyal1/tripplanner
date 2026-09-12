"""Trip itinerary export renderer (print/PDF-friendly HTML)."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import date
from html import escape
from typing import Any
from urllib.parse import quote

import httpx

from tripplanner import http_client
from tripplanner.caching import get_cache
from tripplanner.config import get_settings
from tripplanner.web import places_cache, trip_view

_STATIC_MAP_CACHE_TTL_S = 7 * 24 * 60 * 60
_STATIC_MAP_CACHE = get_cache(
  "google-static-map", default_ttl_seconds=_STATIC_MAP_CACHE_TTL_S, volatile=False
)


def _e(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _yes(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _route_points(
  pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]
) -> list[tuple[float, float]]:
  out: list[tuple[float, float]] = []
  for pid in pin_ids:
    p = pin_by_id.get(pid) or {}
    lat = p.get("lat")
    lng = p.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
      out.append((float(lat), float(lng)))
  return out


def format_export_day_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return raw
    return f"{parsed.strftime('%A')} · {parsed.day} {parsed.strftime('%B %Y')}"


def _minutes_label(minutes: int) -> str:
    minutes = int(minutes)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"{hours} hr"
    return f"{hours} hr {rest} min"


def _unique_texts(*values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _day_map_labels(stops: list[dict[str, Any]]) -> list[str]:
    hotels: list[str] = []
    for stop in stops:
        name = str(stop.get("name") or "").strip()
        if str(stop.get("kind") or "") == "hotel" and name and name not in hotels:
            hotels.append(name)
    visit = 0
    labels: list[str] = []
    for stop in stops:
        kind = str(stop.get("kind") or "")
        name = str(stop.get("name") or "").strip()
        if kind == "hotel":
            if len(hotels) <= 1:
                labels.append("H")
            else:
                labels.append(f"H{hotels.index(name) + 1}" if name in hotels else "H")
        elif kind == "airport":
            labels.append("A")
        elif kind in {"attraction", "meal", "restaurant"}:
            visit += 1
            labels.append(str(visit))
        else:
            labels.append("")
    return labels


def _timing_label(stop: dict[str, Any], *, is_first: bool, is_last: bool) -> str:
    kind = str(stop.get("kind") or "")
    role = str(stop.get("terminal_role") or "")
    if role == "arrival":
        return "Arrive"
    if role == "departure":
        return "Depart"
    if kind == "hotel" and is_first and is_last:
        return "Stay"
    if kind == "hotel" and is_first:
        return "Depart"
    if kind == "hotel" and is_last:
        return "Return"
    if kind == "flight":
        return "Depart"
    if kind == "transport":
        return "Travel"
    return "Arrive"


def _duration_text(stop: dict[str, Any]) -> str:
    operational = str(stop.get("operational_time_display") or "").strip()
    if operational:
        return operational
    kind = str(stop.get("kind") or "")
    duration = stop.get("duration_min")
    if kind == "hotel" or not isinstance(duration, (int, float)) or duration <= 0:
        return ""
    noun = "flight" if kind == "flight" else "transfer" if kind == "transport" else "visit"
    suffix = " est." if stop.get("duration_estimated") else ""
    return f"{_minutes_label(int(duration))} {noun}{suffix}"


def _leave_text(stop: dict[str, Any]) -> str:
    departure = str(stop.get("departure_time") or "").strip()
    if not departure:
        return ""
    kind = str(stop.get("kind") or "")
    prefix = "Arrive" if kind == "flight" else "Ends" if kind == "transport" else "Leave"
    return f"{prefix} {departure}"


def _quadratic_samples(
    start: tuple[float, float],
    end: tuple[float, float],
    sign: float,
) -> list[tuple[float, float]]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    span = math.hypot(dx, dy) or 1.0
    close = span < 52.0
    magnitude = (
        min(30.0, max(12.0, 480.0 / span)) if close else min(16.0, max(7.0, span * 0.09))
    )
    nx, ny = -dy / span, dx / span
    mid = (
        (start[0] + end[0]) / 2 + nx * magnitude * sign,
        (start[1] + end[1]) / 2 + ny * magnitude * sign,
    )
    samples: list[tuple[float, float]] = []
    steps = 10
    for index in range(steps + 1):
        t = index / steps
        rest = 1.0 - t
        samples.append((
            rest * rest * start[0] + 2 * rest * t * mid[0] + t * t * end[0],
            rest * rest * start[1] + 2 * rest * t * mid[1] + t * t * end[1],
        ))
    return samples


def _route_snippet_svg(
  coords: list[tuple[float, float]], labels: list[str] | None = None
) -> str:
  if len(coords) < 2:
    return ""
  width, height, pad = 240.0, 128.0, 16.0
  lats = [c[0] for c in coords]
  lngs = [c[1] for c in coords]
  min_lat, max_lat = min(lats), max(lats)
  min_lng, max_lng = min(lngs), max(lngs)
  lat_span = max(max_lat - min_lat, 1e-6)
  lng_span = max(max_lng - min_lng, 1e-6)

  def _xy(lat: float, lng: float) -> tuple[float, float]:
    x = pad + ((lng - min_lng) / lng_span) * (width - 2 * pad)
    y = pad + ((max_lat - lat) / lat_span) * (height - 2 * pad)
    return (round(x, 2), round(y, 2))

  points = [_xy(lat, lng) for lat, lng in coords]
  path_bits: list[str] = []
  for index in range(len(points) - 1):
    sign = 1.0 if index % 2 == 0 else -1.0
    samples = _quadratic_samples(points[index], points[index + 1], sign)
    path_bits.append(f"M {samples[0][0]:.2f} {samples[0][1]:.2f}")
    path_bits.extend(f"L {x:.2f} {y:.2f}" for x, y in samples[1:])
  nodes = []
  for i, (x, y) in enumerate(points, start=1):
    label = (labels[i - 1] if labels and i - 1 < len(labels) else str(i)) or str(i)
    nodes.append(
      f"<circle cx='{x}' cy='{y}' r='6.4' fill='#0f766e' stroke='white' stroke-width='2' />"
    )
    nodes.append(
      f"<text x='{x}' y='{y + 3.4}' text-anchor='middle' fill='white'"
      f" font-size='7.5' font-weight='700'>{_e(label)}</text>"
    )

  return (
    f"<svg viewBox='0 0 {int(width)} {int(height)}' class='route-svg' xmlns='http://www.w3.org/2000/svg'>"
    "<rect x='0' y='0' width='100%' height='100%' rx='10' fill='#f8fafc' stroke='#7dd3fc' />"
    f"<path d='{' '.join(path_bits)}' fill='none' stroke='#0369a1' stroke-width='2.8'"
    " stroke-linecap='round' stroke-linejoin='round' />"
    + "".join(nodes)
    + "</svg>"
  )


def export_stop_html(
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
    name = str(stop.get("name") or "")
    kind = str(stop.get("kind") or "other")
    display_name = f"Return to {name}" if circuit_return else name
    time = str(stop.get("time") or "")
    time_est = " est." if time and stop.get("time_estimated") else ""
    booked = "Confirmed" if stop.get("booked") else "Needs booking"
    if circuit_return or kind in {"airport", "station", "bus_station", "origin"}:
        booked = ""
    timing = "Return" if circuit_return else _timing_label(
        stop, is_first=is_first, is_last=is_last
    )
    kind_label = "Hotel return" if circuit_return else kind
    duration = _duration_text(stop)
    leave = _leave_text(stop)
    arrival = str(stop.get("arrival_time") or "")
    if arrival and arrival != time:
        leave = leave or f"Arrive {arrival}{' est.' if stop.get('arrival_time_estimated') else ''}"
    meta_bits = [timing, kind_label]
    if duration:
        meta_bits.append(duration)
    if leave:
        meta_bits.append(leave)
    meta_html = " · ".join(_e(bit) for bit in meta_bits if bit)

    travel = stop.get("travel_from_previous") or {}
    travel_html = ""
    if isinstance(travel, dict) and (travel.get("mode") or travel.get("duration_display")):
        parts = [
            str(travel.get("mode") or "").strip(),
            str(travel.get("distance_display") or "").strip(),
            str(travel.get("duration_display") or "").strip(),
        ]
        travel_line = " · ".join(part for part in parts if part)
        extra: list[str] = []
        detail = str(travel.get("detail") or "").strip()
        if detail:
            extra.append(detail)
        expected = str(stop.get("expected_arrival_time") or "").strip()
        if expected:
            buffer = str(stop.get("buffer_before_display") or "").strip()
            conflict = str(stop.get("timing_conflict_display") or "").strip()
            suffix = ""
            if buffer and time:
                suffix = f" · {buffer} free before {time}"
            elif conflict:
                suffix = f" · schedule is {conflict} too tight"
            extra.append(f"Est. arrive {expected}{suffix}")
        extra_html = "".join(f"<div class='travel-extra'>{_e(item)}</div>" for item in extra)
        travel_html = f"<div class='travel'>{_e(travel_line)}{extra_html}</div>"

    place_meta_html = ""
    photo_html = ""
    if name and kind in {"hotel", "attraction", "meal", "restaurant"} and not circuit_return:
        place = places_cache.get_details(name, destination) or {}
        address = str(place.get("address") or "")
        rating = stop.get("rating")
        if not isinstance(rating, (int, float)):
            rating = place.get("rating")
        review_count = stop.get("review_count")
        details = [address] if address else []
        if isinstance(rating, (int, float)):
            reviews = ""
            if isinstance(review_count, (int, float)) and review_count > 0:
                reviews = f" · {int(review_count)} reviews"
            details.append(f"Rating {rating:g}{reviews}")
        popularity = stop.get("popularity_score")
        if isinstance(popularity, (int, float)) and kind == "attraction":
            details.append(f"Must-visit score {int(popularity)}/100")
        if details:
            place_meta_html = f"<div class='place-meta'>{_e(' · '.join(details))}</div>"
        flagship_key = name.strip().casefold()
        if include_photos and flagship_key not in seen_photos:
            photos = places_cache.get_photos(name, destination, max_photos=1)
            if photos:
                seen_photos.add(flagship_key)
                photo_html = (
                    f"<div class='stop-photo-wrap'><img class='stop-photo' src='{_e(photos[0])}' alt='{_e(name)}' /></div>"
                )

    chips: list[str] = []
    if include_budgets and not circuit_return and stop.get("cost_display"):
        chips.append(str(stop.get("cost_display")))
    hours = str(stop.get("opening_hours") or "").strip()
    if hours and not circuit_return:
        chips.append(hours)
    chips_html = (
        "<div class='chips'>"
        + "".join(f"<span class='chip'>{_e(chip)}</span>" for chip in chips)
        + "</div>"
        if chips
        else ""
    )
    concerns = _unique_texts(stop.get("concern"))
    notes = [
        text
        for text in _unique_texts(stop.get("note"), "" if circuit_return else stop.get("insight"))
        if text.casefold() not in {"start from your stay", "return to your stay"}
        and text.casefold() not in {item.casefold() for item in concerns}
    ]
    concern_html = "".join(f"<div class='concern'>{_e(text)}</div>" for text in concerns)
    note_html = "".join(f"<div class='note'>{_e(text)}</div>" for text in notes)
    ref = str(stop.get("booking_ref") or "").strip()
    ticket = str(stop.get("ticket_url") or "").strip()
    ref_html = ""
    if ref:
        ref_html += f"<div class='ref'>{_e(ref)}</div>"
    if ticket:
        ref_html += (
            f"<div class='ref'><a href='{_e(ticket)}'>{_e(ticket)}</a></div>"
        )
    marker_html = (
        f"<span class='ord'>{_e(marker)}</span>" if marker else "<span class='ord ghost'></span>"
    )
    time_html = (
        f"<span class='when'><strong>{_e(time)}</strong>{_e(time_est)}</span>" if time else ""
    )
    state_html = f"<span class='state'>{_e(booked)}</span>" if booked else ""
    hotel_class = " hotel" if kind == "hotel" else ""
    return (
        f"<li class='stop layered{hotel_class}'>"
        f"{travel_html}"
        "<div class='stop-card'>"
        "<div class='stop-main'>"
        f"<div class='stop-line'>{marker_html}{time_html}"
        f"<span class='name'>{_e(display_name)}</span>{state_html}</div>"
        f"<div class='meta'>{meta_html}</div>"
        f"{place_meta_html}{chips_html}{concern_html}{note_html}{ref_html}"
        "</div>"
        f"{photo_html}</div></li>"
    )


def _qr_image_url(value: str) -> str:
  if not value:
    return ""
  return (
    "https://api.qrserver.com/v1/create-qr-code/?size=120x120&margin=2&data="
    + quote(value, safe="")
  )


def _static_map_data_uri(
    pin_ids: list[str], pin_by_id: dict[str, dict[str, Any]]
  ) -> str:
    from tripplanner.places_budget import paid_provider_authorized

    if not paid_provider_authorized():
      return ""
    settings = get_settings()
    key = settings.google_places_api_key.strip() if settings.enable_google_maps else ""
    points = [pin_by_id.get(pin_id) or {} for pin_id in pin_ids]
    coords = [
      (float(point["lat"]), float(point["lng"]))
      for point in points
      if isinstance(point.get("lat"), (int, float))
      and isinstance(point.get("lng"), (int, float))
    ]
    if not key or len(coords) < 2:
      return ""

    cache_key = hashlib.sha256(
      json.dumps(coords, separators=(",", ":")).encode()
    ).hexdigest()
    cached = _STATIC_MAP_CACHE.get(cache_key)
    if isinstance(cached, str):
      from tripplanner.provider_usage import record_cache_hit

      record_cache_hit(provider="google", operation="static_map")
      return cached

    path = "color:0x0369a1ff|weight:4|" + "|".join(
      f"{lat:.6f},{lng:.6f}" for lat, lng in coords
    )
    markers = [
      f"color:0x0d9488|label:{min(index, 9)}|{lat:.6f},{lng:.6f}"
      for index, (lat, lng) in enumerate(coords, start=1)
    ]
    params: list[tuple[str, str]] = [
      ("size", "640x320"),
      ("scale", "2"),
      ("maptype", "roadmap"),
      ("path", path),
      *(("markers", marker) for marker in markers),
      ("key", key),
    ]
    try:
      response = http_client.get(
        "https://maps.googleapis.com/maps/api/staticmap",
        params=params,
        timeout=12,
      )
      response.raise_for_status()
      content_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
      if not content_type.startswith("image/"):
        return ""
      encoded = base64.b64encode(response.content).decode("ascii")
      result = f"data:{content_type};base64,{encoded}"
      _STATIC_MAP_CACHE.set(
        cache_key,
        result,
        ttl_seconds=_STATIC_MAP_CACHE_TTL_S,
      )
      return result
    except httpx.HTTPError:
      return ""


def _decisions_section(trip: dict[str, Any]) -> str:
    """The comparisons behind the plan, printed with the plan.

    Carried through the same sanitiser the share link uses, so an exported page
    can never leak more than a shared one.
    """
    from tripplanner.decisions.provenance import build_provenance
    from tripplanner.decisions.rules import money
    from tripplanner.web.share import sanitize_decisions

    decisions = sanitize_decisions(trip.get("decisions"))
    checks = build_provenance(trip)
    if not decisions and not checks:
        return ""
    blocks: list[str] = []
    for decision in decisions:
        rows: list[str] = []
        for option in decision.get("options") or []:
            price = option.get("price")
            if isinstance(price, dict) and price.get("amount") is not None:
                price_text = money(float(price["amount"]), str(price.get("currency") or "EUR"))
                source = option.get("source") or {}
                provider = str(source.get("provider") or "")
                if provider:
                    price_text += f" · {provider}"
            else:
                price_text = "no fare source"
            chosen = option.get("id") == decision.get("chosen_option_id")
            reason = "" if chosen else str(option.get("rejected_because") or "")
            rows.append(
                "<li class='opt{cls}'><span class='opt-label'>{label}</span>"
                "<span class='opt-price'>{price}</span>{reason}</li>".format(
                    cls=" chosen" if chosen else "",
                    label=_e(str(option.get("label") or "")),
                    price=_e(price_text),
                    reason=f"<div class='opt-reason'>{_e(reason)}</div>" if reason else "",
                )
            )
        blocks.append(
            "<div class='why-item'><div class='why-subject'>{subject}</div>"
            "<div class='why-rule'>{rule}</div><ul class='opts'>{rows}</ul></div>".format(
                subject=_e(str(decision.get("subject") or "")),
                rule=_e(str(decision.get("rule_text") or "")),
                rows="".join(rows),
            )
        )
    checked = "".join(
        "<li class='check{cls}'>{text}</li>".format(
            cls="" if row["current"] else " stale",
            text=_e(str(row["text"])),
        )
        for row in checks
    )
    if checked:
        checked = f"<ul class='checks'>{checked}</ul>"
    return (
        "<section class='why'><h2>Why it is planned this way</h2>"
        f"{''.join(blocks)}{checked}</section>"
    )


#: Download formats. UI offers Standard (day-by-day, same facts as the
#: itinerary panel) and Trip Book. ``detailed`` remains an alias of Standard
#: for older links. Trip Card stays renderable but is not offered in the UI.
#: Standard and Trip Book always include numbered day-circuit diagrams.
TEMPLATES = ("standard", "detailed", "trip_book", "trip_card")
_MAP_TEMPLATES = {"standard", "detailed", "trip_book"}


def _essentials_section(trip: dict[str, Any], *, include_budgets: bool = False) -> str:
    """Weather and budget facts the trip already has -- nothing invented.

    Lab 5's mockup carried emergency-contact numbers, but nothing in this app
    looks those up for real, so they stay out rather than being fabricated.
    """
    weather = trip_view.build_weather(trip)
    cost_breakdown = trip.get("cost_breakdown")
    symbol = trip_view.currency_symbol(trip)

    blocks: list[str] = []
    if weather and weather.get("days"):
        highs = [d["high_c"] for d in weather["days"] if d.get("high_c") is not None]
        lows = [d["low_c"] for d in weather["days"] if d.get("low_c") is not None]
        range_text = f"{min(lows):.0f}–{max(highs):.0f}°C" if highs and lows else ""
        packing = "; ".join(weather.get("packing_advice") or [])
        blocks.append(
            "<div class='essential'><div class='k'>Weather</div>"
            f"<div class='v'>{_e(range_text)}{' · ' if range_text else ''}"
            f"{_e(weather.get('source_label') or '')}</div>"
            + (f"<div class='note'>{_e(packing)}</div>" if packing else "")
            + "</div>"
        )
    if include_budgets and isinstance(cost_breakdown, dict) and cost_breakdown:
        items = " · ".join(
            f"{_e(str(key).replace('_', ' ').title())} {_e(trip_view.fmt_money(value, symbol))}"
            for key, value in cost_breakdown.items()
            if isinstance(value, (int, float))
        )
        if items:
            blocks.append(
                f"<div class='essential'><div class='k'>Budget breakdown</div><div class='v'>{items}</div></div>"
            )
    if not blocks:
        return ""
    return f"<section class='essentials'><h2>Trip essentials</h2>{''.join(blocks)}</section>"


_DOCUMENT_SUMMARY_FIELDS: dict[str, tuple[str, ...]] = {
    "insurance": ("provider", "assistance_phone"),
    "passport": ("expiry",),
    "visa": ("destination_country", "valid_to"),
    "vaccination": ("vaccine", "expiry"),
    "licence": ("expiry",),
    "idp": ("expiry",),
    "loyalty": ("program", "tier"),
}


def _documents_wallet_section(trip: dict[str, Any]) -> str:
    """Saved travel documents relevant to this trip, as a readiness checklist.

    Names and a couple of safe reference fields only. Identity numbers stay
    out of a file that may be printed, emailed, or left on a table.
    """
    from tripplanner.web import travel_documents

    trip_id = str(trip.get("trip_id") or "")
    records = [
        record
        for record in travel_documents.list_documents(scope=None)
        if str(record.get("scope") or "traveler") != "trip"
        or str(record.get("trip_id") or "") == trip_id
    ]
    if not records:
        return ""

    rows: list[str] = []
    for record in records:
        doc_type = str(record.get("type") or "")
        label = travel_documents.TYPE_LABELS.get(doc_type, doc_type.title() or "Document")
        holder = str(record.get("traveller_name") or "").strip() or "Traveller"
        fields = record.get("fields") or {}
        summary = " · ".join(
            str(fields[key])
            for key in _DOCUMENT_SUMMARY_FIELDS.get(doc_type, ())
            if fields.get(key)
        )
        rows.append(
            "<li class='doc-row'><span class='doc-type'>{label}</span>"
            "<span class='doc-holder'>{holder}</span>"
            "<span class='doc-summary'>{summary}</span></li>".format(
                label=_e(label), holder=_e(holder), summary=_e(summary or "On file")
            )
        )
    return (
        "<section class='documents'><h2>Travel documents on file</h2>"
        f"<ul class='doc-list'>{''.join(rows)}</ul>"
        "<p class='doc-note'>Reference numbers are kept out of this file by design.</p>"
        "</section>"
    )


def _condensed_day_rows(
    days: list[dict[str, Any]],
    *,
    include_photos: bool,
    destination: str,
    seen_photos: set[str],
) -> str:
    """One compact row per day for the Trip Card format: date, title, top stops."""
    rows: list[str] = []
    for day in days:
        day_num = int(day.get("day") or 0)
        stops = [s for s in (day.get("stops") or []) if isinstance(s, dict)]
        names = [str(s.get("name") or "").strip() for s in stops if s.get("name")]
        headline_stop = next(
            (s for s in stops if _stop_flagship_key(s) not in seen_photos), None
        )
        thumb = ""
        if include_photos and headline_stop:
            key = _stop_flagship_key(headline_stop)
            photos = places_cache.get_photos(str(headline_stop.get("name") or ""), destination, max_photos=1)
            if photos:
                seen_photos.add(key)
                thumb = f"<img class='card-thumb' src='{_e(photos[0])}' alt='' />"
        rows.append(
            "<li class='card-row'>{thumb}"
            "<div class='card-row-main'>"
            "<div class='card-row-head'><span class='card-day'>Day {day_num}</span>"
            "<span class='card-date'>{date}</span></div>"
            "<div class='card-title'>{title}</div>"
            "<div class='card-stops'>{stops}</div>"
            "</div></li>".format(
                thumb=thumb,
                day_num=day_num,
                date=_e(format_export_day_date(str(day.get("date") or ""))),
                title=_e(day.get("title") or ""),
                stops=_e(" · ".join(names[:4])),
            )
        )
    return f"<ol class='card-days'>{''.join(rows)}</ol>"


def _stop_flagship_key(stop: dict[str, Any]) -> str:
    return str(stop.get("name") or "").strip().casefold()


def build_export_html(
    trip: dict[str, Any] | None,
    *,
    include_photos: bool,
    include_map_circuit: bool,
    template: str = "standard",
    auto_print: bool = False,
    share_url: str = "",
    include_budgets: bool = False,
) -> str:
    """Render a self-contained, print-ready itinerary HTML document."""
    if not trip:
        return """<!doctype html><html><head><meta charset='utf-8'><title>Trip Export</title></head><body><p>No active trip to export.</p></body></html>"""

    template_key = str(template or "standard").strip().lower()
    if template_key == "detailed":
        template_key = "standard"
    if template_key not in TEMPLATES:
        template_key = "standard"
    include_map_circuit = template_key in _MAP_TEMPLATES

    itinerary = trip_view.build_itinerary(trip)
    map_vm = trip_view.build_map_view(trip) if include_map_circuit else {"days": [], "pins": []}
    pin_by_id = {p.get("id"): p for p in (map_vm.get("pins") or [])}
    route_by_day = {int(d.get("day") or 0): d for d in (map_vm.get("days") or [])}
    seen_photos: set[str] = set()

    destination = str(trip.get("destination") or "")
    origin = str(trip.get("origin") or "")
    depart = str(trip.get("departure_date") or "")
    ret = str(trip.get("return_date") or "")
    travelers = str(trip.get("travelers") or "")
    symbol = trip_view.currency_symbol(trip)
    total_display = trip_view.fmt_money(trip.get("total_cost"), symbol)

    if template_key == "trip_book":
        from tripplanner.web.itinerary_trip_book import render_layered_trip_book

        return render_layered_trip_book(
            trip,
            include_photos=include_photos,
            include_map_circuit=include_map_circuit,
            include_budgets=include_budgets,
            auto_print=auto_print,
            share_url=share_url,
            itinerary=itinerary,
            pin_by_id=pin_by_id,
            route_by_day=route_by_day,
            destination=destination,
            origin=origin,
            depart=depart,
            ret=ret,
            travelers=travelers,
            total_display=total_display if include_budgets else "",
            seen_photos=seen_photos,
        )

    day_blocks: list[str] = []
    # Trip Card renders its own condensed rows below instead of full day
    # sections, so skip this loop entirely rather than build unused HTML
    # and burn photo-cache lookups on content that is never shown.
    for day in ([] if template_key == "trip_card" else (itinerary.get("days") or [])):
        day_num = int(day.get("day") or 0)
        route = route_by_day.get(day_num) if include_map_circuit else None
        maps_url = str(day.get("google_maps_url") or "")

        stops = [s for s in (day.get("stops") or []) if isinstance(s, dict)]
        labels = _day_map_labels(stops)
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
        stops_html = []
        for idx, stop in enumerate(stops):
            stops_html.append(
                export_stop_html(
                    stop,
                    marker=labels[idx],
                    is_first=idx == 0,
                    is_last=idx == len(stops) - 1,
                    circuit_return=idx == circuit_return_index,
                    include_photos=include_photos,
                    include_budgets=include_budgets,
                    destination=destination,
                    seen_photos=seen_photos,
                )
            )

        circuit_html = ""
        if include_map_circuit and route:
            pin_names = [
                str(pin_by_id.get(pid, {}).get("name") or pid)
                for pid in (route.get("pin_ids") or [])
            ]
            if pin_names:
                circuit = " -> ".join(_e(n) for n in pin_names)
                stats = route.get("route") or {}
                pin_ids = list(route.get("pin_ids") or [])
                visit = 0
                circuit_labels: list[str] = []
                for pid in pin_ids:
                    kind = str((pin_by_id.get(pid) or {}).get("kind") or "")
                    if kind == "hotel":
                        circuit_labels.append("H")
                    else:
                        visit += 1
                        circuit_labels.append(str(visit))
                snippet = _route_snippet_svg(
                    _route_points(pin_ids, pin_by_id),
                    circuit_labels,
                )
                static_map = _static_map_data_uri(route.get("pin_ids") or [], pin_by_id)
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
                    + _e(_qr_image_url(maps_url))
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
                    "<div class='circuit-title'>Daily map circuit</div>"
                    f"{map_visual}"
                    f"<div class='circuit-line'>{circuit}</div>"
                  f"<div class='circuit-stats'>{stats_html}</div>"
                    f"<div class='circuit-actions'>{maps_link_html}{qr_html}</div>"
                    "</div>"
                )

        schedule = day.get("schedule") or {}
        span = ""
        if schedule.get("start") or schedule.get("end"):
            span = f"{schedule.get('start') or '—'}–{schedule.get('end') or '—'}"
        travel = str(
            schedule.get("travel_duration_display")
            or (day.get("route") or {}).get("duration_display")
            or ""
        )
        distance = str((day.get("route") or {}).get("distance_display") or "")
        timing = " · ".join(part for part in (span, travel, distance) if part)
        day_date = format_export_day_date(str(day.get("date") or ""))
        day_blocks.append(
            """
            <section class='day'>
              <div class='day-head'>
                <h2>Day {day_num}: {title}</h2>
                <div class='day-date'>{date}{timing}</div>
              </div>
              {summary}
              {circuit}
              <ol class='stops'>{stops}</ol>
            </section>
            """.format(
                day_num=day_num,
                title=_e(day.get("title") or f"Day {day_num}"),
                date=_e(day_date),
                timing=f" · {_e(timing)}" if timing else "",
                summary=(f"<p class='summary'>{_e(day.get('summary') or '')}</p>" if day.get("summary") else ""),
                circuit=circuit_html,
                stops="".join(stops_html),
            )
        )

    auto = "<script>window.addEventListener('load',()=>window.print());</script>" if auto_print else ""
    if template_key == "trip_book":
      accent = "#7c3aed"
      hero_bg = "linear-gradient(135deg,#faf5ff,#eef2ff)"
      circuit_bg = "#f5f3ff"
      title_suffix = "Trip Book"
    elif template_key == "trip_card":
      accent = "#b45309"
      hero_bg = "linear-gradient(135deg,#fffbeb,#fff7ed)"
      circuit_bg = "#fffbeb"
      title_suffix = "Trip Card"
    else:
      accent = "#0d9488"
      hero_bg = "linear-gradient(135deg,#f8fafc,#eef2ff)"
      circuit_bg = "#ecfeff"
      title_suffix = "Standard"

    card_days_html = ""
    if template_key == "trip_card":
        card_days_html = _condensed_day_rows(
            itinerary.get("days") or [],
            include_photos=include_photos,
            destination=destination,
            seen_photos=seen_photos,
        )

    overview_map_html = ""
    if template_key == "trip_book":
        overview_map = _static_map_data_uri(list(pin_by_id.keys()), pin_by_id)
        if overview_map:
            overview_map_html = (
                "<section class='overview-map'><h2>Trip overview</h2>"
                f"<img class='route-map' src='{_e(overview_map)}' alt='Full trip overview map' />"
                "</section>"
            )

    essentials_section = (
        _essentials_section(trip, include_budgets=include_budgets)
        if template_key != "trip_card"
        else ""
    )
    documents_section = _documents_wallet_section(trip) if template_key == "trip_book" else ""

    # Optional "Continue Planning" CTA block injected above the footer.
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

    decisions_section = (
        _decisions_section(trip) if template_key in {"standard", "trip_book"} else ""
    )

    budget_cell = (
        f"<div><div class='k'>Total Cost</div><div class='v'>{_e(total_display)}</div></div>"
        if include_budgets
        else ""
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{_e(destination or 'Trip')} · Itinerary Export ({_e(title_suffix)})</title>
  <style>
    :root {{ --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --soft:#f8fafc; --accent:{accent}; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: "Segoe UI", "Inter", sans-serif; color:var(--ink); background:#fff; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .hero {{ border:1px solid var(--line); border-radius:16px; padding:18px; background:{hero_bg}; }}
    .hero h1 {{ margin:0; font-size:28px; }}
    .grid {{ display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .k {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
    .v {{ font-weight:600; }}
    .day {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; padding:14px; page-break-inside:avoid; }}
    .day-head {{ display:flex; justify-content:space-between; gap:10px; align-items:baseline; }}
    .day h2 {{ margin:0; font-size:20px; }}
    .day-date {{ color:var(--muted); font-size:13px; }}
    .summary {{ margin:10px 0 8px; color:#334155; }}
    .circuit {{ margin:8px 0 10px; background:{circuit_bg}; border:1px solid #bae6fd; border-radius:10px; padding:10px; }}
    .circuit-title {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:#0c4a6e; }}
    .route-svg {{ margin-top:8px; width:100%; max-width:330px; height:auto; }}
    .route-map {{ display:block; margin-top:8px; width:100%; max-width:640px; height:auto; border-radius:10px; border:1px solid #bae6fd; }}
    .circuit-line {{ margin-top:5px; font-size:14px; color:#0f172a; }}
    .circuit-stats {{ margin-top:5px; font-size:12px; color:#0369a1; }}
    .circuit-actions {{ margin-top:8px; display:flex; align-items:center; gap:10px; }}
    .maps-link {{ color:#0f766e; font-size:12px; font-weight:600; text-decoration:none; }}
    .maps-link:hover {{ text-decoration:underline; }}
    .qr-wrap {{ display:flex; align-items:center; gap:6px; margin-left:auto; }}
    .qr {{ width:54px; height:54px; border-radius:8px; border:1px solid #bae6fd; background:#fff; }}
    .qr-cap {{ color:#0369a1; font-size:11px; }}
    .stops {{ margin:0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:10px; }}
    .stop {{ display:flex; flex-direction:column; gap:6px; }}
    .stop-card {{ display:flex; gap:12px; justify-content:space-between; border:1px solid var(--line); border-radius:10px; padding:10px; background:var(--soft); }}
    .stop-main {{ min-width:0; flex:1; }}
    .stop-line {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
    .ord {{ display:inline-grid; place-items:center; width:22px; height:22px; border-radius:999px; background:var(--accent); color:#fff; font-size:11px; font-weight:700; }}
    .ord.ghost {{ background:#e2e8f0; color:transparent; }}
    .name {{ font-weight:700; }}
    .when {{ color:var(--muted); font-size:12px; }}
    .state {{ margin-left:auto; font-size:11px; font-weight:700; color:#92400e; }}
    .meta {{ margin-top:4px; color:var(--muted); font-size:12px; }}
    .travel {{ margin:0 0 2px 12px; color:#0f766e; font-size:12px; font-weight:600; }}
    .travel-extra {{ margin-top:2px; font-weight:400; color:var(--muted); }}
    .note {{ margin-top:6px; color:#334155; font-size:13px; }}
    .concern {{ margin-top:6px; color:#be123c; font-size:12px; font-weight:600; }}
    .chips {{ margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-size:11px; color:#334155; background:#fff; }}
    .ref {{ margin-top:4px; font-size:12px; color:#0f172a; }}
    .place-meta {{ margin-top:5px; color:#475569; font-size:12px; }}
    .stop-photo-wrap {{ width:120px; flex-shrink:0; }}
    .stop-photo {{ width:120px; height:84px; object-fit:cover; border-radius:8px; border:1px solid var(--line); }}
    .foot {{ margin-top:18px; color:var(--muted); font-size:12px; }}
    .why {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; padding:14px; page-break-inside:avoid; }}
    .why h2 {{ margin:0 0 4px; font-size:18px; }}
    .why-item {{ margin-top:12px; }}
    .why-subject {{ font-weight:700; }}
    .why-rule {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .opts {{ margin:8px 0 0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:6px; }}
    .opt {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:space-between; border:1px solid var(--line); border-radius:10px; padding:8px 10px; background:var(--soft); font-size:13px; }}
    .opt.chosen {{ border-color:var(--accent); background:#fff; font-weight:600; }}
    .opt-price {{ color:var(--muted); }}
    .opt-reason {{ flex-basis:100%; color:var(--muted); font-size:12px; font-weight:400; }}
    .checks {{ margin:12px 0 0; padding-left:0; list-style:none; font-size:12px;
      color:var(--muted); }}
    .checks .stale {{ color:#92400e; }}
    .overview-map {{ margin-top:20px; }}
    .overview-map h2 {{ margin:0 0 8px; font-size:18px; }}
    .essentials, .documents {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; padding:14px; page-break-inside:avoid; }}
    .essentials h2, .documents h2 {{ margin:0 0 10px; font-size:18px; }}
    .essential {{ margin-top:8px; }}
    .essential .note {{ margin-top:3px; color:#334155; font-size:13px; }}
    .doc-list {{ margin:0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:8px; }}
    .doc-row {{ display:flex; flex-wrap:wrap; gap:10px; align-items:baseline; border:1px solid var(--line); border-radius:10px; padding:8px 10px; background:var(--soft); font-size:13px; }}
    .doc-type {{ font-weight:700; min-width:140px; }}
    .doc-holder {{ color:var(--muted); }}
    .doc-summary {{ margin-left:auto; color:#334155; font-size:12px; }}
    .doc-note {{ margin:10px 0 0; color:var(--muted); font-size:11px; }}
    .card-days {{ margin:16px 0 0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:10px; }}
    .card-row {{ display:flex; gap:12px; border:1px solid var(--line); border-radius:12px; padding:10px; align-items:center; page-break-inside:avoid; }}
    .card-thumb {{ width:56px; height:56px; border-radius:8px; object-fit:cover; flex-shrink:0; }}
    .card-row-main {{ min-width:0; flex:1; }}
    .card-row-head {{ display:flex; justify-content:space-between; gap:8px; }}
    .card-day {{ font-weight:700; color:var(--accent); font-size:13px; }}
    .card-date {{ color:var(--muted); font-size:12px; }}
    .card-title {{ font-weight:600; margin-top:2px; }}
    .card-stops {{ margin-top:3px; color:var(--muted); font-size:12px; }}
    @media print {{
      .wrap {{ max-width:none; padding:10mm; }}
      .day, .card-row, .essentials, .documents {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class='wrap'>
    <section class='hero'>
      <h1>{_e(destination or 'Trip Itinerary')}</h1>
      <div class='grid'>
        <div><div class='k'>From</div><div class='v'>{_e(origin or '—')}</div></div>
        <div><div class='k'>Dates</div><div class='v'>{_e(depart)} → {_e(ret)}</div></div>
        <div><div class='k'>Travelers</div><div class='v'>{_e(travelers or '—')}</div></div>
        <div><div class='k'>Status</div><div class='v'>{_e(str(trip.get('status') or 'draft').title())}</div></div>
        {budget_cell}
        <div><div class='k'>Days</div><div class='v'>{len(itinerary.get('days') or [])}</div></div>
      </div>
    </section>
    {overview_map_html}
    {card_days_html}
    {''.join(day_blocks)}
    {essentials_section}
    {documents_section}
    {decisions_section}
    <p class='foot'>Generated by AI Trip Planner ({_e(title_suffix)} format). Preview and PDF share this layout.</p>
    {share_section}
  </div>
  {auto}
</body>
</html>"""


def parse_export_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return _yes(value)

