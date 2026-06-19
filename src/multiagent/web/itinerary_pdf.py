"""Server-side PDF generation for itinerary exports."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from multiagent.web import trip_view


def build_itinerary_pdf_bytes(trip: dict[str, Any] | None, *, template: str = "detailed") -> bytes:
    """Build a PDF bytes payload for the active itinerary.

    Uses reportlab when available. Caller should catch ImportError and return
    setup guidance if reportlab is not installed.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
