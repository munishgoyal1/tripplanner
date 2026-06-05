"""Tests for tools/memory_recall.py (BM25-lite recall over user prefs)."""

from __future__ import annotations

import json

from multiagent.tools import memory_recall


_PREFS = {
    "learned_notes": [
        {"note": "Father uses a walking stick — needs elevator access at hotels.", "source": "stated", "at": "2026-04-12"},
        {"note": "Spouse prefers vegetarian Indian meals at dinner.", "source": "inferred", "at": "2026-04-12"},
        {"note": "Allergic to peanuts; restaurants must confirm.", "source": "stated", "at": "2026-03-01"},
    ],
    "past_trip_mentions": [
        {"destination": "Goa", "when": "2024-12", "with_whom": "family", "sentiment": "loved it", "notes": "beach resort, kids loved the pool"},
        {"destination": "Manali", "when": "2023-06", "with_whom": "friends", "sentiment": "ok", "notes": "too crowded in season"},
    ],
    "past_trips": [
        {"destination": "Bali", "dates": "2025-09", "rating": 5, "notes": "snorkelling was the highlight"},
    ],
    "family_members": [
        {"relationship": "father", "name": "Ramesh", "age": 72, "dietary": "vegetarian", "mobility": "uses walking stick", "interests": ["temples"], "notes": "needs ground-floor room"},
    ],
    "interests": ["beaches", "photography", "history"],
    "dislikes": ["crowded markets"],
    "about_me": "I live in Bengaluru. I work as a software engineer. I prefer aisle seats on long flights.",
}


def test_tokenize_strips_stopwords_and_punctuation():
    assert "the" not in memory_recall._tokenize("the quick brown fox")
    assert "brown" in memory_recall._tokenize("the quick brown fox")


def test_collect_items_pulls_all_sources():
    items = memory_recall._collect_items(_PREFS)
    kinds = {it["kind"] for it in items}
    assert kinds >= {
        "learned_note", "past_trip_mention", "past_trip",
        "family_member", "interest", "dislike", "about_me",
    }


def test_recall_finds_mobility_note(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = json.loads(memory_recall.recall_relevant_memory.invoke({"query": "father elevator", "top_k": 3}))
    texts = " ".join(r["text"].lower() for r in out["results"])
    assert "elevator" in texts or "walking stick" in texts


def test_recall_finds_past_goa_trip(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = json.loads(memory_recall.recall_relevant_memory.invoke({"query": "Goa beach with kids", "top_k": 2}))
    top = out["results"][0]
    assert "goa" in top["text"].lower()


def test_recall_returns_about_me_for_home_question(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = json.loads(memory_recall.recall_relevant_memory.invoke({"query": "where do I live"}))
    texts = " ".join(r["text"].lower() for r in out["results"])
    assert "bengaluru" in texts


def test_recall_empty_query_errors(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = memory_recall.recall_relevant_memory.invoke({"query": ""})
    assert "required" in out.lower()


def test_recall_no_match_returns_empty_results(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = json.loads(memory_recall.recall_relevant_memory.invoke({"query": "xyzplutonium"}))
    assert out["results"] == []


def test_recall_respects_top_k_cap(monkeypatch):
    monkeypatch.setattr(memory_recall, "load_preferences", lambda: _PREFS)
    out = json.loads(memory_recall.recall_relevant_memory.invoke({"query": "trip family beach", "top_k": 50}))
    assert len(out["results"]) <= 10  # clamped to 10
