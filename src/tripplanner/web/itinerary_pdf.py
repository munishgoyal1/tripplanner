"""Server-side PDF generation for itinerary exports.

The printable HTML is the source of truth. Chromium/Edge print-to-PDF is used
when a browser is available so the file matches preview. ReportLab is only the
fallback renderer and follows the same day/stop structure, not the old tables.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from html import escape, unescape
from io import BytesIO
from pathlib import Path
from typing import Any

from tripplanner import http_client
from tripplanner.web import itinerary_export, trip_view

_IMG_SRC = re.compile(
    r"(<img\b[^>]*?\ssrc=)(['\"])([^'\"]+)\2",
    re.IGNORECASE | re.DOTALL,
)
_MAX_INLINE_IMAGE_BYTES = 1_500_000
_IMAGE_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


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


def inline_remote_images(html: str) -> str:
    """Embed http(s) <img> URLs as data URIs so file:// print-to-PDF can paint them."""
    cache: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        src = unescape(match.group(3)).strip()
        uri = cache.get(src)
        if uri is None:
            payload, content_type = _image_bytes(src)
            uri = ""
            if payload and content_type:
                encoded = base64.b64encode(payload).decode("ascii")
                uri = f"data:{content_type};base64,{encoded}"
            cache[src] = uri
        if not uri:
            return match.group(0)
        quote = match.group(2)
        return f"{match.group(1)}{quote}{uri}{quote}"

    return _IMG_SRC.sub(replace, html)


def materialize_images(html: str, folder: Path) -> str:
    """Rewrite <img> tags to local files in ``folder`` for Chromium print-to-PDF."""
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        src = unescape(match.group(3)).strip()
        payload, content_type = _image_bytes(src)
        if not payload:
            return match.group(0)
        index += 1
        suffix = {
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
        }.get(content_type, ".jpg")
        name = f"img-{index}{suffix}"
        (folder / name).write_bytes(payload)
        quote = match.group(2)
        return f"{match.group(1)}{quote}{name}{quote}"

    return _IMG_SRC.sub(replace, html)


def _image_bytes(src: str) -> tuple[bytes, str]:
    if src.startswith("data:image/") and ";base64," in src:
        header, encoded = src.split(";base64,", 1)
        content_type = header.split(":", 1)[1].split(";", 1)[0]
        try:
            raw = base64.b64decode(encoded)
        except ValueError:
            return b"", ""
        return raw, content_type
    if not src.startswith(("http://", "https://")):
        return b"", ""
    try:
        response = http_client.get(
            src,
            timeout=12,
            headers=_IMAGE_FETCH_HEADERS,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return b"", ""
    raw = response.content or b""
    if not raw or len(raw) > _MAX_INLINE_IMAGE_BYTES:
        return b"", ""
    content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip()
    if not content_type.startswith("image/"):
        if raw[:3] == b"\xff\xd8\xff":
            content_type = "image/jpeg"
        elif raw[:8] == b"\x89PNG\r\n\x1a\n":
            content_type = "image/png"
        elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            content_type = "image/webp"
        else:
            return b"", ""
    return raw, content_type


def html_to_pdf_bytes(html: str) -> bytes | None:
    """Print the export HTML to PDF with a local Chromium-family browser."""
    if os.getenv("TRIPPLANNER_HTML_PDF", "1").strip().lower() in {"0", "false", "no"}:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "itinerary.html"
        pdf_path = Path(tmp) / "itinerary.pdf"
        printable = materialize_images(html, html_path.parent)
        html_path.write_text(printable, encoding="utf-8")
        uri = html_path.resolve().as_uri()
        wait_ms = "20000" if "img-" in printable else "8000"
        timeout_s = 50 if wait_ms == "20000" else 20
        for browser in _browser_paths():
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--allow-file-access-from-files",
                "--run-all-compositor-stages-before-draw",
                f"--virtual-time-budget={wait_ms}",
                f"--print-to-pdf={pdf_path}",
                "--print-to-pdf-no-header",
                uri,
            ]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    timeout=timeout_s,
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
    html: str | None = None,
) -> bytes:
    """Build a PDF bytes payload for the active itinerary."""
    packet = html if html is not None else itinerary_export.build_export_html(
        trip,
        include_photos=include_photos,
        include_map_circuit=include_map_circuit,
        include_budgets=include_budgets,
        template=template,
        auto_print=False,
    )
    printed = html_to_pdf_bytes(packet)
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
