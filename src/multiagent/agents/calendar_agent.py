"""Calendar Agent — read/write Google Calendar events."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


@tool
def list_upcoming_events(max_results: int = 10) -> str:
    """List upcoming events from Google Calendar."""
    # Placeholder — will integrate with Google Calendar API
    return f"[STUB] Would list next {max_results} events from Google Calendar."


@tool
def create_event(title: str, start: str, end: str, description: str = "") -> str:
    """Create a Google Calendar event. start/end in ISO 8601 format."""
    return f"[STUB] Would create event '{title}' from {start} to {end}."


@tool
def find_free_slots(date: str, duration_minutes: int = 60) -> str:
    """Find free time slots on a given date."""
    return f"[STUB] Would find {duration_minutes}-min free slots on {date}."


CALENDAR_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Calendar Agent. You help the user manage their Google Calendar.
You can list events, create new ones, and find free time slots.
Always confirm event details before creating.
""")

CALENDAR_TOOLS = [list_upcoming_events, create_event, find_free_slots]
