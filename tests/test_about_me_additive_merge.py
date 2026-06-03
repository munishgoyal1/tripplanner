"""Tests for the additive overlay that merges About-me extractions back
into saved preferences without ever removing or overwriting prior data.

These exercise the pure helpers in ``multiagent.tools.preferences_merge`` —
no frontend runtime, no LLM, no I/O.
"""

from __future__ import annotations

from multiagent.tools.preferences_merge import (
    additive_overlay_extracted as _additive_overlay_extracted,
    merge_family_member as _merge_family_member,
    union_keep_existing_case as _union_keep_existing_case,
)


# --- _union_keep_existing_case --------------------------------------------


def test_union_appends_new_items() -> None:
    assert _union_keep_existing_case(["beaches"], ["mountains"]) == [
        "beaches",
        "mountains",
    ]


def test_union_is_case_insensitive_existing_casing_wins() -> None:
    # Existing "Mountains" stays; "mountains" is treated as a duplicate.
    assert _union_keep_existing_case(["Mountains"], ["mountains"]) == ["Mountains"]


def test_union_dedupes_within_incoming() -> None:
    assert _union_keep_existing_case([], ["yoga", "Yoga", "YOGA"]) == ["yoga"]


def test_union_drops_empty_and_none() -> None:
    assert _union_keep_existing_case(["beaches"], [None, "", "  "]) == ["beaches"]


def test_union_handles_none_inputs() -> None:
    assert _union_keep_existing_case(None, ["x"]) == ["x"]  # type: ignore[arg-type]
    assert _union_keep_existing_case(["x"], None) == ["x"]  # type: ignore[arg-type]


# --- list-field unions ----------------------------------------------------


def test_interests_unioned_never_replaced() -> None:
    prefs = {"interests": ["beaches"]}
    out = _additive_overlay_extracted(prefs, {"interests": ["mountains"]})
    assert out["interests"] == ["beaches", "mountains"]


def test_extracted_dislikes_do_not_remove_from_interests() -> None:
    """The merge layer is structurally non-destructive: even if the LLM
    somehow returned beaches in dislikes, it must not remove beaches from
    interests (the user's example: "didn't like beaches" -> keep beaches)."""
    prefs = {"interests": ["beaches"], "dislikes": []}
    out = _additive_overlay_extracted(prefs, {"dislikes": ["beaches"]})
    assert "beaches" in out["interests"]
    assert out["dislikes"] == ["beaches"]


def test_food_cuisine_likes_unioned() -> None:
    prefs = {"food_preferences": {"cuisine_likes": ["italian"]}}
    out = _additive_overlay_extracted(
        prefs, {"food_preferences": {"cuisine_likes": ["thai", "italian"]}}
    )
    assert out["food_preferences"]["cuisine_likes"] == ["italian", "thai"]


def test_food_dietary_unioned() -> None:
    prefs = {"food_preferences": {"dietary": ["vegetarian"]}}
    out = _additive_overlay_extracted(
        prefs, {"food_preferences": {"dietary": ["vegetarian", "no-pork"]}}
    )
    assert out["food_preferences"]["dietary"] == ["vegetarian", "no-pork"]


# --- scalar fill-only rules ----------------------------------------------


def test_scalar_home_city_not_overwritten() -> None:
    prefs = {"profile": {"home_city": "Bengaluru"}}
    out = _additive_overlay_extracted(prefs, {"profile": {"home_city": "Mumbai"}})
    assert out["profile"]["home_city"] == "Bengaluru"


def test_scalar_home_city_fills_when_empty() -> None:
    prefs = {"profile": {"home_city": ""}}
    out = _additive_overlay_extracted(prefs, {"profile": {"home_city": "Bengaluru"}})
    assert out["profile"]["home_city"] == "Bengaluru"


def test_scalar_age_band_not_overwritten() -> None:
    prefs = {"profile": {"age_band": "40-50"}}
    out = _additive_overlay_extracted(prefs, {"profile": {"age_band": "30-40"}})
    assert out["profile"]["age_band"] == "40-50"


def test_trip_style_only_fills_when_empty() -> None:
    prefs = {"trip_style": "relaxed"}
    out = _additive_overlay_extracted(prefs, {"trip_style": "adventure"})
    assert out["trip_style"] == "relaxed"

    prefs2 = {"trip_style": ""}
    out2 = _additive_overlay_extracted(prefs2, {"trip_style": "adventure"})
    assert out2["trip_style"] == "adventure"


def test_budget_level_only_fills_when_empty() -> None:
    prefs = {"budget_level": "mid"}
    out = _additive_overlay_extracted(prefs, {"budget_level": "luxury"})
    assert out["budget_level"] == "mid"


def test_hotel_star_min_not_overwritten() -> None:
    prefs = {"hotel_preferences": {"star_rating_min": 4}}
    out = _additive_overlay_extracted(
        prefs, {"hotel_preferences": {"star_rating_min": 3}}
    )
    assert out["hotel_preferences"]["star_rating_min"] == 4


def test_transport_flight_class_not_overwritten() -> None:
    prefs = {"transport_preferences": {"flight_class": "business"}}
    out = _additive_overlay_extracted(
        prefs, {"transport_preferences": {"flight_class": "economy"}}
    )
    assert out["transport_preferences"]["flight_class"] == "business"


def test_transport_prefer_direct_fills_when_unset() -> None:
    prefs: dict = {"transport_preferences": {}}
    out = _additive_overlay_extracted(
        prefs, {"transport_preferences": {"prefer_direct_flights": True}}
    )
    assert out["transport_preferences"]["prefer_direct_flights"] is True


# --- family_members rules -------------------------------------------------


def test_family_appends_new_member() -> None:
    prefs = {
        "family_members": [
            {"relationship": "spouse", "name": "Megha", "age": 40},
        ]
    }
    out = _additive_overlay_extracted(
        prefs,
        {"family_members": [{"relationship": "child", "name": "Amay", "age": 11}]},
    )
    assert len(out["family_members"]) == 2
    names = {m.get("name") for m in out["family_members"]}
    assert names == {"Megha", "Amay"}


def test_family_match_fills_blank_scalar_only() -> None:
    """Matching (relationship, name.lower()) -> fill in blank fields but
    never overwrite a populated scalar."""
    prefs = {
        "family_members": [
            {"relationship": "spouse", "name": "Megha", "age": 40},
        ]
    }
    out = _additive_overlay_extracted(
        prefs,
        {
            "family_members": [
                # New "age" would overwrite -> must be ignored.
                # New "notes" fills in because old notes was missing.
                {
                    "relationship": "spouse",
                    "name": "Megha",
                    "age": 41,
                    "notes": "loves yoga",
                }
            ]
        },
    )
    assert len(out["family_members"]) == 1
    member = out["family_members"][0]
    assert member["age"] == 40  # preserved
    assert member["notes"] == "loves yoga"  # filled


def test_family_match_unions_list_subfields() -> None:
    prefs = {
        "family_members": [
            {
                "relationship": "spouse",
                "name": "Megha",
                "dietary": ["vegetarian"],
                "interests": ["yoga"],
            }
        ]
    }
    out = _additive_overlay_extracted(
        prefs,
        {
            "family_members": [
                {
                    "relationship": "spouse",
                    "name": "Megha",
                    "dietary": ["no-pork", "vegetarian"],
                    "interests": ["hiking"],
                }
            ]
        },
    )
    member = out["family_members"][0]
    assert member["dietary"] == ["vegetarian", "no-pork"]
    assert member["interests"] == ["yoga", "hiking"]


def test_family_match_is_case_insensitive_on_name() -> None:
    prefs = {
        "family_members": [
            {"relationship": "spouse", "name": "Megha", "age": 40},
        ]
    }
    out = _additive_overlay_extracted(
        prefs,
        {
            "family_members": [
                {"relationship": "spouse", "name": "megha", "notes": "loves yoga"}
            ]
        },
    )
    assert len(out["family_members"]) == 1
    assert out["family_members"][0]["notes"] == "loves yoga"


def test_family_unnamed_entries_appended_not_merged() -> None:
    """Two unnamed 'child' rows might be different kids; safer to append."""
    prefs = {"family_members": [{"relationship": "child"}]}
    out = _additive_overlay_extracted(
        prefs, {"family_members": [{"relationship": "child"}]}
    )
    assert len(out["family_members"]) == 2


def test_merge_family_member_helper_directly() -> None:
    existing = {
        "relationship": "spouse",
        "name": "Megha",
        "age": 40,
        "dietary": ["vegetarian"],
    }
    incoming = {
        "relationship": "spouse",
        "name": "Megha",
        "age": 99,
        "dietary": ["no-pork"],
        "notes": "yoga teacher",
    }
    merged = _merge_family_member(existing, incoming)
    assert merged["age"] == 40
    assert merged["notes"] == "yoga teacher"
    assert merged["dietary"] == ["vegetarian", "no-pork"]


# --- end-to-end fidelity --------------------------------------------------


def test_empty_extraction_is_noop() -> None:
    prefs = {"interests": ["beaches"], "profile": {"home_city": "Bengaluru"}}
    out = _additive_overlay_extracted(prefs, {})
    # Original keys preserved; no surprise additions.
    assert out["interests"] == ["beaches"]
    assert out["profile"]["home_city"] == "Bengaluru"


def test_extraction_does_not_mutate_input_prefs() -> None:
    prefs = {"interests": ["beaches"]}
    snapshot = list(prefs["interests"])
    _additive_overlay_extracted(prefs, {"interests": ["mountains"]})
    assert prefs["interests"] == snapshot
