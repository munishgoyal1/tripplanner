"""WhatsApp chat export parser — extract messages from exported .txt files.

WhatsApp → Chat → Export Chat (without media) produces a .txt file.
This parser handles both 12h and 24h timestamp formats across locales.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Common WhatsApp export formats:
#   [1/15/23, 2:30:45 PM] John: message
#   1/15/23, 14:30 - John: message
#   [2023-01-15, 14:30:45] John: message
_PATTERNS = [
    # [MM/DD/YY, H:MM:SS AM/PM] Sender: msg
    re.compile(
        r"\[?(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm]?)\]?\s*[-–]?\s*"
        r"(.+?):\s(.+)"
    ),
    # MM/DD/YY, HH:MM - Sender: msg (24h)
    re.compile(
        r"\[?(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*"
        r"(.+?):\s(.+)"
    ),
    # [YYYY-MM-DD, HH:MM:SS] Sender: msg
    re.compile(
        r"\[?(\d{4}-\d{2}-\d{2},?\s+\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*"
        r"(.+?):\s(.+)"
    ),
]


@dataclass
class WhatsAppMessage:
    """A single parsed WhatsApp message."""
    timestamp: str
    sender: str
    text: str
    chat_name: str
    source: str = "whatsapp"


class WhatsAppParser:
    """Parse WhatsApp chat export files."""

    def __init__(self, exports_dir: str = "data/whatsapp"):
        self.exports_dir = Path(exports_dir)

    def parse_file(self, filepath: str | Path) -> list[WhatsAppMessage]:
        """Parse a single WhatsApp chat export .txt file."""
        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning(f"WhatsApp export not found: {filepath}")
            return []

        chat_name = filepath.stem.replace("WhatsApp Chat with ", "").replace("_", " ")
        messages: list[WhatsAppMessage] = []
        current_msg: WhatsAppMessage | None = None

        for line in filepath.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = self._parse_line(line, chat_name)
            if parsed:
                if current_msg:
                    messages.append(current_msg)
                current_msg = parsed
            elif current_msg:
                # Continuation of previous message
                current_msg.text += f"\n{line.strip()}"

        if current_msg:
            messages.append(current_msg)

        logger.info(f"Parsed {len(messages)} messages from {filepath.name}")
        return messages

    def _parse_line(self, line: str, chat_name: str) -> WhatsAppMessage | None:
        for pattern in _PATTERNS:
            m = pattern.match(line.strip())
            if m:
                return WhatsAppMessage(
                    timestamp=m.group(1).strip(),
                    sender=m.group(2).strip(),
                    text=m.group(3).strip(),
                    chat_name=chat_name,
                )
        return None

    def parse_all_exports(self) -> list[WhatsAppMessage]:
        """Parse all .txt files in the exports directory."""
        if not self.exports_dir.exists():
            logger.info(f"WhatsApp exports dir not found: {self.exports_dir}")
            return []

        all_messages: list[WhatsAppMessage] = []
        for txt_file in sorted(self.exports_dir.glob("*.txt")):
            all_messages.extend(self.parse_file(txt_file))

        logger.info(f"Total WhatsApp messages parsed: {len(all_messages)}")
        return all_messages

    def fetch_as_text(self, last_n: int = 100) -> str:
        """Parse all exports and return last N messages as text for LLM."""
        messages = self.parse_all_exports()
        if not messages:
            return (
                "No WhatsApp messages found. "
                f"Export chats to {self.exports_dir}/ as .txt files."
            )

        recent = messages[-last_n:]
        lines = ["=== WHATSAPP MESSAGES ===\n"]
        for i, m in enumerate(recent, 1):
            lines.append(
                f"{i}. [{m.timestamp}] {m.chat_name} — {m.sender}: {m.text}"
            )
        return "\n".join(lines)
