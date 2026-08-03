"""Tests for the About-me extractor sanitizer.

The live LLM call is not exercised here (it requires network + Azure creds).
We test the pure-Python ``_sanitize_extraction`` function which guarantees the
extractor never returns junk that could corrupt user prefs.
"""

from __future__ import annotations

from tripplanner.tools.about_me_extractor import _sanitize_extraction


def test_sanitize_basic_profile_fields() -> None:
    raw = {
        "profile": {
            "display_name": "  Munish ",
            "home_city": "Bengaluru",
            "home_country": "India",
            "age_band": "40-50",
            "occupation": "software engineer",
        }
    }
    out = _sanitize_extraction(raw)
    assert out["profile"]["display_name"] == "Munish"
    assert out["profile"]["home_city"] == "Bengaluru"
    assert out["profile"]["age_band"] == "40-50"


def test_sanitize_drops_missing_keys() -> None:
    """If the model omits a key, the result must omit it too (so deep-merge
    doesn't blank out the saved value)."""
    out = _sanitize_extraction({"profile": {"home_city": "Paris"}})
    assert out == {"profile": {"home_city": "Paris"}}
    assert "interests" not in out
    assert "trip_style" not in out


def test_sanitize_invalid_trip_style_dropped() -> None:
    out = _sanitize_extraction({"trip_style": "yolo"})
    assert "trip_style" not in out


def test_sanitize_valid_trip_style_kept() -> None:
    out = _sanitize_extraction({"trip_style": "Foodie"})
    assert out["trip_style"] == "foodie"


def test_sanitize_enum_normalises_separators() -> None:
    out = _sanitize_extraction(
        {"transport_preferences": {"flight_class": "premium economy"}}
    )
    assert out["transport_preferences"]["flight_class"] == "premium_economy"


def test_sanitize_clamps_star_rating() -> None:
    out = _sanitize_extraction({"hotel_preferences": {"star_rating_min": 12}})
    assert out["hotel_preferences"]["star_rating_min"] == 5
    out = _sanitize_extraction({"hotel_preferences": {"star_rating_min": -3}})
    assert out["hotel_preferences"]["star_rating_min"] == 1


def test_sanitize_family_members() -> None:
    raw = {
        "family_members": [
            {"relationship": "self", "name": "Munish", "age": 43},
            {"relationship": "spouse", "name": "Megha", "age": 40},
            {"relationship": "child", "name": "Amay", "age": 11},
            # invalid relationship is normalised to "other"
            {"relationship": "robot", "name": "R2D2"},
            # non-dict entries are skipped
            "not-a-dict",
        ]
    }
    out = _sanitize_extraction(raw)
    fams = out["family_members"]
    assert len(fams) == 4
    assert fams[0] == {"relationship": "self", "name": "Munish", "age": 43}
    assert fams[1]["relationship"] == "spouse"
    assert fams[3]["relationship"] == "other"


def test_sanitize_interests_dedupe_and_strip() -> None:
    out = _sanitize_extraction(
        {"interests": [" hiking ", "Hiking", "museums", "", None]}
    )
    assert out["interests"] == ["hiking", "museums"]


def test_sanitize_food_preferences_partial() -> None:
    out = _sanitize_extraction(
        {"food_preferences": {"dietary": ["vegetarian"]}}
    )
    assert out["food_preferences"] == {"dietary": ["vegetarian"]}
    assert "cuisine_likes" not in out["food_preferences"]


def test_sanitize_learned_notes_as_strings() -> None:
    out = _sanitize_extraction(
        {"learned_notes": ["no early flights", "prefers window seat"]}
    )
    notes = out["_learned_notes_to_append"]
    assert len(notes) == 2
    assert notes[0]["note"] == "no early flights"
    assert notes[0]["source"] == "stated"


def test_sanitize_learned_notes_as_objects() -> None:
    out = _sanitize_extraction(
        {"learned_notes": [{"note": "hates crowds"}, {"note": "  "}]}
    )
    notes = out["_learned_notes_to_append"]
    assert len(notes) == 1
    assert notes[0]["note"] == "hates crowds"


def test_sanitize_empty_input() -> None:
    assert _sanitize_extraction({}) == {}
    assert _sanitize_extraction(None) == {}  # type: ignore[arg-type]


def test_sanitize_boolean_prefer_direct_flights() -> None:
    out = _sanitize_extraction(
        {"transport_preferences": {"prefer_direct_flights": False}}
    )
    assert out["transport_preferences"]["prefer_direct_flights"] is False


def test_sanitize_home_area_and_road_break_preferences() -> None:
    out = _sanitize_extraction({
        "profile": {"home_area": " Whitefield "},
        "transport_preferences": {
            "preferred_road_transport": "own car",
            "max_continuous_drive_min": 150,
            "road_break_duration_min": 20,
            "road_break_preferences": [" snack ", "restroom"],
        },
    })

    assert out["profile"]["home_area"] == "Whitefield"
    assert out["transport_preferences"] == {
        "preferred_road_transport": "own_car",
        "max_continuous_drive_min": 150,
        "road_break_duration_min": 20,
        "road_break_preferences": ["snack", "restroom"],
    }


def test_extract_about_me_empty_short_circuits(monkeypatch) -> None:
    """Empty input must not call the LLM."""
    from tripplanner.tools import about_me_extractor as mod

    called = {"n": 0}

    def _fake_get_settings() -> None:
        called["n"] += 1
        raise AssertionError("should not be called for empty input")

    monkeypatch.setattr(mod, "_sanitize_extraction", lambda _: {"x": 1})
    assert mod.extract_about_me("") == {}
    assert mod.extract_about_me("   ") == {}
    assert called["n"] == 0
