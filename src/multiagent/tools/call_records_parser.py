"""Call records parser — parse phone call logs from exports.

Supports:
  1. Google Takeout call log (JSON from Google Fi / Phone app)
  2. Generic CSV export (columns: number, name, type, date, duration)
  3. Android call log CSV exports (various backup apps)
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    """Normalized phone call record."""
    phone_number: str
    contact_name: str
    call_type: str  # incoming, outgoing, missed
    date: str
    duration_seconds: int
    source: str = "call_records"


class CallRecordParser:
    """Parse call log exports from various formats."""

    def __init__(self, data_dir: str = "data/calls"):
        self.data_dir = Path(data_dir)

    def parse_google_takeout(self, filepath: str | Path) -> list[CallRecord]:
        """Parse Google Takeout call log JSON.

        Google Takeout → My Activity → export includes calls in JSON.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            return []

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse Takeout JSON: {e}")
            return []

        records: list[CallRecord] = []

        # Google Takeout formats vary; handle common structures
        entries = data if isinstance(data, list) else data.get("calls", data.get("entries", []))

        for entry in entries:
            record = CallRecord(
                phone_number=entry.get("phoneNumber", entry.get("number", "unknown")),
                contact_name=entry.get("name", entry.get("contactName", "Unknown")),
                call_type=self._normalize_call_type(
                    entry.get("callType", entry.get("type", "unknown"))
                ),
                date=entry.get("timestamp", entry.get("date", "")),
                duration_seconds=int(entry.get("duration", entry.get("durationSeconds", 0))),
            )
            records.append(record)

        logger.info(f"Parsed {len(records)} call records from Google Takeout")
        return records

    def parse_csv(self, filepath: str | Path) -> list[CallRecord]:
        """Parse a generic CSV call log.

        Expected columns (flexible matching):
          number/phone, name/contact, type, date/time, duration
        """
        filepath = Path(filepath)
        if not filepath.exists():
            return []

        records: list[CallRecord] = []

        with open(filepath, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return []

            # Flexible column name matching
            col_map = self._detect_columns(reader.fieldnames)

            for row in reader:
                records.append(CallRecord(
                    phone_number=row.get(col_map["number"], "unknown"),
                    contact_name=row.get(col_map["name"], "Unknown"),
                    call_type=self._normalize_call_type(row.get(col_map["type"], "unknown")),
                    date=row.get(col_map["date"], ""),
                    duration_seconds=self._parse_duration(row.get(col_map["duration"], "0")),
                ))

        logger.info(f"Parsed {len(records)} call records from CSV")
        return records

    def _detect_columns(self, fieldnames: list[str]) -> dict[str, str]:
        """Auto-detect column names from CSV headers."""
        mapping: dict[str, str] = {"number": "", "name": "", "type": "", "date": "", "duration": ""}
        lower_fields = {f.lower().strip(): f for f in fieldnames}

        for key, candidates in {
            "number": ["number", "phone", "phonenumber", "phone_number", "phone number"],
            "name": ["name", "contact", "contactname", "contact_name", "contact name"],
            "type": ["type", "calltype", "call_type", "call type", "direction"],
            "date": ["date", "time", "datetime", "date_time", "timestamp", "date/time"],
            "duration": ["duration", "durationseconds", "duration_seconds", "length", "call duration"],
        }.items():
            for c in candidates:
                if c in lower_fields:
                    mapping[key] = lower_fields[c]
                    break

        return mapping

    def _normalize_call_type(self, raw: str) -> str:
        raw_lower = raw.lower().strip()
        if "miss" in raw_lower:
            return "missed"
        if "out" in raw_lower:
            return "outgoing"
        if "in" in raw_lower or "receive" in raw_lower:
            return "incoming"
        if "reject" in raw_lower:
            return "rejected"
        return raw_lower or "unknown"

    def _parse_duration(self, raw: str) -> int:
        try:
            return int(raw)
        except ValueError:
            # Handle "1:30" (min:sec) format
            parts = raw.split(":")
            if len(parts) == 2:
                try:
                    return int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    pass
            return 0

    def parse_all(self) -> list[CallRecord]:
        """Parse all call log files in the data directory."""
        if not self.data_dir.exists():
            logger.info(f"Call records dir not found: {self.data_dir}")
            return []

        records: list[CallRecord] = []

        for json_file in self.data_dir.glob("*.json"):
            records.extend(self.parse_google_takeout(json_file))
        for csv_file in self.data_dir.glob("*.csv"):
            records.extend(self.parse_csv(csv_file))

        # Sort by date descending
        records.sort(key=lambda r: r.date, reverse=True)
        logger.info(f"Total call records parsed: {len(records)}")
        return records

    def fetch_as_text(self, last_n: int = 50) -> str:
        """Parse all call logs and return as text for LLM consumption."""
        records = self.parse_all()
        if not records:
            return (
                "No call records found. "
                f"Place Google Takeout JSON or CSV call logs in {self.data_dir}/."
            )

        recent = records[:last_n]
        lines = ["=== RECENT CALL RECORDS ===\n"]
        for i, r in enumerate(recent, 1):
            dur_min = r.duration_seconds // 60
            dur_sec = r.duration_seconds % 60
            lines.append(
                f"{i}. [{r.date}] {r.call_type.upper()} — "
                f"{r.contact_name} ({r.phone_number}) — {dur_min}m {dur_sec}s"
            )

        # Highlight missed calls
        missed = [r for r in recent if r.call_type == "missed"]
        if missed:
            lines.append(f"\n⚠ {len(missed)} missed calls — may need follow-up")

        return "\n".join(lines)
