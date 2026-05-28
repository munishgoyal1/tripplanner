"""Gmail connector — scan inbox for action items and follow-ups."""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


@dataclass
class EmailItem:
    """Normalized email summary for TODO extraction."""
    subject: str
    sender: str
    snippet: str
    body_preview: str
    date: str
    message_id: str
    labels: list[str]
    source: str = "gmail"


class GmailConnector:
    """Read emails from Gmail for TODO extraction."""

    def __init__(self):
        self._service = None

    def connect(self) -> bool:
        try:
            from multiagent.tools.google_auth import get_gmail_service
            self._service = get_gmail_service()
            return True
        except Exception as e:
            logger.error(f"Gmail connection failed: {e}")
            return False

    def fetch_recent_emails(
        self,
        max_results: int = 30,
        days_back: int = 7,
        query: str = "",
    ) -> list[EmailItem]:
        """Fetch recent emails from inbox.

        Args:
            max_results: Max emails to fetch.
            days_back: Only look at emails from the last N days.
            query: Additional Gmail search query (e.g. 'is:starred', 'from:boss@co.com').
        """
        if not self._service:
            return []

        after_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y/%m/%d")
        full_query = f"after:{after_date} {query}".strip()

        try:
            results = self._service.users().messages().list(
                userId="me", q=full_query, maxResults=max_results
            ).execute()
        except Exception as e:
            logger.error(f"Gmail list failed: {e}")
            return []

        messages = results.get("messages", [])
        items: list[EmailItem] = []

        for msg_ref in messages:
            try:
                msg = self._service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="full"
                ).execute()
                items.append(self._parse_message(msg))
            except Exception as e:
                logger.warning(f"Failed to fetch message {msg_ref['id']}: {e}")

        logger.info(f"Fetched {len(items)} emails from Gmail")
        return items

    def _parse_message(self, msg: dict) -> EmailItem:
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        sender = headers.get("from", "unknown")
        date_str = headers.get("date", "")

        try:
            date_parsed = parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_parsed = date_str

        body_preview = self._extract_body(msg["payload"])

        return EmailItem(
            subject=subject,
            sender=sender,
            snippet=msg.get("snippet", ""),
            body_preview=body_preview[:500],  # cap preview length
            date=date_parsed,
            message_id=msg["id"],
            labels=msg.get("labelIds", []),
        )

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from email payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            text = self._extract_body(part)
            if text:
                return text

        return ""

    def fetch_as_text(self, **kwargs) -> str:
        """Fetch emails and format as text for LLM consumption."""
        items = self.fetch_recent_emails(**kwargs)
        if not items:
            return "No recent emails found (or not connected)."

        lines = ["=== RECENT EMAILS ===\n"]
        for i, e in enumerate(items, 1):
            lines.append(
                f"{i}. From: {e.sender}\n"
                f"   Subject: {e.subject}\n"
                f"   Date: {e.date}\n"
                f"   Preview: {e.snippet}\n"
            )
        return "\n".join(lines)
