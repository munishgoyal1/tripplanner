"""Trip itinerary export renderer (print/PDF-friendly HTML)."""

from __future__ import annotations

from html import escape
from typing import Any

from multiagent.web import places_cache, trip_view


def _e(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _yes(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def build_export_html(
    trip: dict[str, Any] | None,
    *,
    include_photos: bool,
    include_map_circuit: bool,
    auto_print: bool = False,
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

    day_blocks: list[str] = []
    for day in itinerary.get("days") or []:
        day_num = int(day.get("day") or 0)
        route = route_by_day.get(day_num) if include_map_circuit else None

        stops_html = []
        for idx, stop in enumerate(day.get("stops") or [], start=1):
            name = str(stop.get("name") or "")
            kind = str(stop.get("kind") or "other")
            time = str(stop.get("time") or "")
            note = str(stop.get("note") or "")
            booked = "Booked" if stop.get("booked") else "Pending"
            photo_html = ""
            if include_photos and kind in {"hotel", "attraction"} and name:
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
                circuit_html = (
                    "<div class='circuit'>"
                    "<div class='circuit-title'>Daily map circuit</div>"
                    f"<div class='circuit-line'>{circuit}</div>"
                    f"<div class='circuit-stats'>{_e(stats.get('distance_display') or '')} · {_e(stats.get('duration_display') or '')} · {_e(stats.get('mode') or '')}</div>"
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
    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{_e(destination or 'Trip')} · Itinerary Export</title>
  <style>
    :root {{ --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --soft:#f8fafc; --accent:#0d9488; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: "Segoe UI", "Inter", sans-serif; color:var(--ink); background:#fff; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .hero {{ border:1px solid var(--line); border-radius:16px; padding:18px; background:linear-gradient(135deg,#f8fafc,#eef2ff); }}
    .hero h1 {{ margin:0; font-size:28px; }}
    .grid {{ display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .k {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
    .v {{ font-weight:600; }}
    .day {{ margin-top:20px; border:1px solid var(--line); border-radius:14px; padding:14px; page-break-inside:avoid; }}
    .day-head {{ display:flex; justify-content:space-between; gap:10px; align-items:baseline; }}
    .day h2 {{ margin:0; font-size:20px; }}
    .day-date {{ color:var(--muted); font-size:13px; }}
    .summary {{ margin:10px 0 8px; color:#334155; }}
    .circuit {{ margin:8px 0 10px; background:#ecfeff; border:1px solid #bae6fd; border-radius:10px; padding:10px; }}
    .circuit-title {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:#0c4a6e; }}
    .circuit-line {{ margin-top:5px; font-size:14px; color:#0f172a; }}
    .circuit-stats {{ margin-top:5px; font-size:12px; color:#0369a1; }}
    .stops {{ margin:0; padding-left:0; list-style:none; display:flex; flex-direction:column; gap:10px; }}
    .stop {{ display:flex; gap:12px; justify-content:space-between; border:1px solid var(--line); border-radius:10px; padding:10px; background:var(--soft); }}
    .stop-main {{ min-width:0; flex:1; }}
    .stop-line {{ display:flex; align-items:center; gap:8px; }}
    .ord {{ display:inline-grid; place-items:center; width:22px; height:22px; border-radius:999px; background:var(--accent); color:#fff; font-size:12px; font-weight:700; }}
    .name {{ font-weight:700; }}
    .meta {{ margin-top:4px; color:var(--muted); font-size:12px; }}
    .note {{ margin-top:6px; color:#334155; font-size:13px; }}
    .stop-photo-wrap {{ width:120px; flex-shrink:0; }}
    .stop-photo {{ width:120px; height:84px; object-fit:cover; border-radius:8px; border:1px solid var(--line); }}
    .foot {{ margin-top:18px; color:var(--muted); font-size:12px; }}
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
    <p class='foot'>Generated by AI Trip Planner. Tip: Use browser Print → Save as PDF for a carry-along copy.</p>
  </div>
  {auto}
</body>
</html>"""


def parse_export_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return _yes(value)
