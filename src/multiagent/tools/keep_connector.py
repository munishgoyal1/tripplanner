"""Google Keep connector — pull notes and lists for TODO extraction.

Uses gkeepapi (unofficial, reverse-engineered Google Keep client).
Requires a Google App Password (not your main password) since Keep has no official API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import gkeepapi

from multiagent.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class KeepItem:
    """Normalized item pulled from Google Keep."""
    title: str
    text: str
    source: str = "google_keep"
    labels: list[str] = field(default_factory=list)
    checked: bool = False
    timestamp: str = ""
    note_type: str = "note"  # "note" or "list"


class KeepConnector:
    """Read notes and checklists from Google Keep."""

    def __init__(self):
        self._keep = gkeepapi.Keep()
        self._logged_in = False

    def login(self, email: str | None = None, master_token: str | None = None) -> bool:
        """Authenticate to Google Keep.

        Preferred: use a master token (obtained once via OAuth).
        Fallback: use email + app password from env.
        """
        settings = get_settings()
        email = email or settings.google_keep_email
        master_token = master_token or settings.google_keep_token

        if not email:
            logger.warning("Google Keep email not configured (GOOGLE_KEEP_EMAIL)")
            return False

        try:
            if master_token:
                self._keep.resume(email, master_token)
            else:
                # App password flow — set GOOGLE_KEEP_APP_PASSWORD
                app_password = settings.google_keep_app_password
                if not app_password:
                    logger.warning("Set GOOGLE_KEEP_TOKEN or GOOGLE_KEEP_APP_PASSWORD")
                    return False
                self._keep.login(email, app_password)
            self._logged_in = True
            self._keep.sync()
            return True
        except Exception as e:
            logger.error(f"Google Keep login failed: {e}")
            return False

    def fetch_notes(
        self,
        include_archived: bool = False,
        include_trashed: bool = False,
        labels: list[str] | None = None,
    ) -> list[KeepItem]:
        """Fetch all notes/lists from Keep, returning normalized KeepItems."""
        if not self._logged_in:
            return []

        self._keep.sync()
        items: list[KeepItem] = []

        all_notes = self._keep.all()
        for note in all_notes:
            if not include_archived and note.archived:
                continue
            if not include_trashed and note.trashed:
                continue

            note_labels = [lbl.name for lbl in note.labels.all()]
            if labels and not any(l in note_labels for l in labels):
                continue

            ts = note.timestamps.updated.strftime("%Y-%m-%d %H:%M") if note.timestamps.updated else ""

            if hasattr(note, "items") and note.items:
                # It's a checklist — each item becomes a KeepItem
                for li in note.items:
                    items.append(KeepItem(
                        title=note.title or "Untitled list",
                        text=li.text,
                        labels=note_labels,
                        checked=li.checked,
                        timestamp=ts,
                        note_type="list",
                    ))
            else:
                items.append(KeepItem(
                    title=note.title or "Untitled",
                    text=note.text or "",
                    labels=note_labels,
                    timestamp=ts,
                    note_type="note",
                ))

        logger.info(f"Fetched {len(items)} items from Google Keep")
        return items

    def fetch_as_text(self, **kwargs) -> str:
        """Fetch notes and format as a single text block for LLM consumption."""
        items = self.fetch_notes(**kwargs)
        if not items:
            return "No Google Keep notes found (or not logged in)."

        lines = ["=== GOOGLE KEEP NOTES ===\n"]
        for i, item in enumerate(items, 1):
            status = "[✓]" if item.checked else "[ ]" if item.note_type == "list" else ""
            lines.append(
                f"{i}. {status} {item.title}: {item.text} "
                f"(labels: {', '.join(item.labels) or 'none'}, updated: {item.timestamp})"
            )
        return "\n".join(lines)
