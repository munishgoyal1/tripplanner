"""Budget Agent — track expenses, manage budgets, financial summaries."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

_expenses: list[dict] = []  # in-memory for now


@tool
def add_expense(amount: float, category: str, description: str = "") -> str:
    """Record an expense. Category examples: food, transport, entertainment, bills."""
    entry = {
        "id": len(_expenses) + 1,
        "amount": amount,
        "category": category,
        "description": description,
    }
    _expenses.append(entry)
    return f"Recorded ${amount:.2f} under '{category}': {description or 'no description'}"


@tool
def list_expenses(category: str | None = None) -> str:
    """List recorded expenses, optionally filtered by category."""
    items = _expenses if not category else [e for e in _expenses if e["category"] == category]
    if not items:
        return "No expenses recorded."
    total = sum(e["amount"] for e in items)
    lines = [f"  #{e['id']} ${e['amount']:.2f} [{e['category']}] {e['description']}" for e in items]
    lines.append(f"\n  Total: ${total:.2f}")
    return "\n".join(lines)


@tool
def budget_summary() -> str:
    """Get a summary of spending by category."""
    if not _expenses:
        return "No expenses recorded yet."
    by_cat: dict[str, float] = {}
    for e in _expenses:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
    total = sum(by_cat.values())
    lines = [f"  {cat}: ${amt:.2f}" for cat, amt in sorted(by_cat.items())]
    lines.append(f"\n  Grand Total: ${total:.2f}")
    return "\n".join(lines)


BUDGET_SYSTEM_PROMPT = SystemMessage(content="""\
You are the Budget Agent. You help the user track expenses, set budgets,
and understand their spending patterns. Be clear about amounts and categories.
""")

BUDGET_TOOLS = [add_expense, list_expenses, budget_summary]
