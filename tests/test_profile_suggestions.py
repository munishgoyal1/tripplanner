import pytest

from tripplanner.tools import profile_suggestions, user_preferences


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", tmp_path)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", tmp_path / "preferences.json")


def queue(payload):
    return profile_suggestions.queue_suggestions(
        profile_suggestions.build_suggestions(payload, [], "A possible preference")
    )


def test_optional_suggestion_does_not_change_durable_profile():
    [notice] = queue({"family_members": [{"name": "Rhea", "relationship": "partner"}]})
    assert not user_preferences.load_preferences()["family_members"]
    assert profile_suggestions.list_pending()[0]["id"] == notice["id"]


def test_save_optional_suggestion_adds_family_member():
    [notice] = queue({"family_members": [{"name": "Rhea", "relationship": "partner"}]})
    assert profile_suggestions.resolve(notice["id"], "save")["status"] == "saved"
    assert user_preferences.load_preferences()["family_members"] == [
        {"name": "Rhea", "relationship": "partner"}
    ]
    assert profile_suggestions.list_pending() == []


def test_dismissed_optional_suggestion_does_not_repeat():
    [notice] = queue({"interests": ["hiking"]})
    assert profile_suggestions.resolve(notice["id"], "dismiss")["status"] == "dismissed"
    assert not user_preferences.load_preferences()["interests"]
    assert queue({"interests": ["hiking"]}) == []
