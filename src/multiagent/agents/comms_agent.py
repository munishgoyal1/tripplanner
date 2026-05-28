"""Comms Agent — send SMS, emails, and initiate calls."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


@tool
def send_sms(to: str, body: str) -> str:
    """Send an SMS message via Twilio. `to` should be a phone number like +1234567890."""
    # Lazy import to avoid errors when Twilio isn't configured yet
    from twilio.rest import Client

    from multiagent.config import get_settings

    settings = get_settings()
    if not settings.twilio_account_sid:
        return "Twilio is not configured. Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    message = client.messages.create(
        body=body, from_=settings.twilio_phone_number, to=to
    )
    return f"SMS sent to {to} (SID: {message.sid})"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail API. Requires Google OAuth setup."""
    # Placeholder — will integrate with Gmail API
    return f"[STUB] Would send email to {to} — Subject: {subject}"


@tool
def initiate_call(to: str, message: str) -> str:
    """Initiate a phone call via Twilio with a spoken message."""
    from twilio.rest import Client

    from multiagent.config import get_settings

    settings = get_settings()
    if not settings.twilio_account_sid:
        return "Twilio is not configured."
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        twiml=f"<Response><Say>{message}</Say></Response>",
        from_=settings.twilio_phone_number,
        to=to,
    )
    return f"Call initiated to {to} (SID: {call.sid})"


COMMS_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Communications Agent. You help the user send text messages, emails, and make calls.
Always confirm the recipient and message content before sending.
If credentials are missing, tell the user which ones to configure.
""")

COMMS_TOOLS = [send_sms, send_email, initiate_call]
