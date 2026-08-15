"""Tests for the post-turn passive-learning sweep (safety net)."""

import shutil
from pathlib import Path

import pytest

from tripplanner.tools import passive_learning, profile_suggestions, user_preferences
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

    def test_queues_a_suggestion_instead_of_saving(self, monkeypatch):
        user_preferences.update_preferences({"interests": ["museums"]})
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"interests": ["hiking"]},
        )
        raised = passive_learning.learn_from_message("I love hiking in the mountains")

        assert len(raised) == 1
        # Nothing durable changed until the user confirms.
        assert load_preferences()["interests"] == ["museums"]
        pending = profile_suggestions.list_pending()
        assert [item["id"] for item in pending] == raised
        assert pending[0]["provenance"] == "suggested_from_chat"

    def test_confirming_a_suggestion_merges_it_additively(self, monkeypatch):
        user_preferences.update_preferences({"interests": ["museums"]})
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"interests": ["hiking"]},
        )
        [suggestion_id] = passive_learning.learn_from_message("I love hiking in the mountains")

        resolved = profile_suggestions.resolve(suggestion_id, "save")

        assert resolved["status"] == "saved"
        assert sorted(load_preferences()["interests"]) == ["hiking", "museums"]
        assert profile_suggestions.list_pending() == []

    def test_dismissed_suggestion_is_not_raised_again(self, monkeypatch):
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"interests": ["hiking"]},
        )
        [suggestion_id] = passive_learning.learn_from_message("I love hiking in the mountains")
        profile_suggestions.resolve(suggestion_id, "dismiss")

        assert passive_learning.learn_from_message("I love hiking in the mountains") == []
        assert profile_suggestions.list_pending() == []
        assert load_preferences().get("interests") in (None, [])

    def test_appends_learned_notes_deduped(self, monkeypatch):
        monkeypatch.setattr(
            passive_learning.about_me_extractor,
            "extract_about_me",
            lambda _t: {"_learned_notes_to_append": [{"note": "Prefers aisle seats", "source": "stated"}]},
        )
        first = passive_learning.learn_from_message("I always prefer an aisle seat")
        # The same sentence must not queue the question twice.
        assert passive_learning.learn_from_message("I always prefer an aisle seat") == []

        profile_suggestions.resolve(first[0], "save")
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
