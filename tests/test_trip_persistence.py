"""Ownership-focused tests split from the former tests/test_trip.py module."""

# ruff: noqa: E501, F403, F405, I001

from tests.support.trip import *  # noqa: F403

class TestDeepMerge:
    def test_flat(self):
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_override(self):
        assert _deep_merge({"a": 1}, {"a": 99}) == {"a": 99}

    def test_nested(self):
        base = {"x": {"y": 1, "z": 2}}
        result = _deep_merge(base, {"x": {"z": 99}})
        assert result == {"x": {"y": 1, "z": 99}}

class TestLoadSave:
    def test_defaults_when_no_file(self):
        prefs = load_preferences()
        assert prefs["family"]["adults"] == 1
        assert prefs["trip_style"] == "balanced"
        assert prefs["budget_level"] == "moderate"

    def test_roundtrip(self):
        prefs = load_preferences()
        prefs["family"]["adults"] = 3
        save_preferences(prefs)
        reloaded = load_preferences()
        assert reloaded["family"]["adults"] == 3

    def test_update_merges(self):
        update_preferences({"trip_style": "leisure", "family": {"children": 2, "child_ages": [4, 8]}})
        prefs = load_preferences()
        assert prefs["trip_style"] == "leisure"
        assert prefs["family"]["children"] == 2
        assert prefs["family"]["adults"] == 1  # untouched

    def test_local_mutations_serialize_without_losing_unrelated_updates(self, monkeypatch):
        monkeypatch.setattr(user_preferences.storage_cosmos, "is_enabled", lambda: False)
        first_entered = threading.Event()
        release_first = threading.Event()
        second_done = threading.Event()

        def first(prefs):
            first_entered.set()
            assert release_first.wait(timeout=2)
            prefs["interests"] = ["hiking"]
            return prefs

        def second(prefs):
            prefs["dislikes"] = ["red-eye flights"]
            return prefs

        def run_second():
            result = user_preferences.mutate_preferences(second)
            second_done.set()
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(user_preferences.mutate_preferences, first)
            assert first_entered.wait(timeout=2)
            second_future = pool.submit(run_second)
            assert not second_done.wait(timeout=0.1)
            release_first.set()
            first_future.result(timeout=2)
            second_future.result(timeout=2)

        prefs = load_preferences()
        assert prefs["interests"] == ["hiking"]
        assert prefs["dislikes"] == ["red-eye flights"]

    def test_guest_adoption_fills_defaults_without_replacing_account_fields(self):
        current = load_preferences()
        current["profile"]["display_name"] = "Authenticated name"
        current["planning_mode"] = "interactive"
        current["interests"] = ["museums"]
        current["trip_style"] = "balanced"
        user_preferences.mark_explicit_fields(current, {"trip_style"})
        incoming = load_preferences()
        incoming["profile"]["display_name"] = "Guest name"
        incoming["profile"]["home_city"] = "Bengaluru"
        incoming["trip_style"] = "relaxed"
        incoming["interests"] = ["food", "museums"]

        merged = user_preferences.adopt_missing_preferences(current, incoming)

        assert merged["profile"]["display_name"] == "Authenticated name"
        assert merged["profile"]["home_city"] == "Bengaluru"
        assert merged["planning_mode"] == "interactive"
        assert merged["trip_style"] == "balanced"
        assert merged["interests"] == ["museums", "food"]

    def test_guest_adoption_transfers_only_adopted_explicit_defaults(self):
        current = load_preferences()
        current["budget_level"] = "premium"
        incoming = load_preferences()
        user_preferences.mark_explicit_fields(
            incoming,
            {"trip_style", "budget_level"},
        )

        merged = user_preferences.adopt_missing_preferences(current, incoming)

        assert merged["trip_style"] == "balanced"
        assert merged["budget_level"] == "premium"
        assert "trip_style" in merged["_explicit_fields"]
        assert "budget_level" not in merged["_explicit_fields"]

    def test_authenticated_explicit_default_blocks_guest_non_default(self):
        current = load_preferences()
        user_preferences.mark_explicit_fields(current, {"trip_style"})
        incoming = load_preferences()
        incoming["trip_style"] = "relaxed"
        user_preferences.mark_explicit_fields(incoming, {"trip_style"})

        merged = user_preferences.adopt_missing_preferences(current, incoming)

        assert merged["trip_style"] == "balanced"
        assert merged["_explicit_fields"] == ["trip_style"]

    def test_guest_adoption_merges_matching_family_member(self):
        current = load_preferences()
        current["family_members"] = [
            {
                "relationship": "spouse",
                "name": "Megha",
                "dietary": ["vegetarian"],
            }
        ]
        incoming = load_preferences()
        incoming["family_members"] = [
            {
                "relationship": "spouse",
                "name": "megha",
                "age": 40,
                "interests": ["hiking"],
            }
        ]

        merged = user_preferences.adopt_missing_preferences(current, incoming)

        assert len(merged["family_members"]) == 1
        assert merged["family_members"][0] == {
            "relationship": "spouse",
            "name": "Megha",
            "age": 40,
            "dietary": ["vegetarian"],
            "interests": ["hiking"],
        }

    def test_update_unions_additive_lists(self):
        update_preferences({"food_preferences": {"dietary": ["vegetarian"]}})
        update_preferences({"food_preferences": {"dietary": ["jain"]}})
        prefs = load_preferences()
        assert sorted(prefs["food_preferences"]["dietary"]) == ["jain", "vegetarian"]

    def test_update_dedupes_additive_lists_case_insensitive(self):
        update_preferences({"interests": ["Hiking"]})
        update_preferences({"interests": ["hiking", "food"]})
        prefs = load_preferences()
        assert prefs["interests"] == ["Hiking", "food"]

    def test_update_replaces_non_additive_lists(self):
        update_preferences({"family": {"child_ages": [4, 8]}})
        update_preferences({"family": {"child_ages": [10]}})
        prefs = load_preferences()
        assert prefs["family"]["child_ages"] == [10]  # replace, not union

    def test_add_past_trip(self):
        add_past_trip("Goa", "2025-12-20 to 2025-12-27", 5, "Amazing beaches")
        add_past_trip("Shimla", "2025-01-10 to 2025-01-15", 3, "Too crowded")
        prefs = load_preferences()
        assert len(prefs["past_trips"]) == 2
        assert prefs["past_trips"][0]["destination"] == "Goa"
        assert prefs["past_trips"][1]["rating"] == 3

    def test_learned_notes_deduped_on_save(self):
        prefs = load_preferences()
        prefs["learned_notes"] = [
            {"note": "Prefers aisle seats", "source": "stated", "at": "2026-01-01"},
            {"note": "prefers aisle seats", "source": "inferred", "at": "2026-02-01"},
        ]
        save_preferences(prefs)
        reloaded = load_preferences()
        assert len(reloaded["learned_notes"]) == 1
        assert reloaded["learned_notes"][0]["at"] == "2026-01-01"  # oldest kept

    def test_learned_notes_capped(self):
        from tripplanner.tools.user_preferences import _MAX_LEARNED_NOTES

        prefs = load_preferences()
        prefs["learned_notes"] = [
            {"note": f"note {i}", "source": "stated", "at": "2026-01-01"}
            for i in range(_MAX_LEARNED_NOTES + 25)
        ]
        save_preferences(prefs)
        reloaded = load_preferences()
        assert len(reloaded["learned_notes"]) == _MAX_LEARNED_NOTES
        # most recent kept
        assert reloaded["learned_notes"][-1]["note"] == f"note {_MAX_LEARNED_NOTES + 24}"

class TestPreferenceTools:
    def test_get_travel_preferences(self):
        result = get_travel_preferences.invoke({})
        parsed = json.loads(result)
        assert "family" in parsed
        assert "trip_style" in parsed
        assert "configured_preference_fields" in parsed

    def test_save_travel_preferences(self):
        payload = json.dumps({
            "family": {"adults": 2, "children": 1, "child_ages": [5]},
            "trip_style": "leisure",
            "budget_level": "premium",
        })
        result = save_travel_preferences.invoke({"updates_json": payload})
        assert "Preferences updated" in result
        prefs = load_preferences()
        assert prefs["family"]["adults"] == 2
        assert prefs["trip_style"] == "leisure"

    def test_save_invalid_json(self):
        result = save_travel_preferences.invoke({"updates_json": "not json"})
        assert "Error" in result

    def test_record_past_trip(self):
        result = record_past_trip.invoke({
            "destination": "Paris",
            "dates": "2025-06-01 to 2025-06-07",
            "rating": 5,
            "notes": "Loved the food",
        })
        assert "Paris" in result
        prefs = load_preferences()
        assert len(prefs["past_trips"]) == 1

    def test_record_trip_postmortem_updates_existing(self):
        add_past_trip("Goa", "2026-01-10 to 2026-01-15", None, "")
        result = record_trip_postmortem.invoke({
            "destination": "Goa",
            "rating": 4,
            "what_worked": "beach hotel; private guide",
            "what_didnt": "morning flight; airport hotel",
            "pace_feedback": "just_right",
            "actual_active_minutes_per_full_day": 390,
        })
        assert "Post-mortem" in result and "Goa" in result
        prefs = load_preferences()
        trip = next(t for t in prefs["past_trips"] if t["destination"] == "Goa")
        assert trip["rating"] == 4
        assert trip["what_worked"] == ["beach hotel", "private guide"]
        assert trip["what_didnt"] == ["morning flight", "airport hotel"]
        assert trip["pace_feedback"] == "just_right"
        assert trip["actual_active_minutes_per_full_day"] == 390
        notes = " | ".join(n["note"] for n in prefs.get("learned_notes", []))
        assert "Liked on Goa trip: beach hotel" in notes
        assert "Disliked on Goa trip: morning flight" in notes

    def test_record_trip_postmortem_appends_when_no_match(self):
        result = record_trip_postmortem.invoke({
            "destination": "Tokyo",
            "rating": 5,
            "what_worked": "ryokan stay",
            "dates": "2025-04-01 to 2025-04-08",
        })
        assert "Tokyo" in result
        prefs = load_preferences()
        trip = next(t for t in prefs["past_trips"] if t["destination"] == "Tokyo")
        assert trip["rating"] == 5
        assert trip["dates"] == "2025-04-01 to 2025-04-08"
        assert trip["what_worked"] == ["ryokan stay"]

    def test_create_trip_persists_planning_recommendation(self):
        recommendation = {
            "recommended_days": 3,
            "target_active_minutes_per_full_day": 360,
            "reasons": ["Six matching places fit a balanced city break"],
        }

        create_trip_plan.invoke({
            "destination": "Mysore",
            "departure_date": "2026-09-01",
            "return_date": "2026-09-03",
            "planning_recommendation_json": json.dumps(recommendation),
        })

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["planning_recommendation"] == recommendation
        assert "planning_preferences" in plan["preferences_snapshot"]

class TestSystemPromptDateInjection:
    """The agent must always know today's date and never suggest past dates."""

    def test_includes_today_iso(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "2026-06-02" in msg.content
        assert "TODAY is 2026-06-02" in msg.content

    def test_includes_human_readable_date(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        # Tuesday, 02 June 2026
        assert "June 2026" in msg.content

    def test_includes_min_trip_start(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        # min trip = today + 7 days
        assert "2026-06-09" in msg.content

    def test_includes_default_window(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        # default start = today + 4 weeks; no fixed trip length is assumed
        assert "2026-06-30" in msg.content

    def test_includes_current_and_next_year(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "2026" in msg.content
        assert "2027" in msg.content

    def test_never_in_past_rule_present(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "NEVER suggest" in msg.content
        assert "past" in msg.content.lower()

    def test_default_today_is_now(self):
        """When no date is passed, the prompt should use today's UTC date."""
        msg = build_trip_system_prompt()
        today = datetime.now(timezone.utc).date().isoformat()
        assert today in msg.content

    def test_module_level_constant_exists_for_back_compat(self):
        """Importers that grab the static TRIP_SYSTEM_PROMPT still work."""
        assert TRIP_SYSTEM_PROMPT is not None
        assert "Trip Planner Agent" in TRIP_SYSTEM_PROMPT.content

    def test_interactive_questions_use_structured_prefilled_input(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "request_trip_input" in msg.content
        assert "pre-filled controls" in msg.content
        assert "adults: number of travellers age 13+" in msg.content
        assert "children: number of travellers age 0-12" in msg.content
        assert "party_type: solo, couple, family, friends, or group" in msg.content
        assert "known_context_json" in msg.content
        assert "never ask again" in msg.content

class TestRoadCircuitPromptRules:
    def test_prompt_requires_grounded_ordered_road_breaks(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "INTER-CITY ROAD CIRCUITS" in msg.content
        assert "worthwhile\n    on-route scenic stops" in msg.content
        assert "real scheduled or feasible bus breaks/stopovers" in msg.content
        assert "outside the road circuit" in msg.content

class TestPassiveLearning:
    """Free-form observations get persisted, deduped, and tagged with source."""

    def test_add_learned_note_appends(self):
        prefs = add_learned_note("prefers window seats", source="stated")
        assert any(n["note"] == "prefers window seats" for n in prefs["learned_notes"])
        assert prefs["learned_notes"][-1]["source"] == "stated"
        assert "at" in prefs["learned_notes"][-1]

    def test_add_learned_note_dedupes_case_insensitive(self):
        add_learned_note("Prefers window seats", source="stated")
        prefs = add_learned_note("prefers WINDOW seats", source="inferred")
        notes = [n for n in prefs["learned_notes"] if "window seats" in n["note"].lower()]
        assert len(notes) == 1

    def test_add_learned_note_rejects_empty(self):
        prefs = add_learned_note("   ", source="stated")
        assert prefs["learned_notes"] == []

    def test_add_learned_note_invalid_source_defaults_to_stated(self):
        prefs = add_learned_note("dislikes red-eyes", source="garbage")
        last = prefs["learned_notes"][-1]
        assert last["source"] == "stated"

    def test_remember_about_user_tool(self):
        result = remember_about_user.invoke({
            "note": "anxious flyer — avoid red-eyes",
            "source": "stated",
        })
        assert "Remembered" in result
        prefs = load_preferences()
        assert any("anxious flyer" in n["note"] for n in prefs["learned_notes"])

    def test_remember_about_user_inferred(self):
        result = remember_about_user.invoke({
            "note": "prefers boutique hotels over chains",
            "source": "inferred",
        })
        assert "inferred" in result
        prefs = load_preferences()
        match = [n for n in prefs["learned_notes"] if "boutique" in n["note"]]
        assert match and match[0]["source"] == "inferred"

    def test_default_prefs_include_learned_notes(self):
        prefs = load_preferences()
        assert "learned_notes" in prefs
        assert prefs["learned_notes"] == []

class TestPassiveLearningPromptRules:
    """The system prompt must explicitly instruct the model to learn passively."""

    def test_prompt_mentions_remember_about_user(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "remember_about_user" in msg.content

    def test_prompt_has_passive_learning_section(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "PASSIVE LEARNING" in msg.content

    def test_prompt_distinguishes_stated_vs_inferred(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "stated" in msg.content
        assert "inferred" in msg.content

    def test_prompt_loads_learned_notes_in_step_1(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "learned_notes" in msg.content

    def test_prompt_auto_records_after_execute(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        # Step 7 must require record_past_trip after execute_bookings
        assert "record_past_trip" in msg.content
        assert "non-negotiable" in msg.content.lower() or "immediately after" in msg.content.lower()

    def test_prompt_has_conflict_resolution_rule(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "CONFLICT" in msg.content or "conflict" in msg.content.lower()

class TestProfileStore:
    """update_profile patches without nuking existing fields."""

    def test_partial_update_preserves_others(self):
        update_profile({"display_name": "Munish", "home_city": "Bengaluru"})
        prefs = update_profile({"occupation": "engineer"})
        prof = prefs["profile"]
        assert prof["display_name"] == "Munish"
        assert prof["home_city"] == "Bengaluru"
        assert prof["occupation"] == "engineer"

    def test_none_values_are_ignored(self):
        update_profile({"display_name": "Munish"})
        prefs = update_profile({"display_name": None, "home_country": "India"})
        assert prefs["profile"]["display_name"] == "Munish"
        assert prefs["profile"]["home_country"] == "India"

    def test_empty_string_ignored(self):
        update_profile({"display_name": "Munish"})
        prefs = update_profile({"display_name": "   "})
        assert prefs["profile"]["display_name"] == "Munish"

class TestFamilyMemberUpsert:
    """upsert_family_member: insert + merge + list-field dedup."""

    def test_insert_new_member(self):
        prefs = upsert_family_member("spouse", name="Priya", interests=["beaches"])
        spouses = [m for m in prefs["family_members"] if m["relationship"] == "spouse"]
        assert len(spouses) == 1
        assert spouses[0]["name"] == "Priya"
        assert spouses[0]["interests"] == ["beaches"]

    def test_upsert_merges_interests(self):
        upsert_family_member("spouse", name="Priya", interests=["beaches"])
        prefs = upsert_family_member("spouse", name="priya", interests=["photography"])
        spouses = [m for m in prefs["family_members"] if m["relationship"] == "spouse"]
        assert len(spouses) == 1
        assert set(spouses[0]["interests"]) == {"beaches", "photography"}

    def test_upsert_updates_age(self):
        upsert_family_member("child", name="Aarav", age=7)
        prefs = upsert_family_member("child", name="Aarav", age=8)
        kids = [m for m in prefs["family_members"] if m["relationship"] == "child"]
        assert kids[0]["age"] == 8

    def test_unknown_relationship_maps_to_other(self):
        prefs = upsert_family_member("cousin-twice-removed", name="X")
        assert any(m["relationship"] == "other" for m in prefs["family_members"])

    def test_anonymous_member_no_name(self):
        prefs = upsert_family_member("child", age=5)
        kids = [m for m in prefs["family_members"] if m["relationship"] == "child"]
        assert any(m["age"] == 5 and not m.get("name") for m in kids)

class TestInterestsDislikes:
    def test_add_interest_dedupes(self):
        add_interest("hiking")
        prefs = add_interest("Hiking")
        assert prefs["interests"].count("hiking") == 1

    def test_add_dislike_dedupes(self):
        add_dislike("crowds")
        prefs = add_dislike("CROWDS")
        assert prefs["dislikes"].count("crowds") == 1

    def test_empty_rejected(self):
        prefs = add_interest("   ")
        assert "   " not in prefs["interests"]

class TestTripMentions:
    def test_record_basic(self):
        prefs = add_trip_mention("Bali", when="summer 2024", sentiment="positive", notes="loved it")
        bali = [m for m in prefs["past_trip_mentions"] if m["destination"] == "Bali"]
        assert len(bali) == 1
        assert bali[0]["sentiment"] == "positive"

    def test_dedup_same_dest_and_when(self):
        add_trip_mention("Goa", when="2023", sentiment="negative", notes="crowded")
        prefs = add_trip_mention("Goa", when="2023", sentiment="negative", notes="really crowded")
        goa = [m for m in prefs["past_trip_mentions"] if m["destination"] == "Goa"]
        assert len(goa) == 1
        assert "really crowded" in goa[0]["notes"]

    def test_invalid_sentiment_falls_back(self):
        prefs = add_trip_mention("Paris", sentiment="amazing-vibes")
        paris = [m for m in prefs["past_trip_mentions"] if m["destination"] == "Paris"]
        assert paris[0]["sentiment"] == "neutral"

    def test_empty_destination_skipped(self):
        before = load_preferences().get("past_trip_mentions", [])
        prefs = add_trip_mention("   ")
        assert len(prefs["past_trip_mentions"]) == len(before)

class TestExtractionTools:
    """The @tool wrappers route to the helpers correctly."""

    def test_update_user_profile_tool(self):
        result = tool_update_user_profile.invoke({
            "display_name": "Munish",
            "home_city": "Bengaluru",
            "home_country": "India",
        })
        assert "Profile updated" in result
        prefs = load_preferences()
        assert prefs["profile"]["display_name"] == "Munish"
        assert prefs["profile"]["home_city"] == "Bengaluru"

    def test_add_family_member_tool(self):
        result = tool_add_family_member.invoke({
            "relationship": "child",
            "name": "Aarav",
            "age": 8,
            "dietary": ["nut-free"],
        })
        assert "Saved family member" in result
        prefs = load_preferences()
        kids = [m for m in prefs["family_members"] if m.get("name") == "Aarav"]
        assert kids and "nut-free" in kids[0]["dietary"]

    def test_add_user_interest_tool(self):
        tool_add_user_interest.invoke({"item": "photography"})
        prefs = load_preferences()
        assert "photography" in prefs["interests"]

    def test_add_user_dislike_tool(self):
        tool_add_user_dislike.invoke({"item": "long bus rides"})
        prefs = load_preferences()
        assert "long bus rides" in prefs["dislikes"]

    def test_record_trip_mention_tool(self):
        result = tool_record_trip_mention.invoke({
            "destination": "Tokyo",
            "when": "2023",
            "sentiment": "positive",
            "notes": "loved the food",
        })
        assert "Tokyo" in result
        prefs = load_preferences()
        tokyo = [m for m in prefs["past_trip_mentions"] if m["destination"] == "Tokyo"]
        assert tokyo and tokyo[0]["sentiment"] == "positive"

class TestExtractionPromptRules:
    """System prompt must guide the model toward continuous extraction."""

    def test_prompt_has_extraction_checklist(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "EXTRACTION CHECKLIST" in msg.content

    def test_prompt_mentions_all_new_tools(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        for name in [
            "update_user_profile",
            "add_family_member",
            "add_user_interest",
            "add_user_dislike",
            "record_trip_mention",
        ]:
            assert name in msg.content, f"prompt missing reference to {name}"

    def test_prompt_demands_parallel_calls(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        assert "PARALLEL" in msg.content or "parallel" in msg.content

    def test_prompt_step1_lists_new_sections(self):
        msg = build_trip_system_prompt(today=date(2026, 6, 2))
        # STEP 1 should now describe the new schema
        for token in ["profile", "family_members", "interests", "past_trip_mentions"]:
            assert token in msg.content, f"prompt STEP 1 doesn't mention {token}"

    def test_default_prefs_have_new_sections(self):
        prefs = load_preferences()
        assert "profile" in prefs
        assert "family_members" in prefs
        assert "interests" in prefs
        assert "dislikes" in prefs
        assert "past_trip_mentions" in prefs
