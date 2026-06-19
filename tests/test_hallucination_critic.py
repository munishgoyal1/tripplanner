"""Tests for src/tripplanner/hallucination_critic.py."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tripplanner.hallucination_critic import (
    critique,
    format_heads_up,
)


def _msgs(*tool_contents: str) -> list:
    """Build a fake message list with one ToolMessage per content string."""
    return [
        HumanMessage(content="plan paris"),
        *[ToolMessage(content=c, tool_call_id=f"t{i}") for i, c in enumerate(tool_contents)],
        AIMessage(content=""),
    ]


def test_no_evidence_returns_empty():
    # Conversational reply with no tool calls — we have nothing to check.
    assert critique("The Eiffel Tower is in Paris.", []) == []


def test_empty_reply_returns_empty():
    assert critique("", _msgs("hotels: $200")) == []


def test_price_in_evidence_passes():
    msgs = _msgs("Hotel Le Marais — $245 / night incl. breakfast")
    assert critique("Hotel Le Marais is $245/night.", msgs) == []


def test_price_not_in_evidence_flagged():
    msgs = _msgs("Hotel Le Marais — $245 / night")
    issues = critique("Hotel Le Marais is $999/night.", msgs)
    assert any("$999" in i for i in issues)


def test_currency_with_space_normalised():
    # Agent writes "$ 245" with a space; evidence has "$245" — should match.
    msgs = _msgs("Hotel — $245 / night")
    assert critique("Hotel is $ 245 / night.", msgs) == []


def test_inr_amount_in_evidence_passes():
    msgs = _msgs("Taj Mahal Palace ₹18,500 per night")
    assert critique("Taj Mahal Palace runs ₹18,500 a night.", msgs) == []


def test_price_matches_across_currency_formatting():
    # Agent reformats INR 19500 (tool output) as ₹19,500 — same magnitude,
    # different symbol/grouping. Should be considered grounded.
    msgs = _msgs("IndiGo DEL-GOI round trip: INR 19500")
    assert critique("Flights are ₹19,500.", msgs) == []


def test_plain_thousands_price_matches_grouped_reply():
    msgs = _msgs("Hotel total INR 70000")
    assert critique("The hotel is ₹70,000.", msgs) == []


def test_unrelated_price_still_flagged_with_numeric_match():
    msgs = _msgs("Hotel total INR 70000")
    issues = critique("The hotel is ₹85,000.", msgs)
    assert any("85,000" in i for i in issues)


def test_time_ampm_spacing_normalised():
    # Evidence "10:30 AM" vs reply "10:30am" — spacing shouldn't matter.
    msgs = _msgs("Tour departs 10:30 AM daily")
    assert critique("The tour leaves at 10:30am.", msgs) == []


def test_time_in_evidence_passes():
    msgs = _msgs("Louvre opens 9:00 AM, closes 6:00 PM (Tue closed)")
    assert critique("Louvre opens at 9:00 AM.", msgs) == []


def test_time_not_in_evidence_flagged():
    msgs = _msgs("Louvre opens 9:00 AM, closes 6:00 PM")
    issues = critique("Eiffel Tower opens at 5:30 AM.", msgs)
    assert any("5:30" in i for i in issues)


def test_url_in_evidence_passes():
    msgs = _msgs("Book at https://booking.example.com/hotel/abc")
    assert critique("Book at https://booking.example.com/hotel/abc.", msgs) == []


def test_url_not_in_evidence_flagged():
    msgs = _msgs("Book at https://booking.example.com/hotel/abc")
    issues = critique("Book at https://fake.example.com/x.", msgs)
    assert any("fake.example.com" in i for i in issues)


def test_trailing_punctuation_on_url_stripped():
    # Agent writes "see https://x.com)." — punct shouldn't break the check.
    msgs = _msgs("see https://x.com for more")
    assert critique("(see https://x.com).", msgs) == []


def test_multiple_unverified_claims_listed():
    msgs = _msgs("Just one hotel, no prices listed")
    issues = critique("Hotel is $500 and opens at 8:00 AM.", msgs)
    assert len(issues) == 2


def test_duplicate_claim_only_listed_once():
    msgs = _msgs("nothing relevant")
    issues = critique("$500 and $500 again.", msgs)
    assert len(issues) == 1


def test_format_heads_up_empty_returns_empty():
    assert format_heads_up([]) == ""


def test_format_heads_up_renders_bullets():
    out = format_heads_up(["price $500 was not found", "URL https://x.com was not found"])
    assert "Heads up" in out
    assert "- price $500" in out
    assert "- URL https://x.com" in out


def test_critic_handles_list_content_in_tool_message():
    # Some tool messages carry list[dict] (multi-part). Critic should flatten.
    msgs = [
        ToolMessage(
            content=[{"text": "Hotel — $245 / night"}],
            tool_call_id="t0",
        ),
        AIMessage(content=""),
    ]
    assert critique("Hotel is $245/night.", msgs) == []

