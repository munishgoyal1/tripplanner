from __future__ import annotations

import pytest

from tripplanner.tools import user_preferences


@pytest.fixture
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", tmp_path)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", tmp_path / "user_preferences.json")


def test_set_family_member_adds_a_new_traveller(isolated_preferences) -> None:
    updated = user_preferences.set_family_member(
        original_relationship=None,
        original_name=None,
        relationship="partner",
        name="Rhea",
        age=None,
        dietary=["vegetarian"],
        mobility=[],
        interests=["museums"],
        notes="Likes relaxed mornings",
    )

    assert updated["family_members"] == [{
        "relationship": "partner",
        "name": "Rhea",
        "age": None,
        "dietary": ["vegetarian"],
        "mobility": [],
        "interests": ["museums"],
        "notes": "Likes relaxed mornings",
    }]


def test_set_family_member_replaces_rather_than_merges(isolated_preferences) -> None:
    user_preferences.set_family_member(
        original_relationship=None, original_name=None,
        relationship="child", name="Kabir", age=8,
        dietary=["vegetarian"], mobility=["shorter walks"], interests=["pool time"], notes="",
    )

    # Editing the same person and dropping a tag must actually drop it, not merge it back in.
    updated = user_preferences.set_family_member(
        original_relationship="child", original_name="Kabir",
        relationship="child", name="Kabir", age=9,
        dietary=[], mobility=["shorter walks"], interests=["pool time"], notes="",
    )

    assert updated["family_members"] == [{
        "relationship": "child",
        "name": "Kabir",
        "age": 9,
        "dietary": [],
        "mobility": ["shorter walks"],
        "interests": ["pool time"],
        "notes": None,
    }]


def test_set_family_member_supports_rename(isolated_preferences) -> None:
    user_preferences.set_family_member(
        original_relationship=None, original_name=None,
        relationship="friend", name="Sam", age=None, dietary=[], mobility=[], interests=[], notes="",
    )

    updated = user_preferences.set_family_member(
        original_relationship="friend", original_name="Sam",
        relationship="sibling", name="Samira", age=None, dietary=[], mobility=[], interests=[], notes="",
    )

    assert len(updated["family_members"]) == 1
    assert updated["family_members"][0]["relationship"] == "sibling"
    assert updated["family_members"][0]["name"] == "Samira"


def test_remove_family_member(isolated_preferences) -> None:
    user_preferences.set_family_member(
        original_relationship=None, original_name=None,
        relationship="partner", name="Rhea", age=None, dietary=[], mobility=[], interests=[], notes="",
    )

    updated = user_preferences.remove_family_member("partner", "Rhea")

    assert updated["family_members"] == []
