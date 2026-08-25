"""Tests for user preferences, trip planner state, and trip agent tools."""

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tripplanner.tools import user_preferences
from tripplanner.tools.user_preferences import (
    _deep_merge,
    add_past_trip,
    load_preferences,
    save_preferences,
    update_preferences,
)

# Parallel sandboxes run this suite at the same time against one home
# directory, so a shared name means one run's teardown deletes another
# run's fixture mid-test. The pid keeps them disjoint.
_TEST_DIR = Path.home() / f".tripplanner_test-{os.getpid()}"
_TEST_FILE = _TEST_DIR / "user_preferences.json"
_TEST_ACTIVE_TRIP = _TEST_DIR / "active_trip.json"
_TEST_TRIP_HISTORY = _TEST_DIR / "trips"


@pytest.fixture(autouse=True)
def _isolate_prefs(monkeypatch):
    """Redirect all persistent storage to a temp dir for each test."""
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)

    # Also redirect trip_planner storage
    from tripplanner.tools import trip_planner
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", _TEST_ACTIVE_TRIP)
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", _TEST_TRIP_HISTORY)

    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# user_preferences module tests
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Trip agent preference tools
# ---------------------------------------------------------------------------
from tripplanner.agents.trip_agent import (
    get_travel_preferences,
    record_past_trip,
    record_trip_postmortem,
    save_travel_preferences,
)


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


# ---------------------------------------------------------------------------
# Trip planner state management tools
# ---------------------------------------------------------------------------
from tripplanner.tools.trip_planner import (
    _merge_itinerary_days,
    add_hotel_stay,
    add_selection,
    create_trip_plan,
    execute_bookings,
    finalize_trip,
    get_trip_plan,
    list_past_trips,
    planning_completion_gaps,
    remove_selection,
    set_stop_booked,
    update_trip_plan,
)


class TestPartialItineraryMerge:
    """A single-stop edit must not delete the days the model did not resend."""

    def _days(self, *numbers: int) -> list[dict]:
        return [{"day": n, "stops": [{"name": f"Stop {n}", "kind": "attraction"}]} for n in numbers]

    def test_subset_of_planned_days_is_merged_in_place(self):
        existing = self._days(1, 2, 3)
        incoming = [{"day": 2, "stops": [{"name": "Budget Inn Indore", "kind": "hotel"}]}]

        merged, partial = _merge_itinerary_days(existing, incoming)

        assert partial is True
        assert [day["day"] for day in merged] == [1, 2, 3]
        assert merged[1] == incoming[0]
        assert merged[0] == existing[0]

    def test_full_resubmit_replaces_the_itinerary(self):
        existing = self._days(1, 2, 3)
        incoming = self._days(1, 2)
        incoming.append({"day": 3, "stops": []})

        merged, partial = _merge_itinerary_days(existing, incoming)

        assert partial is False
        assert merged == incoming

    def test_shorter_itinerary_with_a_new_day_replaces(self):
        merged, partial = _merge_itinerary_days(self._days(1, 2, 3), self._days(4))

        assert partial is False
        assert [day["day"] for day in merged] == [4]

    def test_unnumbered_days_replace(self):
        incoming = [{"stops": []}]

        merged, partial = _merge_itinerary_days(self._days(1, 2), incoming)

        assert partial is False
        assert merged == incoming

    def test_hotel_swap_keeps_the_other_planned_days(self):
        create_trip_plan.invoke({
            "destination": "Indore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-12",
            "origin": "Bangalore",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": self._days(1, 2, 3),
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 2,
                    "stops": [{"name": "Lemon Tree Hotel Indore", "kind": "hotel"}],
                },
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert [day["day"] for day in plan["day_wise_itinerary"]] == [1, 2, 3]
        assert plan["day_wise_itinerary"][1]["stops"][0]["name"] == "Lemon Tree Hotel Indore"
        assert "Partial itinerary update merged" in result


class TestTripPlanState:
    @staticmethod
    def _save_booking_ready_trip(**updates):
        plan = {
            "status": "draft",
            "destination": "Goa",
            "origin": "",
            "travel_scope": "destination_only",
            "departure_date": "2026-07-06",
            "return_date": "2026-07-06",
            "travelers": "1 adult",
            "selected_flights": [],
            "selected_hotels": [{"name": "Taj Goa", "city": "Goa", "price": 15000}],
            "selected_activities": [],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {
                            "name": "Riverside Walk",
                            "kind": "attraction",
                            "time": "11:00",
                            "duration_min": 60,
                        },
                    ],
                }
            ],
            "cost_breakdown": {},
            "total_cost": 15000,
            "currency": "INR",
        }
        plan.update(updates)
        trip_planner._save_active_trip(plan)

    def test_save_normalizes_duplicate_return_stay_and_departure_checkout(self):
        plan = {
            "destination": "Ayodhya",
            "departure_date": "2026-09-10",
            "return_date": "2026-09-16",
            "day_wise_itinerary": [
                {
                    "day": 6,
                    "stops": [
                        {"name": "Drive: Chitrakoot to Ayodhya", "kind": "transport"},
                        {"name": "Ayodhya Hotel", "kind": "hotel", "time": "22:30"},
                        {"name": "Ayodhya Hotel", "kind": "hotel", "time": "23:59"},
                    ],
                },
                {
                    "day": 7,
                    "title": "Departure from Ayodhya",
                    "summary": "Check out from hotel and depart from Ayodhya.",
                    "stops": [{"name": "Ayodhya Hotel", "kind": "hotel", "note": "Check-out"}],
                },
            ],
        }

        trip_planner._save_active_trip(plan)

        saved = trip_planner.load_active_trip_dict()
        assert saved is not None
        assert saved["day_wise_itinerary"][0]["stops"] == [
            {"name": "Drive: Chitrakoot to Ayodhya", "kind": "transport"},
            {
                "name": "Ayodhya Hotel",
                "kind": "hotel",
                "time": "22:30",
                "note": "Return to hotel",
            },
        ]
        departure = saved["day_wise_itinerary"][1]["stops"][0]
        assert departure["time"] == "11:00"
        assert "confirm with your hotel" in departure["note"]

    def test_planning_completion_requires_round_trip_intercity_transport(self):
        base = {
            "origin": "Bangalore",
            "destination": "Mysore",
            "selected_hotels": [{"name": "Radisson Blu Plaza Mysore"}],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Mysore Palace", "kind": "attraction"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Taxi to Mysore Palace", "kind": "transport"},
                    ],
                },
            ],
        }

        gaps = planning_completion_gaps(base)

        assert any("Bangalore to Mysore" in gap for gap in gaps)
        assert any("Mysore back to Bangalore" in gap for gap in gaps)

        unrelated_transport = {
            **base,
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Train: Chennai to Mysore", "kind": "transport"},
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Bus: Mysore to Chennai", "kind": "transport"},
                    ],
                },
            ],
        }
        assert len([
            gap for gap in planning_completion_gaps(unrelated_transport)
            if "journey from" in gap
        ]) == 2

        no_hotel_boundaries = {
            **base,
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Train: Bangalore to Mysore", "kind": "transport"}],
            }],
        }
        assert len([
            gap for gap in planning_completion_gaps(no_hotel_boundaries)
            if "journey from" in gap
        ]) == 2

        create_trip_plan.invoke({
            "destination": "Mysore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-11",
            "origin": "Bangalore",
        })
        save_result = update_trip_plan.invoke({"updates_json": json.dumps(base)})
        assert save_result.startswith(
            "Error: itinerary sanity validation rejected this update before persistence."
        )
        assert "Bangalore to Mysore" in save_result
        assert "Mysore back to Bangalore" in save_result

        complete = {
            **base,
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Train: Bengaluru to Mysuru", "kind": "transport"},
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Mysore Palace", "kind": "attraction"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Train: Mysuru to Bengaluru", "kind": "transport"},
                    ],
                },
            ],
        }
        complete_gaps = planning_completion_gaps(complete)

        assert not any("journey from" in gap for gap in complete_gaps)

    def test_create_trip_plan(self):
        result = create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
            "origin": "Delhi",
        })
        assert "Goa" in result
        assert "DRAFT" in result

    def test_create_trip_plan_defaults_origin_from_saved_home_area(self):
        update_preferences({
            "profile": {"home_city": "Bangalore", "home_area": "Whitefield"},
        })

        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == "Whitefield, Bangalore"
        assert parsed["travel_scope"] == "round_trip"

    def test_create_trip_plan_persists_self_arranged_arrival_without_origin(self):
        update_preferences({"profile": {"home_city": "Bangalore"}})

        create_trip_plan.invoke({
            "destination": "Pondicherry",
            "departure_date": "2026-11-07",
            "return_date": "2026-11-09",
            "travel_scope": "destination_only",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == ""
        assert parsed["travel_scope"] == "destination_only"

    def test_resume_keeps_existing_explicit_origin(self):
        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
            "origin": "Mysore",
        })
        update_preferences({"profile": {"home_city": "Bangalore"}})

        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == "Mysore"

    def test_get_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Goa"
        assert parsed["status"] == "draft"

    def test_get_trip_plan_no_plan(self):
        result = get_trip_plan.invoke({})
        assert "No active trip plan" in result

    def test_update_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update = json.dumps({
            "selected_flights": [{"airline": "IndiGo", "price": 8500}],
            "weather": {
                "source": "forecast",
                "days": [{"date": "2026-07-01", "summary": "Rain", "high_c": 29}],
            },
            "total_cost": 8500,
        })
        result = update_trip_plan.invoke({"updates_json": update})
        assert "updated" in result

        plan = json.loads(get_trip_plan.invoke({}))
        assert len(plan["selected_flights"]) == 1
        assert plan["weather"]["source"] == "forecast"
        assert plan["total_cost"] == 8500

    def test_update_trip_plan_moves_known_closed_day_before_persistence(
        self, monkeypatch
    ):
        weekdays = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )

        def structured_hours(name, _destination):
            if name != "Closed Museum":
                return {}
            return {
                "name": name,
                "weekday_descriptions": [
                    f"{day}: {'Closed' if day == 'Tuesday' else '9:00 AM - 6:00 PM'}"
                    for day in weekdays
                ],
            }

        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            structured_hours,
        )
        create_trip_plan.invoke(
            {
                "destination": "Paris",
                "departure_date": "2026-09-07",
                "return_date": "2026-09-08",
                "travel_scope": "destination_only",
            }
        )

        result = update_trip_plan.invoke(
            {
                "updates_json": json.dumps(
                    {
                        "day_wise_itinerary": [
                            {
                                "day": 1,
                                "stops": [{"name": "Hotel Lutetia", "kind": "hotel"}],
                            },
                            {
                                "day": 2,
                                "stops": [
                                    {
                                        "name": "Closed Museum",
                                        "kind": "attraction",
                                        "time": "10:00",
                                        "duration_min": 90,
                                    }
                                ],
                            },
                        ]
                    }
                )
            }
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert [
            stop["name"]
            for stop in saved["day_wise_itinerary"][0]["stops"]
            if stop["kind"] == "attraction"
        ] == ["Closed Museum"]
        assert saved["day_wise_itinerary"][1]["stops"] == []
        assert "Adjusted known closed-day visits before saving" in result

    def test_update_trip_plan_does_not_infer_closed_day_from_unknown_hours(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            lambda *_: {},
        )
        create_trip_plan.invoke(
            {
                "destination": "Paris",
                "departure_date": "2026-09-07",
                "return_date": "2026-09-08",
                "travel_scope": "destination_only",
            }
        )
        itinerary = [
            {
                "day": 1,
                "stops": [{"name": "Hotel Lutetia", "kind": "hotel"}],
            },
            {
                "day": 2,
                "stops": [
                    {
                        "name": "Unknown Museum",
                        "kind": "attraction",
                        "time": "10:00",
                        "duration_min": 90,
                    }
                ],
            },
        ]

        result = update_trip_plan.invoke(
            {"updates_json": json.dumps({"day_wise_itinerary": itinerary})}
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert saved["day_wise_itinerary"] == itinerary
        assert "Adjusted known closed-day visits before saving" not in result

    def test_update_trip_plan_owns_numeric_budget_as_structured_user_target(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        update_trip_plan.invoke(
            {"updates_json": json.dumps({"budget": 100000, "currency": "INR"})}
        )

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["budget"]["amount"] == 100000
        assert plan["budget"]["currency"] == "INR"
        assert plan["budget"]["owner"] == "user"
        assert plan["budget"]["updated_at"]

    def test_update_trip_plan_rejects_placeholder_hotel_selection(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Hotel (TBD)", "price": 15000}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_hotels"] == []
        assert "Hotel planning incomplete" in result
        assert "search_hotels" in result

    def test_update_trip_plan_rejects_generic_city_hotel_selections(self):
        create_trip_plan.invoke({
            "destination": "Kochi, Kerala",
            "departure_date": "2026-12-12",
            "return_date": "2026-12-18",
        })
        before = json.loads(get_trip_plan.invoke({}))
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [
                {"name": "Hotel in Kochi", "price": 15000},
                {"name": "Kochi Hotel", "price": 14000},
            ],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel in Kochi", "kind": "hotel"}],
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan == before
        assert result.startswith(
            "Error: itinerary sanity validation rejected this update before persistence."
        )
        assert "no bookable property" in result

    def test_update_trip_plan_accepts_concrete_hotel_selection(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "DoubleTree by Hilton Goa - Panaji"}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{
                    "name": "DoubleTree by Hilton Goa - Panaji",
                    "kind": "hotel",
                }],
            }],
        })})

        assert "Hotel planning incomplete" not in result

    def test_update_trip_plan_replaces_unnamed_anchors_with_concrete_hotel(self):
        create_trip_plan.invoke({
            "destination": "Paris",
            "departure_date": "2027-04-05",
            "return_date": "2027-04-12",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Hotel Le Six",
                "city": "Paris",
                "address": "14 Rue Stanislas, Paris",
            }],
            "day_wise_itinerary": [
                {
                    "day": day,
                    "stops": [{"name": "Paris Hotel", "kind": "hotel"}],
                }
                for day in range(1, 8)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Hotel Le Six"}
        assert all(stop["address"] == "14 Rue Stanislas, Paris" for stop in hotel_stops)
        assert "no bookable property" not in result

    def test_one_named_hotel_cannot_mask_unnamed_stays_in_other_cities(self):
        create_trip_plan.invoke({
            "destination": "Rajasthan",
            "departure_date": "2027-02-02",
            "return_date": "2027-02-10",
        })
        before = json.loads(get_trip_plan.invoke({}))
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Twinstar Standard",
                "city": "Jaipur",
                "address": "Jaipur City Center",
            }],
            "day_wise_itinerary": [
                {
                    "day": day,
                    "city": city,
                    "stops": [{
                        "name": f"Hotel in {city}",
                        "kind": "hotel",
                    }],
                }
                for day, city in enumerate(
                    [
                        "Jaipur",
                        "Jaipur",
                        "Jodhpur",
                        "Jodhpur",
                        "Jodhpur",
                        "Udaipur",
                        "Udaipur",
                        "Udaipur",
                    ],
                    start=1,
                )
            ],
        })})

        assert json.loads(get_trip_plan.invoke({})) == before
        assert result.startswith(
            "Error: itinerary sanity validation rejected this update before persistence."
        )
        assert "Day(s) 3, 4, 5, 6, 7, 8 name no bookable property" in result

    def test_selected_gangtok_stay_cannot_mask_lachen_placeholders(self):
        create_trip_plan.invoke({
            "destination": "Gangtok & North Sikkim",
            "departure_date": "2027-10-04",
            "return_date": "2027-10-07",
        })
        before = json.loads(get_trip_plan.invoke({}))

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Elgin Nor-Khill",
                "city": "Gangtok",
                "address": "Paljor Stadium Road, Gangtok, Sikkim, India",
            }],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "city": "Gangtok",
                    "stops": [{"name": "The Elgin Nor-Khill", "kind": "hotel"}],
                },
                {
                    "day": 2,
                    "city": "Lachen",
                    "stops": [{"name": "Premium Hotel Lachen (TBD)", "kind": "hotel"}],
                },
                {
                    "day": 3,
                    "city": "Lachen",
                    "stops": [{"name": "Premium Hotel Lachen (TBD)", "kind": "hotel"}],
                },
            ],
        })})

        assert json.loads(get_trip_plan.invoke({})) == before
        assert result.startswith(
            "Error: itinerary sanity validation rejected this update before persistence."
        )
        assert "Hotel placeholders remain on Day(s) 2, 3" in result

    def test_update_trip_plan_replaces_placeholder_anchors_with_concrete_hotel(self):
        create_trip_plan.invoke({
            "destination": "Mauritius",
            "departure_date": "2026-08-28",
            "return_date": "2026-09-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel (TBD)", "kind": "hotel", "time": "09:00"},
                    {"name": "Blue Bay Marine Park", "kind": "attraction", "time": "10:00"},
                    {"name": "Hotel (TBD)", "kind": "hotel", "time": "18:00"},
                ],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Preskil Island Resort",
                "destination": "Mauritius",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert "Hotel planning incomplete" not in result
        assert {stop["name"] for stop in hotel_stops} == {"Preskil Island Resort"}
        assert [stop["time"] for stop in hotel_stops] == ["09:00", "18:00"]

    def test_itinerary_update_cannot_restore_generic_or_placeholder_hotel(self):
        create_trip_plan.invoke({
            "destination": "Gujarat",
            "departure_date": "2026-12-07",
            "return_date": "2026-12-12",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Rann Utsav Tent City",
                "city": "Kutch",
                "address": "Dhordo, Kutch, Gujarat",
            }],
            "day_wise_itinerary": [{
                "day": 3,
                "city": "Kutch",
                "stops": [{"name": "Rann Utsav Tent City", "kind": "hotel"}],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": day,
                    "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
                }
                for day in range(3, 6)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Rann Utsav Tent City"}
        assert "Hotel placeholders remain" not in result

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": day,
                    "city": "Kutch",
                    "stops": [{"name": "Hotel (Kutch)", "kind": "hotel"}],
                }
                for day in range(3, 6)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Rann Utsav Tent City"}
        assert "no bookable property" not in result

    def test_update_trip_plan_rejects_hotel_outside_destination_atomically(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Mountain Luxury Resort",
                "destination": "Queenstown, New Zealand",
                "address": "Kawarau Village, Queenstown, New Zealand",
            }],
            "total_cost": 125000,
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert result.startswith("Error: hotel location must match")
        assert "outside the trip destination 'Manali, India'" in result
        assert plan["selected_hotels"] == []
        assert plan["total_cost"] == 0

    def test_update_trip_plan_accepts_hotel_with_matching_destination_evidence(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Himalayan",
                "destination": "Manali",
                "address": "Hadimba Road, Manali, Himachal Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert not result.startswith("Error:")
        assert plan["selected_hotels"][0]["name"] == "The Himalayan"

    def test_update_trip_plan_accepts_hotel_in_evidenced_itinerary_city(self):
        create_trip_plan.invoke({
            "destination": "Madhya Pradesh",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Old Indore Hotel", "city": "Indore"}],
            "day_wise_itinerary": [{
                "day": 1,
                "city": "Indore",
                "stops": [{"name": "Old Indore Hotel", "kind": "hotel"}],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "WOW Hotel Indore",
                "city": "Indore",
                "address": "AB Road, Indore, Madhya Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert not result.startswith("Error:")
        assert plan["selected_hotels"][0]["name"] == "WOW Hotel Indore"
        assert plan["day_wise_itinerary"][0]["stops"][0]["name"] == "WOW Hotel Indore"

    def test_update_trip_plan_replaces_hotel_in_itinerary_anchors(self, monkeypatch):
        from tripplanner.web import trip_view

        def place_details(name, _destination):
            coords = {
                "The Himalayan": (32.25, 77.18),
                "Hadimba Temple": (32.24, 77.19),
                "Solang Valley": (32.32, 77.16),
            }
            lat, lng = coords.get(name, (32.24, 77.18))
            return {"name": name, "lat": lat, "lng": lng}

        monkeypatch.setattr(
            trip_view.places_cache, "top_places", lambda *_args, **_kwargs: []
        )
        monkeypatch.setattr(
            trip_view.places_cache, "prefetch", lambda *_args, **_kwargs: None
        )
        monkeypatch.setattr(trip_view.places_cache, "get_details", place_details)
        monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(trip_view, "_airport_pin", lambda _destination: None)
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Wrong Mountain Resort",
                "destination": "Manali",
            }],
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "09:00"},
                    {"name": "Hadimba Temple", "kind": "attraction", "time": "10:00"},
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "18:00"},
                ]},
                {"day": 2, "stops": [
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "09:00"},
                    {"name": "Solang Valley", "kind": "attraction", "time": "10:00"},
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "18:00"},
                ]},
            ],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Himalayan",
                "destination": "Manali",
                "address": "Hadimba Road, Manali, Himachal Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert not result.startswith("Error:")
        assert {stop["name"] for stop in hotel_stops} == {"The Himalayan"}
        assert [stop["time"] for stop in hotel_stops] == [
            "09:00", "18:00", "09:00", "18:00",
        ]
        assert all(stop["address"].startswith("Hadimba Road") for stop in hotel_stops)
        map_names = {pin["name"] for pin in trip_view.build_map_view(plan)["pins"]}
        assert "The Himalayan" in map_names
        assert "Wrong Mountain Resort" not in map_names

    def test_update_trip_plan_rejects_hotel_without_destination_evidence(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Mystery Luxury Resort",
                "search_destination": "Manali, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert "has no location evidence matching" in result
        assert plan["selected_hotels"] == []

    def test_update_trip_plan_warns_about_restaurant_placeholders(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                    {"name": "Dinner TBD", "kind": "meal"},
                ],
            }],
        })})

        assert "Restaurant planning incomplete" in result
        assert "nearby_restaurants" in result

    def test_update_trip_plan_accepts_named_restaurants(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                    {"name": "Peter Cat", "kind": "restaurant"},
                ],
            }],
        })})

        assert "Restaurant planning incomplete" not in result

    def test_update_trip_plan_warns_when_full_day_has_no_restaurant(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                ],
            }],
        })})

        assert "Day 1 has multiple activities but no named restaurant stop" in result

    def test_update_trip_plan_warns_about_hotel_only_days(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Holiday Inn Resort Goa"}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Holiday Inn Resort Goa", "kind": "hotel"},
                    {"name": "Holiday Inn Resort Goa", "kind": "hotel"},
                ],
            }],
        })})

        assert "Itinerary planning incomplete" in result
        assert "Day 1 has no planned places beyond the hotel" in result

    def test_update_trip_plan_accepts_transport_only_travel_day(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Overnight train to Goa", "kind": "transport"}],
            }],
        })})

        assert "no planned places beyond the hotel" not in result

    def test_update_trip_plan_rejects_duplicate_or_backwards_visit_times_atomically(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        original = [{
            "day": 1,
            "stops": [
                {"name": "Morning Gallery", "kind": "attraction", "time": "09:00"},
                {"name": "Coastal Walk", "kind": "attraction", "time": "11:00"},
            ],
        }]
        update_trip_plan.invoke({"updates_json": json.dumps({"day_wise_itinerary": original})})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Cavelossim Beach", "kind": "attraction", "time": "10:00"},
                    {"name": "Basilica of Bom Jesus", "kind": "attraction", "time": "10:00"},
                    {"name": "Colva Beach", "kind": "attraction", "time": "09:30"},
                ],
            }],
        })})

        assert "times must increase in circuit order" in result
        assert "Basilica of Bom Jesus" in result
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == original

        tight_result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {
                        "name": "Cavelossim Beach",
                        "kind": "attraction",
                        "time": "10:00",
                        "duration_min": 90,
                    },
                    {"name": "Colva Beach", "kind": "attraction", "time": "11:00"},
                ],
            }],
        })})

        assert "not before 12:00" in tight_result
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == original

    def test_reflow_orders_fully_timed_stops_and_repairs_time_collisions(self, monkeypatch):
        from tripplanner.tools import trip_planner

        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_summary",
            lambda _name, _destination: {"lat": 15.3, "lng": 73.9},
        )
        plan = {
            "destination": "Goa",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Holiday Inn", "kind": "hotel"},
                    {"name": "Dinner", "kind": "meal", "time": "18:30", "duration_min": 60},
                    {"name": "Cavelossim Beach", "kind": "attraction", "time": "10:00", "duration_min": 90},
                    {"name": "Basilica", "kind": "attraction", "time": "10:00", "duration_min": 75},
                    {"name": "Colva Beach", "kind": "attraction", "time": "16:30", "duration_min": 90},
                    {"name": "Holiday Inn", "kind": "hotel"},
                ],
            }],
        }

        assert trip_planner._reflow_unbooked_attractions(plan) is True
        stops = plan["day_wise_itinerary"][0]["stops"]
        assert [stop["name"] for stop in stops] == [
            "Holiday Inn", "Cavelossim Beach", "Basilica", "Colva Beach", "Dinner", "Holiday Inn",
        ]
        times = [trip_planner._parse_hhmm(stop.get("time", "")) for stop in stops[1:-1]]
        assert all(left is not None and right is not None and left < right for left, right in zip(times, times[1:]))

    def test_set_stop_booked_toggles_flag(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Baga Beach", "kind": "attraction"}]},
            ],
        })})
        assert set_stop_booked(1, "Baga Beach", True) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["booked"] is True
        # toggling off persists too
        assert set_stop_booked(1, "baga beach", False) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["booked"] is False

    def test_remove_selection_drops_itinerary_only_place(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        # Place a stop directly in the itinerary WITHOUT adding it to a
        # selected_* bucket (mimics the agent weaving it into the plan).
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})
        assert remove_selection("attraction", "Fort Aguada") is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_clears_selected_bucket_and_itinerary(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})

        assert remove_selection("attraction", "Fort Aguada") is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_activities"] == []
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_removes_only_requested_occurrence(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction", "time": "10:00"}]},
                {"day": 2, "stops": [{"name": "Fort Aguada", "kind": "attraction", "time": "16:00"}]},
            ],
        })})

        assert remove_selection(
            "attraction", "Fort Aguada", day=2, stop=1, all_occurrences=False
        ) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["time"] == "10:00"
        assert plan["day_wise_itinerary"][1]["stops"] == []
        assert plan["selected_activities"] == [{"name": "Fort Aguada"}]

    def test_remove_selection_last_occurrence_clears_selected_bucket(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})

        assert remove_selection(
            "attraction", "Fort Aguada", day=1, stop=1, all_occurrences=False
        ) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_activities"] == []
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_rejects_single_hotel_circuit_anchor(self):
        create_trip_plan.invoke({
            "destination": "London",
            "departure_date": "2026-08-26",
            "return_date": "2026-08-31",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Wilde Aparthotels", "city": "London"}],
            "day_wise_itinerary": [
                {
                    "day": 4,
                    "stops": [
                        {"name": "Wilde Aparthotels", "kind": "hotel"},
                        {"name": "Kew Gardens", "kind": "attraction"},
                        {"name": "Wilde Aparthotels", "kind": "hotel"},
                    ],
                },
            ],
        })})

        assert remove_selection(
            "hotel", "Wilde Aparthotels", day=4, stop=1, all_occurrences=False
        ) is False
        plan = json.loads(get_trip_plan.invoke({}))
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]] == [
            "Wilde Aparthotels",
            "Kew Gardens",
            "Wilde Aparthotels",
        ]

    def test_set_stop_booked_normalizes_string_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 1, "stops": ["Anjuna Market"]}],
        })})
        assert set_stop_booked(1, "Anjuna Market", True) is True
        plan = json.loads(get_trip_plan.invoke({}))
        stop = plan["day_wise_itinerary"][0]["stops"][0]
        assert stop == {"name": "Anjuna Market", "booked": True}

    def test_set_stop_booked_unknown_returns_false(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        assert set_stop_booked(1, "Nowhere", True) is False

    def test_add_selection_infers_time_between_neighbor_stops(self):
        from tripplanner.tools.trip_planner import add_selection

        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Kaali Maa Pujo Pandal", "kind": "attraction", "time": "09:30"},
                        {"name": "Peter Cat", "kind": "meal", "time": "19:00"},
                    ],
                }
            ]
        })})

        res = add_selection("attraction", {"name": "Victoria Memorial"})
        assert res["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        stops = plan["day_wise_itinerary"][0]["stops"]
        vm = next(s for s in stops if str(s.get("name")) == "Victoria Memorial")
        assert vm.get("time") != ""
        assert vm.get("time") is not None

    def test_add_selection_keeps_explicit_itinerary_day(self, monkeypatch):
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_summary",
            lambda name, _destination: {
                "North Stay": {"lat": 15.60, "lng": 73.75},
                "South Stay": {"lat": 15.20, "lng": 74.00},
                "North Market": {"lat": 15.59, "lng": 73.76},
            }.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Stay", "kind": "hotel"}]},
                {"day": 2, "stops": [{"name": "South Stay", "kind": "hotel"}]},
            ],
        })})

        result = add_selection(
            "attraction", {"name": "North Market"}, preferred_day=2
        )

        assert result["placement"] == {"day": 2, "stop": 2, "name": "North Market"}
        plan = json.loads(get_trip_plan.invoke({}))
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]] == [
            "North Stay"
        ]
        assert [stop["name"] for stop in plan["day_wise_itinerary"][1]["stops"]] == [
            "South Stay",
            "North Market",
        ]

    def test_crowded_explicit_day_offers_review_without_moving_choice(self):
        from tripplanner.tools.trip_planner import assess_itinerary_change

        plan = {
            "destination": "Goa",
            "day_wise_itinerary": [{
                "day": 3,
                "stops": [
                    {"name": "Stay", "kind": "hotel"},
                    {"name": "Fort", "kind": "attraction", "duration_min": 90},
                    {"name": "Beach", "kind": "attraction", "duration_min": 90},
                    {"name": "Market", "kind": "attraction", "duration_min": 90},
                    {"name": "Museum", "kind": "attraction", "duration_min": 90},
                    {"name": "Dinner", "kind": "meal", "duration_min": 90},
                    {"name": "Stay", "kind": "hotel"},
                ],
            }],
        }

        review = assess_itinerary_change(
            plan,
            action="added",
            name="Museum",
            days=[3],
        )

        assert review is not None
        assert review["day"] == 3
        assert review["summary"].startswith("Day 3 may feel crowded")
        assert "Do not change the itinerary" in review["prompt"]
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]][4] == "Museum"

    def test_direct_add_reports_exact_day_and_material_review(self):
        from tripplanner.web import trip_operations

        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 3,
                "stops": [
                    {"name": "Taj Cidade de Goa", "kind": "hotel"},
                    {"name": "Fort", "kind": "attraction"},
                    {"name": "Beach", "kind": "attraction"},
                    {"name": "Market", "kind": "attraction"},
                    {"name": "Dinner", "kind": "meal"},
                    {"name": "Taj Cidade de Goa", "kind": "hotel"},
                ],
            }],
        })})

        result = trip_operations.select("attraction", "Museum", day=3)

        assert result["alerts"][0] == "Added Museum to Day 3."
        assert result["placement"]["day"] == 3
        assert result["planner_review"]["day"] == 3

    def test_add_selection_places_restaurant_as_meal(self):
        create_trip_plan.invoke({
            "destination": "Paris",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-20",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 1, "stops": []}],
        })})

        result = add_selection("meal", {"name": "Le Comptoir"}, preferred_day=1)

        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["kind"] == "meal"

    def test_explicit_day_moves_existing_unbooked_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is True
        assert result["placement"] == {"day": 1, "stop": 1, "name": "North Market"}
        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["name"] == "North Market"
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []

    def test_explicit_day_repositions_already_selected_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is True
        assert result["placement"]["day"] == 1
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []

    def test_explicit_day_moves_only_requested_repeated_occurrence(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-22",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 3, "stops": []},
            ],
        })})

        result = add_selection(
            "attraction",
            {"name": "North Market"},
            preferred_day=3,
            source_day=2,
            source_stop=1,
        )

        assert result["ok"] is True
        assert result["placement"]["day"] == 3
        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["name"] == "North Market"
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []
        assert result["trip"]["day_wise_itinerary"][2]["stops"][0]["name"] == "North Market"

    def test_explicit_day_rejects_repeated_occurrence_collision(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-22",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection(
            "attraction",
            {"name": "North Market"},
            preferred_day=1,
            source_day=2,
            source_stop=1,
        )

        assert result["ok"] is False
        assert result["alerts"] == ["North Market is already on Day 1. Choose a different day."]
        assert [
            stop["name"]
            for day in result["trip"]["day_wise_itinerary"]
            for stop in day["stops"]
        ] == ["North Market", "North Market"]

    def test_explicit_unavailable_day_returns_alternatives_without_saving(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 2, "stops": []}, {"day": 3, "stops": []}],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is False
        assert "Choose Day 2, Day 3, or Best day" in result["alerts"][0]
        assert result["trip"].get("selected_activities") == []

    def test_explicit_day_does_not_move_booked_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [
                    {"name": "North Market", "kind": "attraction", "booked": True}
                ]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is False
        assert "booked on Day 2" in result["alerts"][0]
        assert "unbook it and choose Day 1 again" in result["alerts"][0]
        assert result["trip"]["day_wise_itinerary"][1]["stops"][0]["booked"] is True

    def test_add_hotel_stay_updates_range(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Old Stay", "kind": "hotel"}, {"name": "Fort Aguada", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "Old Stay", "kind": "hotel"}, {"name": "Baga Beach", "kind": "attraction"}]},
                {"day": 3, "stops": [{"name": "Candolim", "kind": "attraction"}]},
            ],
        })})

        result = add_hotel_stay("Taj Goa", start_day=2, end_day=3, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        day2 = plan["day_wise_itinerary"][1]["stops"]
        day3 = plan["day_wise_itinerary"][2]["stops"]
        assert day2[0]["name"] == "Taj Goa"
        assert day2[0]["kind"] == "hotel"
        assert day3[0]["name"] == "Taj Goa"
        assert day3[0]["kind"] == "hotel"

    def test_add_hotel_stay_replacement_prunes_old_selected_hotel(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "ITC Goa"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "ITC Goa", "kind": "hotel"}]},
                {"day": 2, "stops": [{"name": "ITC Goa", "kind": "hotel"}]},
            ],
        })})

        result = add_hotel_stay("Hyatt Goa", start_day=1, end_day=2, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        selected = [str(h.get("name") or "") for h in plan.get("selected_hotels") or [] if isinstance(h, dict)]
        assert "Hyatt Goa" in selected
        assert "ITC Goa" not in selected

    def test_hotel_replacement_reflows_unbooked_attractions_by_proximity(self, monkeypatch):
        coords = {
            "North Stay": {"lat": 15.60, "lng": 73.75},
            "South Stay": {"lat": 15.20, "lng": 74.00},
            "North Beach": {"lat": 15.59, "lng": 73.76},
            "South Fort": {"lat": 15.21, "lng": 73.99},
        }
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_summary",
            lambda name, _destination: coords.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "North Stay", "kind": "hotel"},
                    {"name": "South Fort", "kind": "attraction"},
                ]},
                {"day": 2, "stops": [
                    {"name": "South Stay", "kind": "hotel"},
                    {"name": "North Beach", "kind": "attraction"},
                ]},
            ],
        })})

        result = add_hotel_stay("North Stay", start_day=1, end_day=1, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        day1 = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2 = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1 == ["North Stay", "North Beach"]
        assert day2 == ["South Stay", "South Fort"]

    def test_itinerary_reflow_keeps_booked_attraction_on_its_day(self, monkeypatch):
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_summary",
            lambda *_args: {"lat": 15.5, "lng": 73.8},
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [{"name": "Taj Cidade de Goa", "kind": "hotel"}],
                },
                {"day": 2, "stops": [
                    {"name": "Booked Tour", "kind": "attraction", "booked": True},
                    {"name": "Flexible Stop", "kind": "attraction"},
                ]},
            ],
        })})

        add_hotel_stay("New Stay", start_day=1, end_day=2, replace_existing=True)
        plan = json.loads(get_trip_plan.invoke({}))
        day2 = plan["day_wise_itinerary"][1]["stops"]
        assert any(stop.get("name") == "Booked Tour" and stop.get("booked") for stop in day2)

    def test_attraction_add_and_remove_reflow_all_days(self, monkeypatch):
        coords = {
            "North Stay": {"lat": 15.60, "lng": 73.75},
            "South Stay": {"lat": 15.20, "lng": 74.00},
            "North Beach": {"lat": 15.59, "lng": 73.76},
            "North Market": {"lat": 15.58, "lng": 73.77},
            "South Fort": {"lat": 15.21, "lng": 73.99},
        }
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_summary",
            lambda name, _destination: coords.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [
                {"name": "North Beach"},
                {"name": "South Fort"},
            ],
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "North Stay", "kind": "hotel"},
                    {"name": "South Fort", "kind": "attraction"},
                ]},
                {"day": 2, "stops": [
                    {"name": "South Stay", "kind": "hotel"},
                    {"name": "North Beach", "kind": "attraction"},
                ]},
            ],
        })})

        add_selection("attraction", {"name": "North Market"})
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1_names == ["North Stay", "North Beach", "North Market"]
        assert day2_names == ["South Stay", "South Fort"]

        assert remove_selection("attraction", "North Beach") is True
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1_names == ["North Stay", "North Market"]
        assert day2_names == ["South Stay", "South Fort"]

    def test_add_second_hotel_spreads_instead_of_refreshing_first(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Hotel One", "kind": "hotel"}, {"name": "Baga Beach", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "Anjuna Market", "kind": "attraction"}]},
            ],
        })})

        add_selection("hotel", {"name": "Hotel One"})
        add_selection("hotel", {"name": "Hotel Two"})
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [
            (s.get("name") if isinstance(s, dict) else str(s))
            for s in plan["day_wise_itinerary"][0]["stops"]
        ]
        day2_names = [
            (s.get("name") if isinstance(s, dict) else str(s))
            for s in plan["day_wise_itinerary"][1]["stops"]
        ]
        assert "Hotel One" in day1_names
        assert "Hotel Two" in day2_names

    def test_finalize_trip(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            selected_flights=[{"airline": "IndiGo", "price": 8500}]
        )

        result = finalize_trip.invoke({})

        assert "FINALIZED" in result
        assert "IndiGo" in result

    def test_finalize_requires_selections(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = finalize_trip.invoke({})
        assert "Cannot finalize" in result

    def test_finalize_blocks_missing_return_coverage(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            origin="Delhi",
            travel_scope="round_trip",
            return_date="2026-07-07",
            selected_flights=[{"airline": "IndiGo", "price": 8500}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {
                            "name": "Flight Delhi to Goa",
                            "kind": "flight",
                            "time": "08:00",
                            "duration_min": 120,
                        },
                        {"name": "Taj Goa", "kind": "hotel", "time": "11:00"},
                        {"name": "Riverside Walk", "kind": "attraction", "time": "13:00"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {"name": "Old Goa Walk", "kind": "attraction", "time": "11:00"},
                    ],
                },
            ],
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Goa back to Delhi" in result
        assert json.loads(get_trip_plan.invoke({}))["status"] == "draft"

    def test_finalize_blocks_activity_after_departure(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            origin="Delhi",
            travel_scope="round_trip",
            return_date="2026-07-07",
            selected_flights=[{"airline": "IndiGo", "price": 8500}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {
                            "name": "Flight Delhi to Goa",
                            "kind": "flight",
                            "time": "08:00",
                            "duration_min": 120,
                        },
                        {"name": "Taj Goa", "kind": "hotel", "time": "11:00"},
                        {"name": "Riverside Walk", "kind": "attraction", "time": "13:00"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "08:00"},
                        {
                            "name": "Flight Goa to Delhi",
                            "kind": "flight",
                            "time": "14:00",
                            "duration_min": 120,
                        },
                        {"name": "Old Goa Walk", "kind": "attraction", "time": "17:00"},
                    ],
                },
            ],
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Old Goa Walk" in result
        assert "after Flight Goa to Delhi" in result

    def test_finalize_blocks_known_closed_day(self, monkeypatch):
        def closed_monday(name, _destination):
            if name == "Closed Museum":
                return {
                    "name": name,
                    "weekday_descriptions": ["Monday: Closed"],
                }
            return {}

        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            closed_monday,
        )
        self._save_booking_ready_trip(
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {"name": "Closed Museum", "kind": "attraction", "time": "11:00"},
                    ],
                }
            ]
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Closed Museum is closed on Mondays" in result

    def test_finalize_blocks_placeholder_lodging(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Hotel option", "kind": "hotel", "time": "09:00"},
                        {
                            "name": "Riverside Walk",
                            "kind": "attraction",
                            "time": "11:00",
                        },
                    ],
                }
            ]
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Hotel placeholders remain on Day(s) 1" in result

    def test_finalize_keeps_unknown_place_facts_silent(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip()

        result = finalize_trip.invoke({})

        assert "FINALIZED" in result

    def test_execute_bookings(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            selected_flights=[{"airline": "IndiGo", "price": 8500}]
        )
        finalize_trip.invoke({})
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert "No active trip plan" in get_trip_plan.invoke({})

    def test_execute_requires_finalized(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = execute_bookings.invoke({})
        assert "must be finalized" in result

    def test_list_past_trips_empty(self):
        result = list_past_trips.invoke({})
        assert "No past trips" in result

    def test_full_lifecycle(self, monkeypatch):
        """Test the complete plan → finalize → execute → history cycle."""
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            destination="Manali",
            selected_hotels=[{"name": "Snow Valley", "city": "Manali", "price": 12000}],
            selected_activities=[{"name": "Rohtang Pass", "price": 2000}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Snow Valley", "kind": "hotel", "time": "09:00"},
                        {"name": "Rohtang Pass", "kind": "attraction", "time": "11:00"},
                    ],
                }
            ],
            cost_breakdown={"hotel": 12000, "activities": 2000},
            total_cost=14000,
        )
        # Finalize
        result = finalize_trip.invoke({})
        assert "FINALIZED" in result
        # Execute
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        # Check history
        result = list_past_trips.invoke({})
        assert "manali" in result.lower()


# ---------------------------------------------------------------------------
# Flight search helpers
# ---------------------------------------------------------------------------
from tripplanner.tools.flight_search import resolve_iata


class TestFlightHelpers:
    def test_resolve_iata_city_name(self):
        assert resolve_iata("Delhi") == "DEL"
        assert resolve_iata("mumbai") == "BOM"
        assert resolve_iata("Goa") == "GOI"

    def test_resolve_iata_already_code(self):
        assert resolve_iata("DEL") == "DEL"
        assert resolve_iata("bom") == "BOM"

    def test_resolve_iata_international(self):
        assert resolve_iata("Dubai") == "DXB"
        assert resolve_iata("Singapore") == "SIN"
        assert resolve_iata("London") == "LHR"


# ---------------------------------------------------------------------------
# Activity search helpers
# ---------------------------------------------------------------------------
from tripplanner.tools.activities_search import _get_coords


class TestActivityHelpers:
    def test_known_city_coords(self):
        coords = _get_coords("Goa")
        assert coords is not None
        lat, lon = coords
        assert 15 < lat < 16
        assert 73 < lon < 74

    def test_unknown_city_coords(self):
        assert _get_coords("Narnia") is None


# ---------------------------------------------------------------------------
# Google Places + Web search helpers (no network — config checks only)
# ---------------------------------------------------------------------------
from tripplanner.tools import google_places, web_search
from tripplanner.tools.google_places import (
    _format_place,
    _format_reviews,
    nearby_restaurants,
    search_places_with_reviews,
)
from tripplanner.tools.web_search import web_search as web_search_tool


class TestGooglePlacesHelpers:
    def test_format_place_full(self):
        out = _format_place({
            "id": "abc",
            "displayName": {"text": "Taj Mahal Palace"},
            "formattedAddress": "Mumbai, India",
            "rating": 4.6,
            "userRatingCount": 1234,
            "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE",
            "types": ["lodging", "hotel", "establishment"],
            "websiteUri": "https://taj.com",
            "internationalPhoneNumber": "+91 22 6665 3366",
            "currentOpeningHours": {"openNow": True},
        })
        assert out["name"] == "Taj Mahal Palace"
        assert out["rating"] == 4.6
        assert out["place_id"] == "abc"
        assert len(out["types"]) == 3

    def test_format_place_minimal(self):
        out = _format_place({})
        assert out["name"] == ""
        assert out["rating"] is None
        assert out["types"] == []

    def test_format_reviews_truncates(self):
        reviews = [
            {
                "rating": 5,
                "text": {"text": "x" * 500},
                "authorAttribution": {"displayName": "Alice"},
                "relativeTimeDescription": "1 month ago",
            }
        ] * 10
        out = _format_reviews(reviews, limit=3)
        assert len(out) == 3
        assert len(out[0]["text"]) == 300

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"google_places_api_key": ""})(),
        )
        # Re-bind in module under test
        monkeypatch.setattr(google_places, "get_settings", config.get_settings)
        assert not google_places.is_configured()
        result = search_places_with_reviews.invoke({"query": "test", "city": "Goa"})
        assert "not configured" in result.lower()
        result = nearby_restaurants.invoke({"city": "Goa"})
        assert "not configured" in result.lower()


def test_hotel_search_uses_google_fallback_when_amadeus_unconfigured(monkeypatch):
    from tripplanner.tools import hotel_search

    class FakeGoogleSearch:
        @staticmethod
        def invoke(args):
            return json.dumps([{"name": "Grounded Hotel", "rating": 4.7, **args}])

    # No live provider configured, so best-effort falls through to Amadeus then Google.
    monkeypatch.setattr(hotel_search, "get_hotel_providers", lambda: [])
    monkeypatch.setattr(hotel_search.amadeus_client, "is_configured", lambda: False)
    monkeypatch.setattr(hotel_search, "search_places_with_reviews", FakeGoogleSearch())

    result = hotel_search.search_hotels.invoke(
        {"city": "Paris", "checkin": "2026-09-01", "checkout": "2026-09-05"}
    )

    assert "Grounded Hotel" in result
    assert '"city": "Paris"' in result


class TestWebSearchHelpers:
    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"tavily_api_key": ""})(),
        )
        monkeypatch.setattr(web_search, "get_settings", config.get_settings)
        assert not web_search.is_configured()
        result = web_search_tool.invoke({"query": "best beaches in Goa"})
        assert "not configured" in result.lower()


# ---------------------------------------------------------------------------
# Duffel flight search helpers (no network — formatting & config checks only)
# ---------------------------------------------------------------------------
from tripplanner.tools import duffel_flights
from tripplanner.tools.duffel_flights import (
    _format_duration,
    _format_offers,
    _format_segment,
    search_flights_duffel,
)


class TestDuffelHelpers:
    def test_format_duration_basic(self):
        assert _format_duration("PT5H30M") == "5h 30m"
        assert _format_duration("PT2H") == "2h"
        assert _format_duration("PT45M") == "45m"
        assert _format_duration("") == ""

    def test_format_segment_minimal(self):
        seg = {
            "marketing_carrier": {"iata_code": "AI"},
            "marketing_carrier_flight_number": "101",
            "origin": {"iata_code": "DEL"},
            "destination": {"iata_code": "BOM"},
            "departing_at": "2026-03-01T09:30:00",
            "arriving_at": "2026-03-01T11:45:00",
            "duration": "PT2H15M",
        }
        line = _format_segment(seg)
        assert "AI101" in line
        assert "DEL 09:30" in line
        assert "BOM 11:45" in line
        assert "2h 15m" in line

    def test_format_offers_empty(self):
        assert "No Duffel offers" in _format_offers([], 5)

    def test_format_offers_sorts_by_price(self):
        offers = [
            {
                "total_amount": "500.00",
                "total_currency": "INR",
                "owner": {"name": "Expensive Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "XX"},
                                "marketing_carrier_flight_number": "999",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T08:00:00",
                                "arriving_at": "2026-03-01T10:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
            {
                "total_amount": "100.00",
                "total_currency": "INR",
                "owner": {"name": "Cheap Air"},
                "slices": [
                    {
                        "duration": "PT2H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "YY"},
                                "marketing_carrier_flight_number": "1",
                                "origin": {"iata_code": "DEL"},
                                "destination": {"iata_code": "BOM"},
                                "departing_at": "2026-03-01T09:00:00",
                                "arriving_at": "2026-03-01T11:00:00",
                                "duration": "PT2H",
                            }
                        ],
                    }
                ],
            },
        ]
        out = _format_offers(offers, 5)
        cheap_pos = out.find("Cheap Air")
        exp_pos = out.find("Expensive Air")
        assert 0 <= cheap_pos < exp_pos

    def test_not_configured_returns_friendly_message(self, monkeypatch):
        from tripplanner import config
        # No live provider configured, so the friendly Duffel setup message surfaces.
        monkeypatch.setattr(duffel_flights, "get_flight_provider", lambda: None)
        monkeypatch.setattr(
            config, "get_settings",
            lambda: type("S", (), {"duffel_api_key": ""})(),
        )
        monkeypatch.setattr(duffel_flights, "get_settings", config.get_settings)
        assert not duffel_flights.is_configured()
        result = search_flights_duffel.invoke({
            "origin": "Delhi",
            "destination": "Mumbai",
            "departure_date": "2026-03-01",
        })
        assert "not configured" in result.lower()
        assert "duffel.com/sign-up" in result.lower()


# ---------------------------------------------------------------------------
# Cosmos DB dispatch (mocked — verifies preferences + trip_planner branch
# correctly when storage_cosmos.is_enabled() returns True). No network.
# ---------------------------------------------------------------------------
from tripplanner import storage_cosmos, user_context
from tripplanner.tools import trip_planner


def test_restore_inspection_trip_writes_identity_copy_without_archiving(monkeypatch) -> None:
    source = {
        "trip_id": "spiti_valley_2027-06-01_2027-06-08",
        "user_id": "corpus-original",
        "destination": "Spiti Valley",
        "day_wise_itinerary": [{"day": 1, "stops": [{"name": "Narkanda"}]}],
    }
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(
        trip_planner.debug_store,
        "record_trip",
        lambda *_args, **_kwargs: pytest.fail("inspection must not alter the debug archive"),
    )
    token = user_context._user_id.set("corpus-spiti-food-friends-7d")
    try:
        restored = trip_planner.restore_inspection_trip(
            source,
            "corpus-spiti-food-friends-7d",
        )
    finally:
        user_context._user_id.reset(token)

    active = json.loads(
        (_TEST_DIR / "users/corpus-spiti-food-friends-7d/active_trip.json").read_text()
    )
    history = json.loads(
        (
            _TEST_DIR
            / "users/corpus-spiti-food-friends-7d/trips"
            / "spiti_valley_2027-06-01_2027-06-08.json"
        ).read_text()
    )
    assert restored["user_id"] == "corpus-spiti-food-friends-7d"
    assert active == history == restored
    assert source["user_id"] == "corpus-original"
    assert "updated_at" not in source


class TestCosmosDispatch:
    """When Cosmos is enabled, read/write go through storage_cosmos, not files."""

    def test_load_preferences_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {"trip_style": "adventure", "budget_level": "premium"},
        )
        prefs = load_preferences()
        assert prefs["trip_style"] == "adventure"
        assert prefs["budget_level"] == "premium"
        # defaults still merged for unspecified keys
        assert prefs["family"]["adults"] == 1

    def test_load_preferences_cosmos_missing_returns_defaults(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        prefs = load_preferences()
        assert prefs["trip_style"] == "balanced"

    def test_save_preferences_uses_cosmos(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: None,
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: captured.update(
                {"container": c, "user_id": u, "doc_id": d, "body": body}
            ),
        )
        save_preferences({"trip_style": "adventure"})
        assert captured["container"] == "users"
        assert captured["doc_id"] == "preferences"
        assert captured["user_id"] == "local"  # default user
        assert captured["body"]["trip_style"] == "adventure"

    def test_save_preferences_uses_current_user_id(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: None,
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: captured.update({"user_id": u}),
        )
        token = user_context._user_id.set("session-abc-123")
        try:
            save_preferences({"trip_style": "leisure"})
        finally:
            user_context._user_id.reset(token)
        assert captured["user_id"] == "session-abc-123"

    def test_update_preferences_replays_after_write_conflict(self, monkeypatch):
        state = {
            "body": {"trip_style": "balanced", "interests": ["museums"]},
            "version": '"v1"',
        }
        replace_calls = 0

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: storage_cosmos.VersionedDocument(
                body=state["body"], version=state["version"]
            ),
        )

        def replace(_container, _user_id, _doc_id, body, version):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 1:
                state["body"] = {
                    "trip_style": "leisure",
                    "interests": ["museums"],
                }
                state["version"] = '"v2"'
                raise storage_cosmos.WriteConflictError("concurrent update")
            assert version == '"v2"'
            state["body"] = body

        monkeypatch.setattr(storage_cosmos, "replace_doc_if_version", replace)

        result = update_preferences({"interests": ["hiking"]})

        assert replace_calls == 2
        assert result["trip_style"] == "leisure"
        assert result["interests"] == ["museums", "hiking"]

    def test_update_preferences_replays_after_create_conflict(self, monkeypatch):
        state = {"body": None, "version": None}
        create_calls = 0

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)

        def read_versioned(_container, _user, _doc_id):
            if state["body"] is None:
                return None
            return storage_cosmos.VersionedDocument(
                body=state["body"], version=state["version"]
            )

        def create(_container, _user, _doc_id, _body):
            nonlocal create_calls
            create_calls += 1
            state["body"] = {"trip_style": "leisure", "interests": ["museums"]}
            state["version"] = '"v1"'
            raise storage_cosmos.WriteConflictError("concurrent create")

        def replace(_container, _user, _doc_id, body, version):
            assert version == '"v1"'
            state["body"] = body

        monkeypatch.setattr(storage_cosmos, "read_doc_versioned", read_versioned)
        monkeypatch.setattr(storage_cosmos, "create_doc_if_absent", create)
        monkeypatch.setattr(storage_cosmos, "replace_doc_if_version", replace)

        result = update_preferences({"interests": ["hiking"]})

        assert create_calls == 1
        assert result["trip_style"] == "leisure"
        assert result["interests"] == ["museums", "hiking"]

    def test_load_active_trip_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {
                "destination": "Tokyo",
                "departure_date": "2026-09-01",
                "return_date": "2026-09-08",
                "status": "draft",
            },
        )
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Tokyo"
        assert parsed["status"] == "draft"

    def test_create_trip_plan_writes_to_cosmos(self, monkeypatch):
        captured: list[dict[str, object]] = []
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        # read_doc is called for preferences (load_preferences) and active_trip
        # — return None so defaults are used and no existing plan is found.
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: captured.append(
                {"container": c, "doc_id": d, "body": body}
            ),
        )
        result = create_trip_plan.invoke({
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
        })
        assert "Bali" in result
        # Should have upserted exactly the active_trip doc to the users container.
        active_writes = [
            c for c in captured
            if c["container"] == "users" and c["doc_id"] == "active_trip"
        ]
        assert len(active_writes) == 1
        assert active_writes[0]["body"]["destination"] == "Bali"

    def test_execute_bookings_deletes_active_trip_from_cosmos(self, monkeypatch):
        # State machine: cosmos read returns a finalized plan, then upserts and
        # deletes get captured. Mock all read_doc calls (prefs + active_trip).
        active_plan = {
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
            "travelers": "2 adults",
            "selected_flights": [{"airline": "AI", "price": 5000}],
            "selected_hotels": [{"name": "Hotel", "price": 8000}],
            "selected_activities": [],
            "day_wise_itinerary": [],
            "cost_breakdown": {},
            "total_cost": 13000,
            "notes": "",
            "status": "finalized",
        }
        delete_calls: list[tuple[str, str, str]] = []
        upsert_calls: list[tuple[str, str, str]] = []

        def _read(container: str, user: str, doc_id: str):
            if doc_id == "active_trip":
                return dict(active_plan)
            return None  # preferences fall back to defaults

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", _read)
        monkeypatch.setattr(storage_cosmos, "read_doc_versioned", lambda c, u, d: None)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: upsert_calls.append((c, u, d)),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: upsert_calls.append((c, u, d)),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "delete_doc",
            lambda c, u, d: delete_calls.append((c, u, d)),
        )

        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert ("users", "local", "active_trip") in delete_calls
        # The archived trip should be written to the trips container.
        assert any(c == "trips" for c, _, _ in upsert_calls)

    def test_list_past_trips_queries_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "query_docs",
            lambda c, u: [
                {
                    "destination": "Goa",
                    "departure_date": "2025-06-01",
                    "return_date": "2025-06-05",
                    "total_cost": 25000,
                    "status": "booked",
                },
                {
                    "destination": "Kerala",
                    "departure_date": "2025-12-10",
                    "return_date": "2025-12-15",
                    "total_cost": 30000,
                    "status": "booked",
                },
            ],
        )
        result = list_past_trips.invoke({})
        assert "Goa" in result
        assert "Kerala" in result


class TestUserContext:
    """ContextVar default + scoped override behavior."""

    def test_default_user_id(self):
        assert user_context.get_user_id() == "local"
        assert user_context.is_default_user() is True

    def test_set_and_reset_user_id(self):
        token = user_context._user_id.set("alice")
        try:
            assert user_context.get_user_id() == "alice"
            assert user_context.is_default_user() is False
        finally:
            user_context._user_id.reset(token)
        assert user_context.get_user_id() == "local"



# ---------------------------------------------------------------------------
# Trip system prompt — temporal context injection
# ---------------------------------------------------------------------------
from datetime import date, datetime, timedelta, timezone

from tripplanner.agents.trip_agent import TRIP_SYSTEM_PROMPT, build_trip_system_prompt


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


# ---------------------------------------------------------------------------
# Passive learning — learned_notes + remember_about_user tool
# ---------------------------------------------------------------------------
from tripplanner.agents.trip_agent import remember_about_user
from tripplanner.tools.user_preferences import add_learned_note


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


# ---------------------------------------------------------------------------
# Continuous learning — profile / family / interests / dislikes / trip_mentions
# ---------------------------------------------------------------------------
from tripplanner.agents.trip_agent import (
    add_family_member as tool_add_family_member,
    add_user_dislike as tool_add_user_dislike,
    add_user_interest as tool_add_user_interest,
    record_trip_mention as tool_record_trip_mention,
    update_user_profile as tool_update_user_profile,
)
from tripplanner.tools.user_preferences import (
    add_dislike,
    add_interest,
    add_trip_mention,
    update_profile,
    upsert_family_member,
)


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


# ---------------------------------------------------------------------------
# Saved trips — remember, resume, switch, delete (Session 19)
# ---------------------------------------------------------------------------
from tripplanner.tools.trip_planner import (
    _compute_trip_id,
    delete_saved_trip,
    list_saved_trips,
    resume_trip,
    switch_active_trip,
)


def _make_trip(dest, dep, ret, **selections):
    create_trip_plan.invoke(
        {"destination": dest, "departure_date": dep, "return_date": ret}
    )
    if selections:
        update_trip_plan.invoke({"updates_json": json.dumps(selections)})


class TestTripId:
    def test_stable_for_same_dest_and_dates(self):
        a = _compute_trip_id(
            {"destination": "Mumbai", "departure_date": "2026-07-10", "return_date": "2026-07-15"}
        )
        b = _compute_trip_id(
            {"destination": "mumbai", "departure_date": "2026-07-10", "return_date": "2026-07-15"}
        )
        assert a == b == "mumbai_2026-07-10_2026-07-15"

    def test_differs_for_different_dates(self):
        a = _compute_trip_id(
            {"destination": "Mumbai", "departure_date": "2026-07-10", "return_date": "2026-07-15"}
        )
        b = _compute_trip_id(
            {"destination": "Mumbai", "departure_date": "2026-08-01", "return_date": "2026-08-05"}
        )
        assert a != b

    def test_handles_missing_dates(self):
        assert _compute_trip_id({"destination": "Goa"}) == "goa_nodate_nodate"


class TestSavedTrips:
    def test_create_saves_to_history(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        trips = list_saved_trips()
        assert len(trips) == 1
        assert trips[0]["destination"] == "Mumbai"
        assert trips[0]["is_active"] is True
        assert trips[0]["trip_id"] == "mumbai_2026-07-10_2026-07-15"

    def test_starting_new_trip_keeps_previous(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15",
                   selected_hotels=[{"name": "Taj", "city": "Mumbai", "price": 9000}])
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        trips = list_saved_trips()
        dests = {t["destination"] for t in trips}
        assert dests == {"Mumbai", "Vietnam"}
        # The previous Mumbai trip retained its selection.
        mumbai = next(t for t in trips if t["destination"] == "Mumbai")
        assert mumbai["counts"]["hotels"] == 1

    def test_same_dest_and_dates_resumes_not_overwrites(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15",
                   selected_hotels=[{"name": "Taj", "city": "Mumbai", "price": 9000}])
        # Re-create with identical destination + dates -> should resume.
        result = create_trip_plan.invoke(
            {"destination": "Mumbai", "departure_date": "2026-07-10", "return_date": "2026-07-15"}
        )
        assert "Resumed" in result
        plan = json.loads(get_trip_plan.invoke({}))
        assert len(plan["selected_hotels"]) == 1  # selection preserved
        assert len(list_saved_trips()) == 1  # still one trip, merged

    def test_different_duration_kept_separate(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Mumbai", "2026-07-10", "2026-07-20")  # longer stay
        trips = list_saved_trips()
        assert len([t for t in trips if t["destination"] == "Mumbai"]) == 2

    def test_trips_are_numbered_in_creation_order(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        numbers = {t["destination"]: t["trip_number"] for t in list_saved_trips()}
        assert numbers == {"Mumbai": 1, "Vietnam": 2}

    def test_trip_number_is_stable_across_updates(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        before = list_saved_trips()[0]["trip_number"]
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        after = next(t for t in list_saved_trips() if t["destination"] == "Mumbai")
        assert after["trip_number"] == before

    def test_older_unnumbered_trips_are_backfilled_once(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        from tripplanner.tools import trip_planner as tp

        for plan in tp._all_history_trips():
            plan.pop("trip_number", None)
            tp._mirror_to_history(plan)
        first = {t["destination"]: t["trip_number"] for t in list_saved_trips()}
        second = {t["destination"]: t["trip_number"] for t in list_saved_trips()}
        assert sorted(first.values()) == [1, 2]
        assert first == second

    def test_switch_active_trip(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        # Vietnam is active now; switch back to Mumbai.
        plan = switch_active_trip("mumbai_2026-07-10_2026-07-15")
        assert plan is not None
        assert plan["destination"] == "Mumbai"
        active = json.loads(get_trip_plan.invoke({}))
        assert active["destination"] == "Mumbai"

    def test_switch_unknown_returns_none(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        assert switch_active_trip("nope_x_y") is None

    def test_delete_saved_trip(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        ok = delete_saved_trip("vietnam_2026-09-01_2026-09-10")
        assert ok is True
        trips = list_saved_trips()
        assert {t["destination"] for t in trips} == {"Mumbai"}

    def test_delete_active_clears_active_pointer(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        delete_saved_trip("mumbai_2026-07-10_2026-07-15")
        assert "No active trip plan" in get_trip_plan.invoke({})

    def test_resume_trip_by_destination(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        _make_trip("Vietnam", "2026-09-01", "2026-09-10")
        result = resume_trip.invoke({"destination": "Mumbai"})
        assert "Resumed" in result and "Mumbai" in result
        assert json.loads(get_trip_plan.invoke({}))["destination"] == "Mumbai"

    def test_resume_trip_by_id(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        result = resume_trip.invoke({"trip_id": "mumbai_2026-07-10_2026-07-15"})
        assert "Resumed" in result

    def test_resume_trip_no_match_lists_options(self):
        _make_trip("Mumbai", "2026-07-10", "2026-07-15")
        result = resume_trip.invoke({"destination": "Antarctica"})
        assert "Which saved trip" in result
        assert "Mumbai" in result

    def test_resume_trip_no_saved_trips(self):
        result = resume_trip.invoke({"destination": "Mumbai"})
        assert "no saved trips" in result.lower()
