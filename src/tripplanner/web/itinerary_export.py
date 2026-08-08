"""Trip itinerary export renderer (print/PDF-friendly HTML)."""

from __future__ import annotations

import base64
from html import escape
import os
from typing import Any
from urllib.parse import quote

import requests

from tripplanner.web import places_cache, trip_view


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


def _route_snippet_svg(coords: list[tuple[float, float]]) -> str:
  if len(coords) < 2:
    return ""
  width, height, pad = 220.0, 116.0, 12.0
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
  poly = " ".join(f"{x},{y}" for x, y in points)
  nodes = []
  for i, (x, y) in enumerate(points, start=1):
    nodes.append(
      f"<circle cx='{x}' cy='{y}' r='5.5' fill='#0d9488' stroke='white' stroke-width='1.5' />"
    )
    nodes.append(
      f"<text x='{x}' y='{y + 3.2}' text-anchor='middle' fill='white' font-size='7' font-weight='700'>{i}</text>"
    )

  return (
    f"<svg viewBox='0 0 {int(width)} {int(height)}' class='route-svg' xmlns='http://www.w3.org/2000/svg'>"
    "<rect x='0' y='0' width='100%' height='100%' rx='10' fill='#f8fafc' stroke='#bae6fd' />"
    f"<polyline points='{poly}' fill='none' stroke='#0369a1' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' />"
    + "".join(nodes)
    + "</svg>"
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
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    points = [pin_by_id.get(pin_id) or {} for pin_id in pin_ids]
    coords = [
      (float(point["lat"]), float(point["lng"]))
      for point in points
      if isinstance(point.get("lat"), (int, float))
      and isinstance(point.get("lng"), (int, float))
    ]
    if not key or len(coords) < 2:
      return ""

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
      response = requests.get(
        "https://maps.googleapis.com/maps/api/staticmap",
        params=params,
        timeout=12,
      )
      response.raise_for_status()
      content_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
      if not content_type.startswith("image/"):
        return ""
      encoded = base64.b64encode(response.content).decode("ascii")
      return f"data:{content_type};base64,{encoded}"
    except requests.RequestException:
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


def build_export_html(
    trip: dict[str, Any] | None,
    *,
    include_photos: bool,
    include_map_circuit: bool,
    template: str = "detailed",
    auto_print: bool = False,
    share_url: str = "",
) -> str:
    """Render a self-contained, print-ready itinerary HTML document."""
    if not trip:
        return """<!doctype html><html><head><meta charset='utf-8'><title>Trip Export</title></head><body><p>No active trip to export.</p></body></html>"""

    itinerary = trip_view.build_itinerary(trip)
    map_vm = trip_view.build_map_view(trip) if include_map_circuit else {"days": [], "pins": []}
    pin_by_id = {p.get("id"): p for p in (map_vm.get("pins") or [])}
    route_by_day = {int(d.get("day") or 0): d for d in (map_vm.get("days") or [])}

    destination = str(trip.get("destination") or "")
    origin = str(trip.get("origin") or "")
    depart = str(trip.get("departure_date") or "")
    ret = str(trip.get("return_date") or "")
    travelers = str(trip.get("travelers") or "")
    symbol = trip_view.currency_symbol(trip)
    total_display = trip_view.fmt_money(trip.get("total_cost"), symbol)

    template_key = str(template or "detailed").strip().lower()
    if template_key not in {"minimal", "detailed", "family"}:
      template_key = "detailed"

    day_blocks: list[str] = []
    for day in itinerary.get("days") or []:
        day_num = int(day.get("day") or 0)
        route = route_by_day.get(day_num) if include_map_circuit else None
        maps_url = str(day.get("google_maps_url") or "")

        stops_html = []
        for idx, stop in enumerate(day.get("stops") or [], start=1):
            name = str(stop.get("name") or "")
            kind = str(stop.get("kind") or "other")
            time = str(stop.get("time") or "")
            note = str(stop.get("note") or "")
            booked = "Booked" if stop.get("booked") else "Pending"
            photo_html = ""
            place_meta_html = ""
            if name and kind in {"hotel", "attraction", "meal", "restaurant"}:
              place = places_cache.get_summary(name, destination) or {}
              address = str(place.get("address") or "")
              rating = place.get("rating")
              details = [address] if address else []
              if isinstance(rating, (int, float)):
                details.append(f"Rating {rating:g}")
              if details:
                place_meta_html = f"<div class='place-meta'>{_e(' · '.join(details))}</div>"
            if include_photos and kind in {"hotel", "attraction", "meal", "restaurant"} and name:
                photos = places_cache.get_photos(name, destination, max_photos=1)
                if photos:
                    photo_html = (
                        f"<div class='stop-photo-wrap'><img class='stop-photo' src='{_e(photos[0])}' alt='{_e(name)}' /></div>"
                    )
            stops_html.append(
                """
                <li class='stop'>
                  <div class='stop-main'>
                    <div class='stop-line'><span class='ord'>{ord}</span><span class='name'>{name}</span></div>
                    <div class='meta'>{kind}{time_sep}{time} · {booked}</div>
                        {place_meta}
                    {note_html}
                  </div>
                  {photo}
                </li>
                """.format(
                    ord=idx,
                    name=_e(name),
                    kind=_e(kind.title()),
                    time_sep=" @ " if time else "",
                    time=_e(time),
                    booked=_e(booked),
                    note_html=(f"<div class='note'>{_e(note)}</div>" if note else ""),
                    place_meta=place_meta_html,
                    photo=photo_html,
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
                snippet = _route_snippet_svg(
                    _route_points(route.get("pin_ids") or [], pin_by_id)
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

        day_blocks.append(
            """
            <section class='day'>
              <div class='day-head'>
                <h2>Day {day_num}: {title}</h2>
                <div class='day-date'>{date}</div>
              </div>
              {summary}
              {circuit}
              <ol class='stops'>{stops}</ol>
            </section>
            """.format(
                day_num=day_num,
                title=_e(day.get("title") or f"Day {day_num}"),
                date=_e(day.get("date") or ""),
                summary=(f"<p class='summary'>{_e(day.get('summary') or '')}</p>" if day.get("summary") else ""),
                circuit=circuit_html,
                stops="".join(stops_html),
            )
        )

    auto = "<script>window.addEventListener('load',()=>window.print());</script>" if auto_print else ""
    if template_key == "minimal":
      accent = "#334155"
      hero_bg = "linear-gradient(135deg,#f8fafc,#f1f5f9)"
      circuit_bg = "#f8fafc"
      title_suffix = "Minimal"
    elif template_key == "family":
      accent = "#7c3aed"
      hero_bg = "linear-gradient(135deg,#faf5ff,#eef2ff)"
      circuit_bg = "#f5f3ff"
      title_suffix = "Family"
    else:
      accent = "#0d9488"
      hero_bg = "linear-gradient(135deg,#f8fafc,#eef2ff)"
      circuit_bg = "#ecfeff"
      title_suffix = "Detailed"

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

    decisions_section = _decisions_section(trip)

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
    .stop {{ display:flex; gap:12px; justify-content:space-between; border:1px solid var(--line); border-radius:10px; padding:10px; background:var(--soft); }}
    .stop-main {{ min-width:0; flex:1; }}
    .stop-line {{ display:flex; align-items:center; gap:8px; }}
    .ord {{ display:inline-grid; place-items:center; width:22px; height:22px; border-radius:999px; background:var(--accent); color:#fff; font-size:12px; font-weight:700; }}
    .name {{ font-weight:700; }}
    .meta {{ margin-top:4px; color:var(--muted); font-size:12px; }}
    .note {{ margin-top:6px; color:#334155; font-size:13px; }}
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
    @media print {{
      .wrap {{ max-width:none; padding:10mm; }}
      .day {{ break-inside: avoid; }}
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
        <div><div class='k'>Total Cost</div><div class='v'>{_e(total_display)}</div></div>
        <div><div class='k'>Days</div><div class='v'>{len(itinerary.get('days') or [])}</div></div>
      </div>
    </section>
    {''.join(day_blocks)}
    {decisions_section}
    <p class='foot'>Generated by AI Trip Planner ({_e(title_suffix)} template). Tip: Use browser Print → Save as PDF for a carry-along copy.</p>
    {share_section}
  </div>
  {auto}
</body>
</html>"""


def parse_export_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return _yes(value)

