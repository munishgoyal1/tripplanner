"""Server-side PDF generation for itinerary exports.

The printable HTML is the source of truth. Chromium/Edge print-to-PDF is used
when a browser is available so the file matches preview. ReportLab is only the
fallback renderer and follows the same day/stop structure, not the old tables.
"""

from __future__ import annotations

import base64
import contextvars
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from html import escape, unescape
from io import BytesIO
from pathlib import Path
from typing import Any

from tripplanner import http_client
from tripplanner.web import itinerary_export, places_cache, trip_view

_IMG_SRC = re.compile(
    r"(<img\b[^>]*?\ssrc=)(['\"])([^'\"]+)\2",
    re.IGNORECASE | re.DOTALL,
)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_TAG_SRC = re.compile(r"\bsrc=(['\"])([^'\"]+)\1", re.IGNORECASE)
_MAX_INLINE_IMAGE_BYTES = 1_500_000
_IMAGE_FETCH_TIMEOUT_S = 6
_IMAGE_FETCH_WORKERS = 8
# A 4 MB photo packet prints in 3-7s. These bound the pathological case only:
# one attempt that outlives its timeout ends the browser path for the request.
_PRINT_ATTEMPT_TIMEOUT_S = 40.0
_PRINT_TOTAL_DEADLINE_S = 60.0
_IMAGE_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.google.com/",
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
    return embed_packet_images(html, "")


def embed_packet_images(html: str, destination: str = "") -> str:
    """Rewrite packet images to data URIs using URL bytes, then Places media.

    A week-long packet carries ~30 photos, maps and QR codes. Fetched one at a
    time that was 15-30s before the browser even started, and one slow CDN
    response added its full timeout; distinct images are fetched concurrently.
    """
    def key_for(tag: str) -> tuple[str, str] | None:
        """(image URL, Places fallback name) for a tag that still needs bytes."""
        src_match = _TAG_SRC.search(tag)
        if not src_match:
            return None
        src = unescape(src_match.group(2)).strip()
        if src.startswith("data:image/"):
            return None
        alt = ""
        if "stop-photo" in tag and destination:
            alt_match = re.search(r"\balt=(['\"])(.*?)\1", tag, re.IGNORECASE | re.DOTALL)
            alt = unescape(alt_match.group(2)).strip() if alt_match else ""
        return src, alt

    def data_uri(result: tuple[bytes, str]) -> str:
        payload, content_type = result
        if not payload or not content_type:
            return ""
        return f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"

    keys = [key for key in (key_for(m.group(0)) for m in _IMG_TAG.finditer(html)) if key]
    if not keys:
        return html
    by_src = _fetch_concurrently(_image_bytes, list(dict.fromkeys(src for src, _ in keys)))
    by_src = {src: data_uri(result) for src, result in by_src.items()}
    fallback_names = list(dict.fromkeys(alt for src, alt in keys if alt and not by_src[src]))
    by_name = {
        name: data_uri(result)
        for name, result in _fetch_concurrently(
            lambda name: places_cache.get_photo_bytes(name, destination), fallback_names
        ).items()
    }

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        key = key_for(tag)
        uri = (by_src[key[0]] or by_name.get(key[1], "")) if key else ""
        src_match = _TAG_SRC.search(tag)
        if not uri or not src_match:
            return tag
        start, end = src_match.start(2), src_match.end(2)
        return f"{tag[:start]}{uri}{tag[end:]}"

    return _IMG_TAG.sub(replace, html)


def _fetch_concurrently(
    fetch: Callable[[str], tuple[bytes, str]], items: list[str]
) -> dict[str, tuple[bytes, str]]:
    if not items:
        return {}
    with ThreadPoolExecutor(max_workers=min(_IMAGE_FETCH_WORKERS, len(items))) as pool:
        # copy_context carries the paid-provider scope into Places photo fetches.
        futures = [pool.submit(contextvars.copy_context().run, fetch, item) for item in items]
        return dict(zip(items, (future.result() for future in futures), strict=True))


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
            timeout=_IMAGE_FETCH_TIMEOUT_S,
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


def html_to_pdf_bytes(html: str, destination: str = "") -> bytes | None:
    """Print the export HTML to PDF with a local Chromium-family browser."""
    if os.getenv("TRIPPLANNER_HTML_PDF", "1").strip().lower() in {"0", "false", "no"}:
        return None
    # Browser profiles can keep files locked briefly after exit on Windows.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        html_path = Path(tmp) / "itinerary.html"
        pdf_path = Path(tmp) / "itinerary.pdf"
        printable = embed_packet_images(html, destination)
        html_path.write_text(printable, encoding="utf-8")
        uri = html_path.resolve().as_uri()
        wait_ms = "12000" if "data:image/" in printable else "8000"
        deadline = time.monotonic() + _PRINT_TOTAL_DEADLINE_S
        attempt = 0
        for browser in _browser_paths():
            for headless in ("--headless=new", "--headless"):
                remaining = deadline - time.monotonic()
                if remaining <= 1:
                    return None
                attempt += 1
                if pdf_path.exists():
                    pdf_path.unlink()
                cmd = [
                    browser,
                    headless,
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-extensions",
                    "--no-first-run",
                    "--no-default-browser-check",
                    # A private profile per attempt: never hand the job to (or
                    # queue behind) the user's own browser or another automation.
                    f"--user-data-dir={Path(tmp) / f'profile-{attempt}'}",
                    "--run-all-compositor-stages-before-draw",
                    f"--virtual-time-budget={wait_ms}",
                    f"--print-to-pdf={pdf_path}",
                    "--print-to-pdf-no-header",
                    uri,
                ]
                finished = _run_browser(cmd, min(_PRINT_ATTEMPT_TIMEOUT_S, remaining))
                if pdf_path.is_file() and pdf_path.stat().st_size > 8:
                    data = pdf_path.read_bytes()
                    if data.startswith(b"%PDF"):
                        return data
                if finished is None:
                    # It hung. Another browser/mode on the same packet has only
                    # ever hung too; fall back instead of stacking timeouts.
                    return None
    return None


def _run_browser(cmd: list[str], timeout_s: float) -> int | None:
    """Run one print attempt; the exit code, or ``None`` if it was killed.

    On 2026-09-15 a local export sat in the print step for 25 minutes under
    ``subprocess.run(capture_output=True, timeout=40)`` across four attempts.
    That wedge did not reproduce offline, so every way to wait is removed
    rather than tuned: no captured pipes to drain after a kill, and a timed-out
    attempt loses its whole process tree, not just the launcher.
    """
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        popen_kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(cmd, **popen_kwargs)
    except OSError:
        return 1
    try:
        return process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        return None


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
        process.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


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
    if template == "booking_intent":
        from tripplanner.web.booking_export import build_pdf
        return build_pdf(trip)
    packet = html if html is not None else itinerary_export.build_export_html(
        trip,
        include_photos=include_photos,
        include_map_circuit=include_map_circuit,
        include_budgets=include_budgets,
        template=template,
        auto_print=False,
    )
    destination = str((trip or {}).get("destination") or "")
    printed = html_to_pdf_bytes(packet, destination)
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
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

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
    _ = include_map_circuit
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
            if include_photos and name:
                payload, _ctype = places_cache.get_photo_bytes(name, destination)
                if payload:
                    try:
                        story.append(
                            Image(ImageReader(BytesIO(payload)), width=90, height=63)
                        )
                    except Exception:
                        pass
            story.append(Spacer(1, 3))
        story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        "This PDF fallback matches the preview structure when a browser printer is unavailable.",
        muted,
    ))
    doc.build(story)
    return buf.getvalue()
