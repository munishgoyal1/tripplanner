"""Tests for the shared apply_about_me flow (preferences_merge).

These lock in the contract used by the frontend (the About-me settings form and
the SPA `POST /preferences`): store the raw blurb, extract only when it
changed, overlay additively, and never remove prior data. The LLM extractor is
stubbed so these run offline and deterministically.
"""

from __future__ import annotations

from multiagent.tools import preferences_merge


def test_apply_about_me_stores_raw_and_extracts(monkeypatch) -> None:
    monkeypatch.setattr(
        preferences_merge.about_me_extractor,
        "extract_about_me",
        lambda text: {"profile": {"home_city": "Pune"}, "interests": ["hiking"]},
    )
    prefs, keys = preferences_merge.apply_about_me({}, "I live in Pune and love hiking")
    assert prefs["about_me"] == "I live in Pune and love hiking"
    assert prefs["profile"]["home_city"] == "Pune"
    assert prefs["interests"] == ["hiking"]
    assert "profile.home_city" in keys
    assert "interests" in keys


def test_apply_about_me_skips_extraction_when_unchanged(monkeypatch) -> None:
    called = {"n": 0}

    def _extract(text: str) -> dict:
        called["n"] += 1
        return {}

    monkeypatch.setattr(preferences_merge.about_me_extractor, "extract_about_me", _extract)
    prefs = {"about_me": "same blurb", "interests": ["beaches"]}
    out, keys = preferences_merge.apply_about_me(prefs, "same blurb")
    assert called["n"] == 0
    assert keys == []
    assert out["interests"] == ["beaches"]


def test_apply_about_me_is_additive_not_destructive(monkeypatch) -> None:
    monkeypatch.setattr(
        preferences_merge.about_me_extractor,
        "extract_about_me",
        lambda text: {"interests": ["coffee"]},
    )
    prefs = {"interests": ["beaches"], "about_me": "old"}
    out, _ = preferences_merge.apply_about_me(prefs, "new blurb")
    assert out["interests"] == ["beaches", "coffee"]


def test_apply_about_me_appends_learned_notes(monkeypatch) -> None:
    monkeypatch.setattr(
        preferences_merge.about_me_extractor,
        "extract_about_me",
        lambda text: {"_learned_notes_to_append": [{"note": "dislikes red-eyes"}]},
    )
    prefs, keys = preferences_merge.apply_about_me({}, "no red-eye flights please")
    assert prefs["learned_notes"][0]["note"] == "dislikes red-eyes"
    assert "learned_notes" in keys


def test_apply_about_me_truncates_overlong_blurb(monkeypatch) -> None:
    monkeypatch.setattr(
        preferences_merge.about_me_extractor, "extract_about_me", lambda text: {}
    )
    long_text = "x" * (preferences_merge.ABOUT_ME_MAX_CHARS + 500)
    prefs, _ = preferences_merge.apply_about_me({}, long_text)
    assert len(prefs["about_me"]) == preferences_merge.ABOUT_ME_MAX_CHARS
