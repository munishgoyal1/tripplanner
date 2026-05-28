"""Tests for the todo agent tools."""

from multiagent.agents.todo_agent import _todos, add_todo, complete_todo, delete_todo, list_todos


def setup_function():
    _todos.clear()


def test_add_todo():
    result = add_todo.invoke({"title": "Buy groceries", "priority": "high"})
    assert "Added TODO #1" in result
    assert len(_todos) == 1
    assert _todos[0]["source"] == "manual"


def test_list_todos_empty():
    result = list_todos.invoke({"include_done": False})
    assert "No TODOs" in result


def test_list_todos():
    add_todo.invoke({"title": "Task 1"})
    add_todo.invoke({"title": "Task 2"})
    result = list_todos.invoke({"include_done": False})
    assert "Task 1" in result
    assert "Task 2" in result


def test_complete_todo():
    add_todo.invoke({"title": "Finish report"})
    result = complete_todo.invoke({"todo_id": 1})
    assert "Completed" in result
    assert _todos[0]["done"] is True


def test_delete_todo():
    add_todo.invoke({"title": "Temp task"})
    result = delete_todo.invoke({"todo_id": 1})
    assert "Deleted" in result
    assert len(_todos) == 0
