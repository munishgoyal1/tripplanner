from pathlib import Path

import pytest

from tripplanner.tools import passive_learning, profile_suggestions, user_preferences


@pytest.fixture
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", tmp_path)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", tmp_path / "user_preferences.json")


def test_chat_learning_queues_without_durable_write(isolated_preferences, monkeypatch):
    monkeypatch.setattr(
        passive_learning.about_me_extractor,
        "extract_about_me",
        lambda _text: {"family_members": [{"name": "Rhea", "relationship": "partner"}]},
    )

    [suggestion_id] = passive_learning.learn_from_message("My partner Rhea prefers relaxed mornings")

    assert user_preferences.load_preferences().get("family_members") in (None, [])
    pending = profile_suggestions.list_pending()
    assert pending[0]["id"] == suggestion_id
    assert pending[0]["provenance"] == "suggested_from_chat"


def test_save_suggestion_adds_family_member(isolated_preferences, monkeypatch):
    monkeypatch.setattr(
        passive_learning.about_me_extractor,
        "extract_about_me",
        lambda _text: {"family_members": [{"name": "Rhea", "relationship": "partner"}]},
    )
    [suggestion_id] = passive_learning.learn_from_message("My partner Rhea prefers relaxed mornings")

    resolved = profile_suggestions.resolve(suggestion_id, "save")

    assert resolved and resolved["status"] == "saved"
    assert user_preferences.load_preferences()["family_members"] == [
        {"name": "Rhea", "relationship": "partner"}
    ]
    assert profile_suggestions.list_pending() == []


def test_dismiss_suggestion_does_not_write_or_repeat(isolated_preferences, monkeypatch):
    monkeypatch.setattr(
        passive_learning.about_me_extractor,
        "extract_about_me",
        lambda _text: {"interests": ["hiking"]},
    )
    [suggestion_id] = passive_learning.learn_from_message("I love hiking in the mountains")

    resolved = profile_suggestions.resolve(suggestion_id, "dismiss")

    assert resolved and resolved["status"] == "dismissed"
    assert user_preferences.load_preferences().get("interests") in (None, [])
    assert passive_learning.learn_from_message("I love hiking in the mountains") == []
