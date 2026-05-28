"""Todo Agent — manage tasks, reminders, and follow-ups.

Includes tools for:
  - Manual TODO management (add, list, complete, delete)
  - Auto-extraction from Google Keep, Gmail, WhatsApp, and call records
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# In-memory store (will move to Cosmos DB)
# ---------------------------------------------------------------------------

_todos: list[dict] = []


# ---------------------------------------------------------------------------
# Manual TODO tools
# ---------------------------------------------------------------------------

@tool
def add_todo(title: str, due: str | None = None, priority: str = "medium") -> str:
    """Add a new TODO item. Priority: low/medium/high."""
    item = {
        "id": len(_todos) + 1,
        "title": title,
        "due": due,
        "priority": priority,
        "done": False,
        "source": "manual",
    }
    _todos.append(item)
    return f"Added TODO #{item['id']}: {title}"


@tool
def list_todos(include_done: bool = False) -> str:
    """List all TODO items. Set include_done=True to see completed ones too."""
    items = _todos if include_done else [t for t in _todos if not t["done"]]
    if not items:
        return "No TODOs found."
    lines = []
    for t in items:
        status = "✓" if t["done"] else "○"
        due = f" (due {t['due']})" if t["due"] else ""
        src = f" [{t.get('source', 'manual')}]" if t.get("source", "manual") != "manual" else ""
        lines.append(f"  {status} #{t['id']} [{t['priority']}] {t['title']}{due}{src}")
    return "\n".join(lines)


@tool
def complete_todo(todo_id: int) -> str:
    """Mark a TODO as done by its ID."""
    for t in _todos:
        if t["id"] == todo_id:
            t["done"] = True
            return f"Completed TODO #{todo_id}: {t['title']}"
    return f"TODO #{todo_id} not found."


@tool
def delete_todo(todo_id: int) -> str:
    """Delete a TODO by its ID."""
    for i, t in enumerate(_todos):
        if t["id"] == todo_id:
            _todos.pop(i)
            return f"Deleted TODO #{todo_id}: {t['title']}"
    return f"TODO #{todo_id} not found."


# ---------------------------------------------------------------------------
# Source-scanning tools
# ---------------------------------------------------------------------------

@tool
def scan_all_sources() -> str:
    """Scan Google Keep, Gmail, WhatsApp, and call records to auto-extract TODOs.

    This uses the LLM to identify actionable items from all connected sources
    and adds them to your TODO list.
    """
    from multiagent.tools.todo_extractor import TodoExtractor

    extractor = TodoExtractor()
    extracted = extractor.extract_todos()

    if not extracted:
        return "No actionable TODOs found. Make sure at least one source is configured."

    added = 0
    for t in extracted:
        # Avoid duplicates — check if a similar title already exists
        exists = any(
            existing["title"].lower() == t.title.lower()
            for existing in _todos
        )
        if exists:
            continue

        item = {
            "id": len(_todos) + 1,
            "title": t.title,
            "due": t.due,
            "priority": t.priority,
            "done": False,
            "source": t.source,
            "context": t.context,
            "people": t.people,
        }
        _todos.append(item)
        added += 1

    return (
        f"Scanned all sources. Found {len(extracted)} actionable items, "
        f"added {added} new TODOs (skipped {len(extracted) - added} duplicates).\n\n"
        + list_todos.invoke({"include_done": False})
    )


@tool
def scan_keep() -> str:
    """Scan only Google Keep notes and checklists for TODO items."""
    from multiagent.tools.keep_connector import KeepConnector
    from multiagent.tools.todo_extractor import TodoExtractor

    keep = KeepConnector()
    if not keep.login():
        return "Google Keep not configured. Set GOOGLE_KEEP_EMAIL and GOOGLE_KEEP_TOKEN in .env."
    text = keep.fetch_as_text()
    extractor = TodoExtractor()
    extracted = extractor.extract_todos(sources={"google_keep": text})
    return _ingest_extracted(extracted, "Google Keep")


@tool
def scan_gmail(days_back: int = 3, query: str = "") -> str:
    """Scan recent Gmail messages for action items and follow-ups.

    Args:
        days_back: How many days of email to scan (default 3).
        query: Optional Gmail filter (e.g. 'is:starred', 'from:boss@co.com').
    """
    from multiagent.tools.gmail_connector import GmailConnector
    from multiagent.tools.todo_extractor import TodoExtractor

    gmail = GmailConnector()
    if not gmail.connect():
        return "Gmail not connected. Run Google OAuth setup first."
    text = gmail.fetch_as_text(days_back=days_back, query=query)
    extractor = TodoExtractor()
    extracted = extractor.extract_todos(sources={"gmail": text})
    return _ingest_extracted(extracted, "Gmail")


@tool
def scan_whatsapp() -> str:
    """Scan exported WhatsApp chats for action items and commitments."""
    from multiagent.tools.todo_extractor import TodoExtractor
    from multiagent.tools.whatsapp_parser import WhatsAppParser

    wa = WhatsAppParser()
    text = wa.fetch_as_text()
    if "No WhatsApp" in text:
        return text
    extractor = TodoExtractor()
    extracted = extractor.extract_todos(sources={"whatsapp": text})
    return _ingest_extracted(extracted, "WhatsApp")


@tool
def scan_calls() -> str:
    """Scan call records for missed calls and follow-ups needed."""
    from multiagent.tools.call_records_parser import CallRecordParser
    from multiagent.tools.todo_extractor import TodoExtractor

    calls = CallRecordParser()
    text = calls.fetch_as_text()
    if "No call records" in text:
        return text
    extractor = TodoExtractor()
    extracted = extractor.extract_todos(sources={"call_records": text})
    return _ingest_extracted(extracted, "Call Records")


def _ingest_extracted(extracted: list, source_name: str) -> str:
    """Add extracted TODOs to the store, deduplicating."""
    if not extracted:
        return f"No actionable items found in {source_name}."

    added = 0
    for t in extracted:
        exists = any(e["title"].lower() == t.title.lower() for e in _todos)
        if exists:
            continue
        _todos.append({
            "id": len(_todos) + 1,
            "title": t.title,
            "due": t.due,
            "priority": t.priority,
            "done": False,
            "source": t.source,
            "context": t.context,
            "people": t.people,
        })
        added += 1

    return (
        f"Scanned {source_name}: found {len(extracted)} items, added {added} new TODOs.\n\n"
        + list_todos.invoke({"include_done": False})
    )


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

TODO_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Todo Agent. You help the user manage their personal task list.

You have two modes:
1. **Manual**: add, list, complete, delete TODOs directly.
2. **Auto-scan**: pull actionable items from the user's connected sources:
   - Google Keep (notes & checklists)
   - Gmail (emails needing replies/actions)
   - WhatsApp (exported chats with commitments)
   - Call records (missed calls needing follow-up)

When the user says "scan my stuff", "build my TODOs", "check all sources", etc. — use scan_all_sources.
For individual sources, use scan_keep, scan_gmail, scan_whatsapp, or scan_calls.
Always show the resulting TODO list after scanning.
""")

TODO_TOOLS = [
    add_todo, list_todos, complete_todo, delete_todo,
    scan_all_sources, scan_keep, scan_gmail, scan_whatsapp, scan_calls,
]
