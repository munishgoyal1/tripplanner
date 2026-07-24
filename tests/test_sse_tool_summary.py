"""Unit tests for the SSE tool-input summarizer used in /chat/stream."""

from __future__ import annotations

from tripplanner.api import _auto_persist_itinerary, _summarize_tool_input


def test_summarize_none_is_empty() -> None:
    assert _summarize_tool_input(None) == ""


def test_summarize_dict_emits_key_value_pairs() -> None:
    out = _summarize_tool_input({"city": "Paris", "nights": 5})
    assert "city=Paris" in out
    assert "nights=5" in out


def test_summarize_unwraps_input_wrapper() -> None:
    # LangChain often wraps the args in {"input": {...}}.
    out = _summarize_tool_input({"input": {"q": "best ramen"}})
    assert out == "q=best ramen"


def test_summarize_truncates_long_values() -> None:
    long = "x" * 200
    out = _summarize_tool_input({"q": long}, max_len=80)
    assert len(out) <= 80
    # Either the per-value cap (40 chars → "...") or the overall cap (→ "…")
    # has to have kicked in, otherwise we leaked the whole 200-char string.
    assert out.endswith("...") or out.endswith("\u2026")
    assert long not in out


def test_summarize_handles_list_values() -> None:
    out = _summarize_tool_input({"tags": ["a", "b", "c"]})
    assert "tags=" in out
    assert "a" in out and "c" in out


def test_auto_persist_itinerary_invokes_update_tool(monkeypatch) -> None:
    from tripplanner.tools import trip_planner

    calls: list[dict] = []

    class FakeUpdateTool:
        def invoke(self, value: dict) -> None:
            calls.append(value)

    monkeypatch.setattr(trip_planner, "update_trip_plan", FakeUpdateTool())

    _auto_persist_itinerary(
        "Day 1 - Arrival\nVisit **Louvre Museum**.\n"
        "Day 2 - Montmartre\nExplore **Sacré-Cœur**."
    )

    assert len(calls) == 1
    assert "updates_json" in calls[0]
