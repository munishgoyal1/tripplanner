"""Itinerary email delivery with durable outbound-write idempotency."""

from __future__ import annotations

import os
import smtplib
import time
from email.message import EmailMessage
from urllib.parse import quote

from azure.communication.email import EmailClient
from fastapi.responses import JSONResponse

from tripplanner.api_contracts import ExportEmailRequest
from tripplanner.observability import app_event
from tripplanner.tools import trip_planner
from tripplanner.web import external_operations, itinerary_export, share


def send_itinerary_email(
    req: ExportEmailRequest,
    *,
    base_url: str,
) -> dict | JSONResponse:
    plan = trip_planner.load_active_trip_dict()
    if not plan:
        return {"ok": False, "error": "no_active_trip", "message": "No active trip to export."}

    token = share.mint_for_active_trip()
    share_url = f"{base_url.rstrip('/')}/trip/shared/{token}" if token else ""
    html = itinerary_export.build_export_html(
        plan,
        include_photos=bool(req.include_photos),
        include_map_circuit=bool(req.include_map_circuit),
        template=req.template,
        auto_print=False,
        share_url=share_url,
    )
    destination = str(plan.get("destination") or "Trip")
    subject = f"{destination} itinerary export"
    fingerprint = external_operations.payload_fingerprint(
        {
            "trip_id": trip_planner.active_trip_id(),
            "email": req.email.strip().casefold(),
            "include_photos": req.include_photos,
            "include_map_circuit": req.include_map_circuit,
            "template": req.template,
        }
    )
    try:
        existing = external_operations.get(req.request_id, fingerprint)
    except external_operations.IdempotencyConflictError as exc:
        return JSONResponse(
            {"ok": False, "error": "idempotency_conflict", "message": str(exc)},
            status_code=409,
        )
    if existing and existing.get("status") == "completed":
        return {**dict(existing.get("result") or {}), "replayed": True}

    plain = (
        f"Your trip itinerary for {destination} is attached as HTML.\n"
        "Open it in a browser and Print -> Save as PDF for a carry-along copy.\n"
        + (f"\nContinue planning or share this trip:\n{share_url}\n" if share_url else "")
    )

    acs_conn = os.getenv("AZURE_COMMUNICATION_CONNECTION_STRING", "").strip()
    acs_sender = os.getenv("AZURE_COMMUNICATION_EMAIL_SENDER", "").strip()
    if acs_conn and acs_sender:
        email_started: float | None = None
        try:
            operation, _ = external_operations.claim_pending(
                req.request_id, fingerprint, provider="acs"
            )
            if operation.get("provider") != "acs":
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "email_delivery_uncertain",
                        "message": "The earlier delivery attempt is still unresolved.",
                    },
                    status_code=503,
                )
            client = EmailClient.from_connection_string(acs_conn)
            message = {
                "senderAddress": acs_sender,
                "recipients": {"to": [{"address": req.email}]},
                "content": {"subject": subject, "plainText": plain, "html": html},
            }
            email_started = time.monotonic()
            poller = client.begin_send(
                message,
                operation_id=external_operations.provider_operation_id(req.request_id),
            )
            poller.result()
            from tripplanner.provider_usage import record_call

            record_call(
                provider="azure_communication_email",
                operation="email_send",
                status="ok",
                duration_ms=(time.monotonic() - email_started) * 1000,
            )
            result = {"ok": True, "message": f"Itinerary sent to {req.email}."}
            external_operations.record_completed(
                req.request_id,
                fingerprint,
                provider="acs",
                result=result,
            )
            app_event("api_trip_export_email_sent", destination=destination, provider="acs")
            return result
        except Exception as exc:
            if email_started is not None:
                from tripplanner.provider_usage import record_call

                record_call(
                    provider="azure_communication_email",
                    operation="email_send",
                    status=type(exc).__name__,
                    duration_ms=(time.monotonic() - email_started) * 1000,
                )
            app_event("api_trip_export_email_error", error=type(exc).__name__, provider="acs")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "email_delivery_uncertain",
                    "message": "Email delivery could not be confirmed. Retry this send safely.",
                },
                status_code=503,
            )

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "").strip()
    smtp_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"}

    if not smtp_host or not smtp_from:
        body = quote(plain + "\n(Email sending is not configured on this server.)", safe="")
        return {
            "ok": False,
            "error": "email_not_configured",
            "mailto": (
                f"mailto:{quote(req.email, safe='')}?"
                f"subject={quote(subject, safe='')}&body={body}"
            ),
            "message": "SMTP is not configured; opened mail client fallback.",
        }

    try:
        operation, claimed = external_operations.claim_pending(
            req.request_id, fingerprint, provider="smtp"
        )
    except external_operations.IdempotencyConflictError as exc:
        return JSONResponse(
            {"ok": False, "error": "idempotency_conflict", "message": str(exc)},
            status_code=409,
        )
    if not claimed:
        if operation.get("status") == "completed":
            return {**dict(operation.get("result") or {}), "replayed": True}
        return JSONResponse(
            {
                "ok": False,
                "error": "email_delivery_uncertain",
                "message": "The earlier delivery attempt is still unresolved.",
            },
            status_code=503,
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = req.email
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    message.add_attachment(
        html.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename="trip-itinerary.html",
    )

    email_started = time.monotonic()
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            if smtp_tls:
                smtp.starttls()
            if smtp_user:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(message)
    except Exception as exc:
        from tripplanner.provider_usage import record_call

        record_call(
            provider="smtp",
            operation="email_send",
            status=type(exc).__name__,
            duration_ms=(time.monotonic() - email_started) * 1000,
        )
        app_event("api_trip_export_email_error", error=type(exc).__name__)
        return JSONResponse(
            {
                "ok": False,
                "error": "email_delivery_uncertain",
                "message": "Email delivery could not be confirmed.",
            },
            status_code=503,
        )

    from tripplanner.provider_usage import record_call

    record_call(
        provider="smtp",
        operation="email_send",
        status="ok",
        duration_ms=(time.monotonic() - email_started) * 1000,
    )
    result = {"ok": True, "message": f"Itinerary sent to {req.email}."}
    external_operations.record_completed(
        req.request_id,
        fingerprint,
        provider="smtp",
        result=result,
    )
    app_event("api_trip_export_email_sent", destination=destination)
    return result
