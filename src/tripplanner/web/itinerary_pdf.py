"""Server-side PDF generation for itinerary exports."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from tripplanner.web import trip_view


def build_itinerary_pdf_bytes(trip: dict[str, Any] | None, *, template: str = "detailed") -> bytes:
    """Build a PDF bytes payload for the active itinerary.

    Uses reportlab when available. Caller should catch ImportError and return
    setup guidance if reportlab is not installed.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Circle, Drawing, PolyLine, String
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    map_vm = trip_view.build_map_view(trip)
    route_by_day = {int(d.get("day") or 0): d for d in (map_vm.get("days") or [])}
    pin_by_id = {p.get("id"): p for p in (map_vm.get("pins") or [])}

    story.append(Paragraph(f"{destination} Itinerary ({template.title()})", title_style))
    summary = (
        f"From: {trip.get('origin') or '—'} &nbsp;&nbsp; "
        f"Dates: {trip.get('departure_date') or '—'} to {trip.get('return_date') or '—'} &nbsp;&nbsp; "
        f"Status: {str(trip.get('status') or 'draft').title()}"
    )
    story.append(Paragraph(summary, body))
    story.append(Spacer(1, 10))

    for day in itinerary.get("days") or []:
        day_num = int(day.get("day") or 0)
        story.append(Paragraph(f"Day {day_num}: {day.get('title') or ''}", h2))
        if day.get("date"):
            story.append(Paragraph(f"Date: {day.get('date')}", body))
        if day.get("summary"):
            story.append(Paragraph(str(day.get("summary")), body))

        route = route_by_day.get(day_num)
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
            mini_map = _route_drawing(_route_coords(route.get("pin_ids") or []))
            if mini_map is not None:
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

        rows = [["#", "Stop", "Type", "Time", "Status"]]
        for i, stop in enumerate(day.get("stops") or [], start=1):
            rows.append([
                str(i),
                str(stop.get("name") or ""),
                str(stop.get("kind") or "").title(),
                str(stop.get("time") or ""),
                "Booked" if stop.get("booked") else "Pending",
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

    doc.build(story)
    return buf.getvalue()

