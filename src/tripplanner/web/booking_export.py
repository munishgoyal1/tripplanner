"""Self-contained, redacted booking-intent packets; never fetch provider data."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from html import escape

from tripplanner.decisions.booking_intent import build_booking_view


def snapshot(plan: dict | None) -> dict:
    return {
        "kind": "booking_intent",
        "exported_at": datetime.now(UTC).isoformat(),
        "notice": "Research and intentions only. Not a booking confirmation; prices and availability are not held.",
        **build_booking_view(plan, private=False),
    }


def packet_lines(packet: dict) -> list[str]:
    lines = [
        f"{packet['destination']} — Booking intent list",
        packet["notice"],
        f"Trip: {packet['trip_id']} | Revision: {packet['updated_at']}",
        f"Exported: {packet['exported_at']} | Party: {packet['travelers']}",
        packet["coverage"],
    ]
    for category, budget in packet["budgets"].items():
        lines.append(
            f"{category}: {budget['currency']} {budget['known_total']:,.2f} known / {budget['amount']:,.2f} cap — {budget['status']}"
        )
    for row in packet["rows"]:
        lines.extend(
            [
                "",
                f"{row['category'].upper()} — {row['name']}",
                "Selected itinerary item"
                if row["selected"]
                else "Researched proposal — not selected for booking",
                f"{row['start_date']} — {row['end_date']} {row['time']}",
                f"Intent: {row['intent_state']} | Booking: {'user-reported booked' if row['actual'] else 'marked booked' if row['booked'] else row['disposition']}",
                f"Research: {row['currency']} {row['amount'] if row['amount'] is not None else 'unknown'} | {row['evidence']}",
                f"Source/suggested provider: {row['provider'] or 'unverified'} | Checked: {row['checked_at'] or 'unknown'} | Expires: {row['expires_at'] or 'unknown'}",
                f"Mandatory costs: {'complete in saved evidence' if row['complete_cost'] else 'not fully verified'}",
                "Details: " + describe(row["details"]),
                f"Handoff: {row['handoff_label']}"
                + (
                    f" {row['url']}"
                    if row["url"]
                    else " Use these details to book anywhere, including offline."
                ),
            ]
        )
        if row["intended"]:
            intent = row["intended"]
            lines.append(
                f"Saved intention: {intent['name']} | {intent['start_date']} — {intent['end_date']} | {intent['currency']} {intent['amount']}"
            )
        lines.extend(row.get("warnings") or [])
        if row.get("context_warning"):
            lines.append(row["context_warning"])
        if row["actual"]:
            actual = row["actual"]
            lines.append(
                f"Reported actual: {actual['product']} via {actual['provider']} | {actual['currency']} {actual['amount'] if actual['amount'] is not None else 'amount unknown'} | {actual['start_date']} — {actual['end_date']} {actual['time']}"
            )
        for option in row["alternatives"]:
            lines.append(
                f"Alternative: {option['name']} | {option['currency']} {option['amount']} | {option['start_date']} — {option['end_date']} | {option['provider']} | checked {option['checked_at']} | {describe(option['details'])}"
            )
    return lines


def describe(value) -> str:
    if value is None or value == "":
        return "Unknown"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        return "; ".join(
            f"{key.replace('_', ' ')}: {describe(item)}" for key, item in value.items()
        )
    if isinstance(value, list):
        return "; ".join(describe(item) for item in value) or "None recorded"
    return str(value)


def build_html(plan: dict | None, *, auto_print: bool = False) -> str:
    packet = snapshot(plan)
    paragraphs = "".join(
        f"<p>{escape(line)}</p>" if line else "<hr>" for line in packet_lines(packet)
    )
    links = "".join(
        f'<li><a href="{escape(row["url"], quote=True)}" rel="noopener noreferrer">{escape(row["name"])}</a>'
        f" — {escape(row['handoff_label'])}</li>"
        for row in packet["rows"]
        if row["url"]
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Booking intent list</title>'
        "<style>body{font:14px/1.5 system-ui;max-width:900px;margin:32px auto;padding:20px;color:#162e35}"
        "p{white-space:pre-wrap;overflow-wrap:anywhere}hr{margin:26px 0;border:0;border-top:1px solid #bbc}"
        "@media print{body{margin:0;padding:0}a{color:inherit}}</style></head><body>"
        "<h1>Booking intent list</h1>"
        + paragraphs
        + "<ul>"
        + links
        + "</ul>"
        + ("<script>window.print()</script>" if auto_print else "")
        + "</body></html>"
    )


def build_pdf(plan: dict | None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output = io.BytesIO()
    style = getSampleStyleSheet()["BodyText"]
    style.wordWrap = "CJK"
    story = []
    for line in packet_lines(snapshot(plan)):
        story.append(Paragraph(escape(line), style) if line else Spacer(1, 12))
    SimpleDocTemplate(output, pagesize=A4, title="Booking intent list").build(story)
    return output.getvalue()
