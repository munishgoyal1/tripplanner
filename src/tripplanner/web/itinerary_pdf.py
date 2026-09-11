"""Server-side PDF generation for itinerary exports.

The printable HTML is the source of truth. Chromium/Edge print-to-PDF is used
when a browser is available so the file matches preview. ReportLab is only the
fallback renderer and follows the same day/stop structure, not the old tables.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from tripplanner.web import itinerary_export, trip_view


def _browser_paths() -> list[str]:
    found: list[str] = []
    for name in (
        "msedge",
        "chrome",
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
    ):
        path = shutil.which(name)
        if path:
            found.append(path)
    extra = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for path in extra:
        if path.is_file():
            found.append(str(path))
    unique: list[str] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def html_to_pdf_bytes(html: str) -> bytes | None:
    """Print the export HTML to PDF with a local Chromium-family browser."""
    if os.getenv("TRIPPLANNER_HTML_PDF", "1").strip().lower() in {"0", "false", "no"}:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "itinerary.html"
        pdf_path = Path(tmp) / "itinerary.pdf"
        html_path.write_text(html, encoding="utf-8")
        uri = html_path.resolve().as_uri()
        for browser in _browser_paths():
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                f"--print-to-pdf={pdf_path}",
                "--print-to-pdf-no-header",
                uri,
            ]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    timeout=12,
                    capture_output=True,
                )
            except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                continue
            if pdf_path.is_file() and pdf_path.stat().st_size > 8:
                data = pdf_path.read_bytes()
                if data.startswith(b"%PDF"):
                    return data
    return None


def build_itinerary_pdf_bytes(
    trip: dict[str, Any] | None,
    *,
    template: str = "standard",
    include_photos: bool = False,
    include_map_circuit: bool = True,
    include_budgets: bool = False,
) -> bytes:
    """Build a PDF bytes payload for the active itinerary."""
    html = itinerary_export.build_export_html(
        trip,
        include_photos=include_photos,
        include_map_circuit=include_map_circuit,
        include_budgets=include_budgets,
        template=template,
        auto_print=False,
    )
    printed = html_to_pdf_bytes(html)
    if printed:
        return printed
    return _reportlab_packet_bytes(
        trip,
        template=template,
        include_photos=include_photos,
        include_map_circuit=include_map_circuit,
        include_budgets=include_budgets,
    )


def _reportlab_packet_bytes(
    trip: dict[str, Any] | None,
    *,
    template: str,
    include_photos: bool,
    include_map_circuit: bool,
    include_budgets: bool,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=28, bottomMargin=28
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=18, leading=22, spaceAfter=8
    )
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, leading=16, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=12)
    muted = ParagraphStyle("muted", parent=body, textColor="#475569")
    story: list[Any] = []
    if not trip:
        story.append(Paragraph("No active trip to export.", body))
        doc.build(story)
        return buf.getvalue()

    template_key = str(template or "standard").strip().lower()
    if template_key == "detailed":
        template_key = "standard"
    include_map_circuit = template_key in itinerary_export._MAP_TEMPLATES
    _ = include_photos, include_map_circuit
    destination = str(trip.get("destination") or "Trip")
    itinerary = trip_view.build_itinerary(trip)
    label = "Trip Book" if template_key == "trip_book" else "Standard"
    story.append(Paragraph(escape(f"{destination} itinerary ({label})"), title_style))
    story.append(Paragraph(
        escape(
            f"From {trip.get('origin') or '—'} · "
            f"{trip.get('departure_date') or '—'} to {trip.get('return_date') or '—'}"
        ),
        muted,
    ))
    if include_budgets:
        total = trip_view.fmt_money(trip.get("total_cost"), trip_view.currency_symbol(trip))
        story.append(Paragraph(escape(f"Total {total}"), body))
    story.append(Spacer(1, 8))

    for day in itinerary.get("days") or []:
        day_num = int(day.get("day") or 0)
        day_date = itinerary_export.format_export_day_date(str(day.get("date") or ""))
        story.append(Paragraph(escape(f"Day {day_num}: {day.get('title') or ''}"), h2))
        if day_date:
            story.append(Paragraph(escape(day_date), muted))
        if day.get("summary"):
            story.append(Paragraph(escape(str(day.get("summary"))), body))
        stops = [s for s in (day.get("stops") or []) if isinstance(s, dict)]
        labels = itinerary_export._day_map_labels(stops)
        for index, stop in enumerate(stops):
            name = str(stop.get("name") or "")
            time = str(stop.get("time") or "")
            marker = labels[index]
            duration = itinerary_export._duration_text(stop)
            hours = str(stop.get("opening_hours") or "").strip()
            note = str(stop.get("note") or "").strip()
            bits = [bit for bit in (marker, time, name, duration, hours, note) if bit]
            story.append(Paragraph(escape(" · ".join(bits)), body))
            story.append(Spacer(1, 3))
        story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        "This PDF fallback matches the preview structure when a browser printer is unavailable.",
        muted,
    ))
    doc.build(story)
    return buf.getvalue()
