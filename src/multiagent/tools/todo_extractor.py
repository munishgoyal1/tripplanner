"""TODO Extractor — uses LLM to extract actionable TODOs from all sources.

Pulls data from Google Keep, Gmail, WhatsApp, and call records,
then asks the LLM to identify actionable items, follow-ups, and reminders.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from multiagent.config import get_settings
from multiagent.tools.call_records_parser import CallRecordParser
from multiagent.tools.gmail_connector import GmailConnector
from multiagent.tools.keep_connector import KeepConnector
from multiagent.tools.whatsapp_parser import WhatsAppParser

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = SystemMessage(content="""\
You are a personal assistant analyzing the user's messages, emails, notes, and call logs.

Your job: extract ACTIONABLE TODO items from the raw data below.

For each TODO, output a JSON array with objects containing:
  - "title": concise action description (imperative, e.g. "Call back Dr. Smith")
  - "priority": "high", "medium", or "low"
  - "due": suggested due date (YYYY-MM-DD) or null if unclear
  - "source": where it came from ("google_keep", "gmail", "whatsapp", "call_records")
  - "context": brief explanation of why this is a TODO
  - "people": list of people involved (names or contacts)

Rules:
- Only include genuinely ACTIONABLE items (not FYI, not spam, not newsletters)
- Missed calls → suggest "Call back [person]" with high priority
- Emails asking for a response → "Reply to [person] re: [subject]"
- Keep checklist unchecked items → preserve as TODOs
- WhatsApp messages with commitments/requests → extract the action
- Deduplicate: if the same action appears in multiple sources, merge them
- Return ONLY the JSON array, no markdown, no explanation

Output ONLY valid JSON.
""")


@dataclass
class ExtractedTodo:
    title: str
    priority: str
    due: str | None
    source: str
    context: str
    people: list[str] = field(default_factory=list)


class TodoExtractor:
    """Pull data from all sources and extract TODOs via LLM."""

    def __init__(self):
        self.keep = KeepConnector()
        self.gmail = GmailConnector()
        self.whatsapp = WhatsAppParser()
        self.calls = CallRecordParser()

    def gather_all_sources(self) -> dict[str, str]:
        """Collect text from all available sources."""
        sources: dict[str, str] = {}

        # Google Keep
        try:
            text = self.keep.fetch_as_text()
            if "not logged in" not in text.lower():
                sources["google_keep"] = text
        except Exception as e:
            logger.warning(f"Keep fetch failed: {e}")

        # Gmail
        try:
            if self.gmail.connect():
                sources["gmail"] = self.gmail.fetch_as_text(max_results=20, days_back=3)
        except Exception as e:
            logger.warning(f"Gmail fetch failed: {e}")

        # WhatsApp
        try:
            text = self.whatsapp.fetch_as_text(last_n=80)
            if "No WhatsApp" not in text:
                sources["whatsapp"] = text
        except Exception as e:
            logger.warning(f"WhatsApp parse failed: {e}")

        # Call records
        try:
            text = self.calls.fetch_as_text(last_n=30)
            if "No call records" not in text:
                sources["call_records"] = text
        except Exception as e:
            logger.warning(f"Call records parse failed: {e}")

        return sources

    def extract_todos(self, sources: dict[str, str] | None = None) -> list[ExtractedTodo]:
        """Extract TODOs from all sources using LLM."""
        if sources is None:
            sources = self.gather_all_sources()

        if not sources:
            logger.warning("No data sources available for TODO extraction")
            return []

        # Combine all source text
        combined = "\n\n".join(sources.values())

        # Call LLM
        settings = get_settings()
        llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            azure_deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            temperature=0.2,
        )

        response = llm.invoke([
            EXTRACTION_PROMPT,
            HumanMessage(content=f"Today is {datetime.now().strftime('%Y-%m-%d')}.\n\n{combined}"),
        ])

        # Parse JSON response
        try:
            raw = response.content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            todos_data = json.loads(raw)
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"LLM returned invalid JSON: {e}\nRaw: {response.content}")
            return []

        todos = [
            ExtractedTodo(
                title=t.get("title", "Untitled"),
                priority=t.get("priority", "medium"),
                due=t.get("due"),
                source=t.get("source", "unknown"),
                context=t.get("context", ""),
                people=t.get("people", []),
            )
            for t in todos_data
            if isinstance(t, dict)
        ]

        logger.info(f"Extracted {len(todos)} TODOs from {len(sources)} sources")
        return todos

    def extract_as_text(self) -> str:
        """Extract TODOs and format as readable text."""
        todos = self.extract_todos()
        if not todos:
            return "No actionable TODOs found across your sources."

        lines = [f"Found {len(todos)} actionable items:\n"]
        for i, t in enumerate(todos, 1):
            due = f" (due {t.due})" if t.due else ""
            people = f" — involving: {', '.join(t.people)}" if t.people else ""
            lines.append(
                f"  {i}. [{t.priority.upper()}] {t.title}{due}\n"
                f"     Source: {t.source} | {t.context}{people}\n"
            )
        return "\n".join(lines)
