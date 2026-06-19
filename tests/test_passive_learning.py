"""Tests for the post-turn passive-learning sweep (safety net)."""

import shutil
from pathlib import Path

import pytest

from tripplanner.tools import passive_learning, user_preferences
from tripplanner.tools.user_preferences import load_preferences

_TEST_DIR = Path.home() / ".tripplanner_passive_test"
_TEST_FILE = _TEST_DIR / "user_preferences.json"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)
    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


class TestHasLearnableSignal:
    @pytest.mark.parametrize("text", ["ok", "yes", "book it", "do it", "sounds good"])
    def test_trivial_messages_skipped(self, text):
        assert passive_learning.has_learnable_signal(text) is False

    @pytest.mark.parametrize(
        "text",
        [
            "I am vegetarian and my wife loves hiking",
            "We always prefer boutique hotels",
            "I'm allergic to peanuts",
            "my daughter is 6 years old",
        ],
    )
    def test_personal_messages_flagged(self, text):
        assert passive_learning.has_learnable_signal(text) is True


class TestLearnFromMessage:
    def test_skips_trivial_without_calling_extractor(self, monkeypatch):
        called = {"n": 0}

        def _fake(_text):
            called["n"] += 1
            return {}

        monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", _fake)
        assert passive_learning.learn_from_message("book it") == []
        assert called["n"] == 0

    def test_overlays_extracted_additively(self, monkeypatch):
        user_preferences.update_preferences({"interests": ["museums"]})
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"interests": ["hiking"]},
        )
        touched = passive_learning.learn_from_message("I love hiking in the mountains")
        assert "interests" in touched
        prefs = load_preferences()
        assert sorted(prefs["interests"]) == ["hiking", "museums"]

    def test_appends_learned_notes_deduped(self, monkeypatch):
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"_learned_notes_to_append": [{"note": "Prefers aisle seats", "source": "stated"}]},
        )
        passive_learning.learn_from_message("I always prefer an aisle seat")
        passive_learning.learn_from_message("I always prefer an aisle seat")
        prefs = load_preferences()
        notes = [n["note"] for n in prefs["learned_notes"]]
        assert notes.count("Prefers aisle seats") == 1

    def test_swallows_extractor_errors(self, monkeypatch):
        def _boom(_t):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", _boom)
        # Must not raise.
        assert passive_learning.learn_from_message("I am vegetarian and love hiking") == []

    def test_noop_when_extractor_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            passive_learning.about_me_extractor, "extract_about_me", lambda _t: {}
        )
        assert passive_learning.learn_from_message("I am vegetarian and love hiking") == []
