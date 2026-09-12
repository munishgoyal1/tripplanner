"""Durable conversational learning without confirmation gates."""

import pytest

from tripplanner.tools import passive_learning, profile_suggestions, user_preferences
from tripplanner.tools.user_preferences import load_preferences


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", tmp_path)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", tmp_path / "preferences.json")


def extractor(monkeypatch, result):
    monkeypatch.setattr(
        passive_learning.about_me_extractor, "extract_about_me", lambda *a, **k: result
    )


def test_stated_facts_save_without_confirmation_and_can_be_undone(monkeypatch):
    user_preferences.update_preferences({"interests": ["museums"]})
    extractor(monkeypatch, {"profile": {"home_city": "Bangalore"}, "interests": ["hiking"]})
    passive_learning.learn_from_message("Bangalore is home. I love hiking.")
    prefs = load_preferences()
    assert prefs["profile"]["home_city"] == "Bangalore"
    assert prefs["interests"] == ["museums", "hiking"]
    [notice] = profile_suggestions.list_pending()
    assert notice["status"] == "saved"
    profile_suggestions.resolve(notice["id"], "undo")
    assert load_preferences()["profile"]["home_city"] is None
    assert load_preferences()["interests"] == ["museums"]
    assert passive_learning.learn_from_message("Bangalore is home. I love hiking.") == []


def test_correction_replaces_stale_scalar_and_schema_default(monkeypatch):
    user_preferences.update_preferences({"profile": {"home_city": "Delhi"}})
    extractor(monkeypatch, {"profile": {"home_city": "Bangalore"}, "budget_level": "luxury"})
    passive_learning.learn_from_message("I now live in Bangalore and prefer luxury stays.")
    assert load_preferences()["profile"]["home_city"] == "Bangalore"
    assert load_preferences()["budget_level"] == "luxury"


def test_undo_does_not_overwrite_a_newer_edit(monkeypatch):
    extractor(monkeypatch, {"profile": {"home_city": "Bangalore"}})
    passive_learning.learn_from_message("Bangalore is home")
    [notice] = profile_suggestions.list_pending()
    user_preferences.update_preferences({"profile": {"home_city": "Mumbai"}})
    profile_suggestions.resolve(notice["id"], "undo")
    assert load_preferences()["profile"]["home_city"] == "Mumbai"


def test_background_result_does_not_overwrite_a_concurrent_edit(monkeypatch):
    def extract(*args, **kwargs):
        user_preferences.update_preferences({"profile": {"home_city": "Mumbai"}})
        return {"profile": {"home_city": "Bangalore"}}
    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", extract)
    passive_learning.learn_from_message("Bangalore is home")
    assert load_preferences()["profile"]["home_city"] == "Mumbai"


def test_failure_survives_and_retries_on_next_turn(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", fail)
    assert passive_learning.learn_from_message("Bangalore is home") == []
    assert len(load_preferences()["_learning_pending"]) == 1
    extractor(monkeypatch, {"profile": {"home_city": "Bangalore"}})
    passive_learning.learn_from_message("ok")
    assert load_preferences()["profile"]["home_city"] == "Bangalore"
    assert load_preferences()["_learning_pending"] == []


def test_short_answer_uses_context_without_requiring_keywords(monkeypatch):
    seen = []
    def extract(prompt, **kwargs):
        seen.append((prompt, kwargs))
        return {"profile": {"home_city": "Bengaluru"}}
    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", extract)
    passive_learning.learn_from_message(
        "Bengaluru", [{"role": "ai", "text": "Which city is home?"}]
    )
    assert "Which city is home?" in seen[0][0]
    assert "NEW MESSAGE:\nBengaluru" in seen[0][0]
    assert seen[0][1] == {"conversation": True, "raise_on_error": True}
    assert load_preferences()["profile"]["home_city"] == "Bengaluru"


def test_mixed_trip_exception_does_not_discard_durable_part(monkeypatch):
    extractor(monkeypatch, {"profile": {"home_city": "Bangalore"}})
    passive_learning.learn_from_message("I live in Bangalore; 3-star is fine just for this trip.")
    assert load_preferences()["profile"]["home_city"] == "Bangalore"
    assert load_preferences()["hotel_preferences"]["star_rating_min"] == 3


def test_duplicate_family_fact_does_not_duplicate_roster(monkeypatch):
    user_preferences.update_preferences({"family_members": [{"relationship": "child", "age": 9}]})
    extractor(monkeypatch, {"family_members": [{"relationship": "child", "age": 10}]})
    passive_learning.learn_from_message("My child is now 10")
    assert load_preferences()["family_members"] == [{"relationship": "child", "age": 10}]


def test_noop_and_control_messages_do_not_create_notices(monkeypatch):
    calls = []
    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me",
                        lambda *a, **k: calls.append(a) or {})
    assert passive_learning.learn_from_message("ok") == []
    assert not calls
    assert passive_learning.learn_from_message("Plan Thailand") == []
    assert len(calls) == 1
    assert profile_suggestions.list_pending() == []


def test_retry_of_older_fact_cannot_overwrite_newer_learned_fact(monkeypatch):
    offline = [True]

    def extract(text, **kwargs):
        if "NEW MESSAGE:\nI live in Delhi" in text:
            if offline[0]:
                raise RuntimeError("offline")
            return {"profile": {"home_city": "Delhi"}}
        return {"profile": {"home_city": "Bangalore"}}

    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", extract)
    passive_learning.learn_from_message("I live in Delhi")
    passive_learning.learn_from_message("I now live in Bangalore")
    assert load_preferences()["profile"]["home_city"] == "Bangalore"
    offline[0] = False
    passive_learning.learn_from_message("ok")
    assert load_preferences()["profile"]["home_city"] == "Bangalore"
    assert not load_preferences()["_learning_pending"]


def test_retry_preserves_manual_edit_made_after_failed_extraction(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", fail)
    passive_learning.learn_from_message("I live in Delhi")
    user_preferences.update_preferences({"profile": {"home_city": "Mumbai"}})
    extractor(monkeypatch, {"profile": {"home_city": "Delhi"}})
    passive_learning.learn_from_message("ok")
    assert load_preferences()["profile"]["home_city"] == "Mumbai"


def test_profile_reset_cancels_inflight_learning(monkeypatch):
    def extract(*args, **kwargs):
        user_preferences.reset_preferences()
        return {"profile": {"home_city": "Bangalore"}}

    monkeypatch.setattr(passive_learning.about_me_extractor, "extract_about_me", extract)
    passive_learning.learn_from_message("Bangalore is home")
    assert load_preferences()["profile"]["home_city"] is None
    assert profile_suggestions.list_pending() == []


def test_new_name_enriches_the_only_known_child_instead_of_duplicating(monkeypatch):
    user_preferences.update_preferences({"family_members": [{"relationship": "child", "age": 10}]})
    extractor(monkeypatch, {"family_members": [{"relationship": "child", "name": "Aarav"}]})
    passive_learning.learn_from_message("My child's name is Aarav")
    assert load_preferences()["family_members"] == [
        {"relationship": "child", "age": 10, "name": "Aarav"}
    ]
