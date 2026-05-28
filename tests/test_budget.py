"""Tests for the budget agent tools."""

from multiagent.agents.budget_agent import _expenses, add_expense, budget_summary, list_expenses


def setup_function():
    _expenses.clear()


def test_add_expense():
    result = add_expense.invoke({"amount": 25.50, "category": "food", "description": "Lunch"})
    assert "$25.50" in result
    assert len(_expenses) == 1


def test_list_expenses():
    add_expense.invoke({"amount": 10.0, "category": "transport"})
    add_expense.invoke({"amount": 50.0, "category": "food"})
    result = list_expenses.invoke({})
    assert "transport" in result
    assert "food" in result
    assert "Total: $60.00" in result


def test_budget_summary():
    add_expense.invoke({"amount": 20.0, "category": "food"})
    add_expense.invoke({"amount": 30.0, "category": "food"})
    add_expense.invoke({"amount": 15.0, "category": "transport"})
    result = budget_summary.invoke({})
    assert "food: $50.00" in result
    assert "transport: $15.00" in result
    assert "Grand Total: $65.00" in result
