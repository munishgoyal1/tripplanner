"""Server-side PDF generation for itinerary exports."""

from __future__ import annotations

import base64
from html import escape
from io import BytesIO
from typing import Any

import httpx

from tripplanner import http_client
from tripplanner.web import itinerary_export, places_cache, trip_view


def build_itinerary_pdf_bytes(
    trip: dict[str, Any] | None,
    *,
    template: str = "standard",
    include_photos: bool = False,
    include_map_circuit: bool = True,
) -> bytes:
    """Build a PDF bytes payload for the active itinerary.

    Uses reportlab when available. Caller should catch ImportError and return
    setup guidance if reportlab is not installed.
    """
    template_key = str(template or "detailed").strip().lower()
    if template_key not in itinerary_export.TEMPLATES:
        template_key = "detailed"
    include_map_circuit = include_map_circuit and template_key in itinerary_export._MAP_TEMPLATES
    seen_photos: set[str] = set()
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Circle, Drawing, PolyLine, String
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def _image_from_source(source: str, width: float, height: float) -> Image | None:
        try:
            if source.startswith("data:image/") and ";base64," in source:
                raw = base64.b64decode(source.split(";base64,", 1)[1])
            else:
                response = http_client.get(source, timeout=12)
                response.raise_for_status()
                raw = response.content
            ImageReader(BytesIO(raw)).getSize()
            image = Image(BytesIO(raw), width=width, height=height)
            image.hAlign = "LEFT"
            return image
        except (OSError, ValueError, httpx.HTTPError):
            return None

    def _route_coords(pin_ids: list[str]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for pid in pin_ids:
            p = pin_by_id.get(pid) or {}
            lat = p.get("lat")
            lng = p.get("lng")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                out.append((float(lat), float(lng)))
        return out

    def _route_drawing(coords: list[tuple[float, float]]) -> Drawing | None:
        if len(coords) < 2:
            return None
        width, height, pad = 120.0, 70.0, 8.0
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)
        lat_span = max(max_lat - min_lat, 1e-6)
        lng_span = max(max_lng - min_lng, 1e-6)

        def _xy(lat: float, lng: float) -> tuple[float, float]:
            x = pad + ((lng - min_lng) / lng_span) * (width - 2 * pad)
            y = pad + ((max_lat - lat) / lat_span) * (height - 2 * pad)
            return x, y

        points = [_xy(lat, lng) for lat, lng in coords]
        flat = [v for pt in points for v in pt]
        d = Drawing(width, height)
        d.add(PolyLine(flat, strokeColor=colors.HexColor("#0369a1"), strokeWidth=1.8))
        for idx, (x, y) in enumerate(points, start=1):
            d.add(Circle(x, y, 3.4, fillColor=colors.HexColor("#0d9488"), strokeColor=colors.white, strokeWidth=0.8))
            d.add(String(x, y - 1.6, str(idx), fontName="Helvetica-Bold", fontSize=4.5, fillColor=colors.white, textAnchor="middle"))
        return d

    def _qr_drawing(value: str) -> Drawing | None:
        text = str(value or "").strip()
        if not text:
            return None
        qr = QrCodeWidget(text)
        b = qr.getBounds()
        w = float(b[2] - b[0])
        h = float(b[3] - b[1])
        if w <= 0 or h <= 0:
            return None
        size = 20 * mm
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(qr)
        return d

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=20, leading=24, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, leading=18, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)

    story = []
    if not trip:
        story.append(Paragraph("No active trip to export.", body))
        doc.build(story)
        return buf.getvalue()

    destination = str(trip.get("destination") or "Trip")
    itinerary = trip_view.build_itinerary(trip)
    map_vm = trip_view.build_map_view(trip) if include_map_circuit else {"days": [], "pins": []}
    route_by_day = {int(d.get("day") or 0): d for d in (map_vm.get("days") or [])}
    pin_by_id = {p.get("id"): p for p in (map_vm.get("pins") or [])}

    title_labels = {
        "standard": "Standard",
        "detailed": "Detailed",
        "trip_book": "Trip Book",
        "trip_card": "Trip Card",
    }
    story.append(
        Paragraph(f"{destination} Itinerary ({title_labels[template_key]})", title_style)
    )
    summary = (
        f"From: {trip.get('origin') or '—'} &nbsp;&nbsp; "
        f"Dates: {trip.get('departure_date') or '—'} to {trip.get('return_date') or '—'} &nbsp;&nbsp; "
        f"Status: {str(trip.get('status') or 'draft').title()}"
    )
    story.append(Paragraph(summary, body))
    story.append(Spacer(1, 10))

    if template_key == "trip_book":
        from tripplanner.web.itinerary_trip_book import stay_name, trip_book_readiness

        readiness = trip_book_readiness(trip)
        stay = stay_name(trip, itinerary)
        story.append(Paragraph("Contents", h2))
        story.append(Paragraph(
            "Trip brief · Daily itinerary · Essentials and help · Travel documents"
            + (" · Day circuit maps" if include_map_circuit else ""),
            body,
        ))
        badge = str(readiness.get("badge") or "")
        if badge:
            story.append(Paragraph(escape(badge), body))
        else:
            story.append(
                Paragraph(
                    "Document groups on file look ready, or checks are silent for this trip.",
                    body,
                )
            )
        story.append(Spacer(1, 8))
        story.append(Paragraph("Trip brief", h2))
        if stay:
            story.append(Paragraph(f"Stay: {escape(stay)}", body))
        prefs = trip.get("preferences_snapshot") or {}
        style = str(prefs.get("trip_style") or "").strip()
        if style:
            story.append(Paragraph(
                f"Saved trip style: {escape(style.replace('_', ' '))} (preference snapshot).",
                body,
            ))
        story.append(Spacer(1, 8))

    if template_key == "trip_card":
        rows = [["Day", "Date", "Title", "Highlights"]]
        for day in itinerary.get("days") or []:
            stops = [s for s in (day.get("stops") or []) if isinstance(s, dict)]
            names = [str(s.get("name") or "").strip() for s in stops if s.get("name")]
            rows.append([
                str(int(day.get("day") or 0)),
                str(day.get("date") or ""),
                Paragraph(escape(str(day.get("title") or "")), body),
                Paragraph(escape(" · ".join(names[:4])), body),
            ])
        if len(rows) > 1:
            t = Table(rows, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff7ed")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#78350f")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#fed7aa")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(t)
        story.append(Spacer(1, 12))

    for day in ([] if template_key == "trip_card" else (itinerary.get("days") or [])):
        day_num = int(day.get("day") or 0)
        story.append(Paragraph(f"Day {day_num}: {day.get('title') or ''}", h2))
        if day.get("date"):
            story.append(Paragraph(f"Date: {day.get('date')}", body))
        if day.get("summary"):
            story.append(Paragraph(str(day.get("summary")), body))

        route = route_by_day.get(day_num) if include_map_circuit else None
        maps_url = str(day.get("google_maps_url") or "")
        if route:
            stats = route.get("route") or {}
            names = [str(pin_by_id.get(pid, {}).get("name") or pid) for pid in (route.get("pin_ids") or [])]
            story.append(Paragraph(
                "Circuit: " + " -> ".join(names),
                body,
            ))
            story.append(Paragraph(
                f"Route stats: {stats.get('distance_display') or ''} · {stats.get('duration_display') or ''} · {stats.get('mode') or ''}",
                body,
            ))
            map_source = itinerary_export._static_map_data_uri(
                route.get("pin_ids") or [], pin_by_id
            )
            map_image = _image_from_source(map_source, 170 * mm, 85 * mm) if map_source else None
            mini_map = _route_drawing(_route_coords(route.get("pin_ids") or []))
            if map_image is not None:
                story.append(Spacer(1, 4))
                story.append(map_image)
            elif mini_map is not None:
                story.append(Spacer(1, 4))
                story.append(mini_map)

        if maps_url:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"Open route: {maps_url}", body))
            qr_img = _qr_drawing(maps_url)
            if qr_img is not None:
                story.append(Spacer(1, 3))
                story.append(qr_img)
                story.append(Paragraph("Scan to open this day route in Google Maps.", body))

        rows = [["#", "Place details", "Type / time", "Status", "Photo"]]
        for i, stop in enumerate(day.get("stops") or [], start=1):
            name = str(stop.get("name") or "")
            kind = str(stop.get("kind") or "")
            place = (
                places_cache.get_details(name, destination) or {}
                if name and kind in {"hotel", "attraction", "meal", "restaurant"}
                else {}
            )
            details = [f"<b>{escape(name)}</b>"]
            address = str(place.get("address") or "")
            rating = place.get("rating")
            note = str(stop.get("note") or "")
            if address:
                details.append(escape(address))
            if isinstance(rating, (int, float)):
                details.append(f"Rating {rating:g}")
            if note:
                details.append(escape(note))
            photo = None
            flagship_key = name.strip().casefold()
            if (
                include_photos
                and name
                and kind in {"hotel", "attraction", "meal", "restaurant"}
                and flagship_key not in seen_photos
            ):
                photos = places_cache.get_photos(name, destination, max_photos=1)
                if photos:
                    seen_photos.add(flagship_key)
                    photo = _image_from_source(photos[0], 34 * mm, 23 * mm)
            rows.append([
                str(i),
                Paragraph("<br/>".join(details), body),
                f"{kind.title()} {str(stop.get('time') or '')}".strip(),
                "Booked" if stop.get("booked") else "Pending",
                photo or "",
            ])
        if len(rows) > 1:
            t = Table(rows, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(Spacer(1, 6))
            story.append(t)
        story.append(Spacer(1, 12))

    if template_key in {"detailed", "trip_book"}:
        weather = trip_view.build_weather(trip)
        cost_breakdown = trip.get("cost_breakdown")
        symbol = trip_view.currency_symbol(trip)
        essential_lines: list[str] = []
        if weather and weather.get("days"):
            highs = [d["high_c"] for d in weather["days"] if d.get("high_c") is not None]
            lows = [d["low_c"] for d in weather["days"] if d.get("low_c") is not None]
            if highs and lows:
                essential_lines.append(
                    f"Weather: {min(lows):.0f}–{max(highs):.0f}°C · {weather.get('source_label') or ''}"
                )
            packing = "; ".join(weather.get("packing_advice") or [])
            if packing:
                essential_lines.append(f"Packing: {packing}")
        if isinstance(cost_breakdown, dict) and cost_breakdown:
            items = " · ".join(
                f"{str(key).replace('_', ' ').title()} {trip_view.fmt_money(value, symbol)}"
                for key, value in cost_breakdown.items()
                if isinstance(value, (int, float))
            )
            if items:
                essential_lines.append(f"Budget breakdown: {items}")
        if essential_lines:
            heading = "Essentials and help" if template_key == "trip_book" else "Trip essentials"
            story.append(Paragraph(heading, h2))
            for line in essential_lines:
                story.append(Paragraph(escape(line), body))
            story.append(Spacer(1, 12))

    if template_key == "trip_book":
        from tripplanner.web import travel_documents
        from tripplanner.web.itinerary_trip_book import stay_name, trip_book_readiness

        readiness = trip_book_readiness(trip)
        stay = stay_name(trip, itinerary)
        if stay:
            story.append(Paragraph(f"Hotel: {escape(stay)}", body))
        travelers = str(trip.get("travelers") or "").strip()
        if travelers:
            story.append(Paragraph(f"Travelling party: {escape(travelers)}", body))
        story.append(Paragraph("Confirmations and entry", h2))
        trip_id = str(trip.get("trip_id") or "")
        records = [
            record
            for record in travel_documents.list_documents(scope=None)
            if str(record.get("scope") or "traveler") != "trip"
            or str(record.get("trip_id") or "") == trip_id
        ]
        doc_rows = [["Document", "Traveller", "Notes"]]
        for item in trip.get("selected_flights") or []:
            if isinstance(item, dict):
                label = str(item.get("airline") or item.get("name") or "Flight")
            else:
                label = str(item)
            doc_rows.append(["Flight", label, "Selected"])
        for record in records:
            doc_type = str(record.get("type") or "")
            label = travel_documents.TYPE_LABELS.get(
                doc_type, doc_type.title() or "Document"
            )
            holder = str(record.get("traveller_name") or "").strip() or "Traveller"
            fields = record.get("fields") or {}
            summary_fields = itinerary_export._DOCUMENT_SUMMARY_FIELDS.get(doc_type, ())
            summary = " · ".join(str(fields[key]) for key in summary_fields if fields.get(key))
            doc_rows.append([label, holder, summary or "On file"])
        for check in readiness.get("checks") or []:
            if check.get("severity") in {"blocker", "warning"}:
                doc_rows.append([
                    "Action needed",
                    str(check.get("title") or ""),
                    str(check.get("detail") or ""),
                ])
        if len(doc_rows) > 1:
            t = Table(doc_rows, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(t)
        story.append(Paragraph("Reference numbers are kept out of this file by design.", body))

    doc.build(story)
    return buf.getvalue()

