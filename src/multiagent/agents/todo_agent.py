"""Todo Agent — manage tasks, reminders, and follow-ups."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_todos: list[dict] = []  # in-memory for now; will move to Cosmos DB


@tool
def add_todo(title: str, due: str | None = None, priority: str = "medium") -> str:
    """Add a new TODO item. Priority: low/medium/high."""
    item = {"id": len(_todos) + 1, "title": title, "due": due, "priority": priority, "done": False}
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
        lines.append(f"  {status} #{t['id']} [{t['priority']}] {t['title']}{due}")
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
# Agent definition
# ---------------------------------------------------------------------------

TODO_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Todo Agent. You help the user manage their personal task list.
You can add, list, complete, and delete TODO items.
Always confirm actions clearly. If the user asks about priorities or due dates, help them organize.
""")

TODO_TOOLS = [add_todo, list_todos, complete_todo, delete_todo]
