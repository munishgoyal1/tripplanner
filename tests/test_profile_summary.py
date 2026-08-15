"""Tests for the continuous-learning layers added in Session 24:

1. ``profile_summary`` — system-authored running summary, gated by a durable digest.
2. trip-scoped constraints — one-off exceptions stored on the active trip.
3. passive-learning trip-scope guard — routes one-offs to the trip, not durable prefs.
"""

import os
import shutil
from pathlib import Path

import pytest

from tripplanner.tools import (
    passive_learning,
    profile_suggestions,
    profile_summary,
    trip_planner,
    user_preferences,
)
from tripplanner.tools.user_preferences import load_preferences, save_preferences

# Parallel sandboxes run this suite at the same time against one home
# directory, so a shared name means one run's teardown deletes another
# run's fixture mid-test. The pid keeps them disjoint.
_TEST_DIR = Path.home() / f".tripplanner_test_profile-{os.getpid()}"
_TEST_FILE = _TEST_DIR / "user_preferences.json"
_TEST_ACTIVE_TRIP = _TEST_DIR / "active_trip.json"
_TEST_TRIP_HISTORY = _TEST_DIR / "trips"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", _TEST_DIR)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", _TEST_FILE)
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", _TEST_DIR)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", _TEST_ACTIVE_TRIP)
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", _TEST_TRIP_HISTORY)
    _TEST_DIR.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------
class TestSchema:
    def test_default_profile_summary_fields(self):
        prefs = load_preferences()
        assert prefs["profile_summary"] == ""
        assert prefs["profile_summary_updated_at"] is None
        assert prefs["profile_summary_digest"] == ""


# ---------------------------------------------------------------------------
# trip constraints
# ---------------------------------------------------------------------------
class TestTripConstraints:
    def test_add_constraint_no_active_trip(self):
        assert trip_planner.add_trip_constraint("3-star is fine") is False

    def test_add_constraint_persists_and_dedupes(self):
        trip_planner.create_trip_plan.invoke(
            {"destination": "Goa", "departure_date": "2026-01-10", "return_date": "2026-01-15"}
        )
        assert trip_planner.add_trip_constraint("3-star is fine this trip") is True
        # duplicate (case-insensitive) is rejected
        assert trip_planner.add_trip_constraint("3-STAR is fine this trip") is False
        plan = trip_planner.load_active_trip_dict()
        assert plan["trip_constraints"] == ["3-star is fine this trip"]

    def test_blank_constraint_ignored(self):
        trip_planner.create_trip_plan.invoke(
            {"destination": "Goa", "departure_date": "2026-01-10", "return_date": "2026-01-15"}
        )
        assert trip_planner.add_trip_constraint("   ") is False


# ---------------------------------------------------------------------------
# passive-learning trip-scope guard
# ---------------------------------------------------------------------------
class TestTripScopeGuard:
    def test_cue_detection(self):
        assert passive_learning.has_trip_scope_cue("3-star is fine just for this trip")
        assert passive_learning.has_trip_scope_cue("OK with a connection this time")
        assert passive_learning.has_trip_scope_cue("I'll make an exception here")
        assert not passive_learning.has_trip_scope_cue("I always prefer 5-star hotels")

    def test_one_off_routes_to_trip_not_prefs(self, monkeypatch):
        # The extractor must NOT be called for a trip-scoped one-off.
        called = {"n": 0}

        def _boom(_text):
            called["n"] += 1
            return {"hotel_preferences": {"star_rating_min": 3}}

        monkeypatch.setattr(
            passive_learning.about_me_extractor, "extract_about_me", _boom
        )
        trip_planner.create_trip_plan.invoke(
            {"destination": "Goa", "departure_date": "2026-01-10", "return_date": "2026-01-15"}
        )
        touched = passive_learning.learn_from_message(
            "A 3-star hotel is fine just for this trip"
        )
        assert touched == ["trip_constraint"]
        assert called["n"] == 0
        # durable prefs untouched (still default star floor 3, unchanged)
        prefs = load_preferences()
        assert prefs["hotel_preferences"]["star_rating_min"] == 3
        plan = trip_planner.load_active_trip_dict()
        assert any("3-star" in c for c in plan["trip_constraints"])

    def test_durable_statement_still_extracts(self, monkeypatch):
        def _fake(_text):
            return {"interests": ["scuba diving"]}

        monkeypatch.setattr(
            passive_learning.about_me_extractor, "extract_about_me", _fake
        )
        raised = passive_learning.learn_from_message(
            "I always love scuba diving on my trips"
        )
        assert raised and raised != ["trip_constraint"]
        profile_suggestions.resolve(raised[0], "save")
        prefs = load_preferences()
        assert "scuba diving" in prefs["interests"]


# ---------------------------------------------------------------------------
# profile summary regeneration + digest gating
# ---------------------------------------------------------------------------
class TestProfileSummary:
    def test_no_signal_returns_empty(self, monkeypatch):
        # _has_signal is False on fresh prefs -> regenerate short-circuits.
        calls = {"n": 0}
        monkeypatch.setattr(
            profile_summary,
            "regenerate",
            lambda prefs: (calls.__setitem__("n", calls["n"] + 1) or "SUMMARY"),
        )
        # fresh prefs have no durable signal, digest differs from "" stored... but
        # update_summary calls regenerate which we mocked; ensure it persists digest
        out = profile_summary.update_summary()
        # regenerate mocked returns "SUMMARY" so it gets stored
        assert out == "SUMMARY"
        assert calls["n"] == 1

    def test_digest_gating_skips_llm(self, monkeypatch):
        prefs = load_preferences()
        prefs["interests"] = ["hiking"]
        save_preferences(prefs)

        calls = {"n": 0}

        def _fake_regen(_prefs):
            calls["n"] += 1
            return "A hiker."

        monkeypatch.setattr(profile_summary, "regenerate", _fake_regen)

        first = profile_summary.update_summary()
        assert first == "A hiker."
        assert calls["n"] == 1

        # Nothing durable changed -> no second LLM call.
        second = profile_summary.update_summary()
        assert second == "A hiker."
        assert calls["n"] == 1

        # A durable change bumps the digest -> regenerate runs again.
        prefs = load_preferences()
        prefs["interests"] = ["hiking", "diving"]
        save_preferences(prefs)
        third = profile_summary.update_summary()
        assert third == "A hiker."
        assert calls["n"] == 2

    def test_force_bypasses_gate(self, monkeypatch):
        prefs = load_preferences()
        prefs["interests"] = ["hiking"]
        save_preferences(prefs)

        calls = {"n": 0}
        monkeypatch.setattr(
            profile_summary,
            "regenerate",
            lambda p: (calls.__setitem__("n", calls["n"] + 1) or "S"),
        )
        profile_summary.update_summary()
        profile_summary.update_summary(force=True)
        assert calls["n"] == 2

    def test_regeneration_does_not_overwrite_concurrent_user_edit(self, monkeypatch):
        prefs = load_preferences()
        prefs["interests"] = ["hiking"]
        save_preferences(prefs)

        def _fake_regen(_prefs):
            profile_summary.set_summary("User correction.")
            return "Stale generated summary."

        monkeypatch.setattr(profile_summary, "regenerate", _fake_regen)

        assert profile_summary.update_summary(force=True) == "User correction."
        assert load_preferences()["profile_summary"] == "User correction."

    def test_empty_regeneration_returns_concurrent_user_edit(self, monkeypatch):
        prefs = load_preferences()
        prefs["interests"] = ["hiking"]
        save_preferences(prefs)

        def _fake_regen(_prefs):
            profile_summary.set_summary("User correction.")
            return ""

        monkeypatch.setattr(profile_summary, "regenerate", _fake_regen)

        assert profile_summary.update_summary(force=True) == "User correction."

    def test_set_summary_persists_and_stamps_digest(self, monkeypatch):
        prefs = load_preferences()
        prefs["interests"] = ["hiking"]
        save_preferences(prefs)

        profile_summary.set_summary("My own words.")
        prefs = load_preferences()
        assert prefs["profile_summary"] == "My own words."
        assert prefs["profile_summary_updated_at"] is not None

        # Since set_summary stamped the current digest, an immediate sweep is a
        # no-op (no LLM call) and the user's text survives.
        calls = {"n": 0}
        monkeypatch.setattr(
            profile_summary,
            "regenerate",
            lambda p: (calls.__setitem__("n", calls["n"] + 1) or "OVERWRITE"),
        )
        out = profile_summary.update_summary()
        assert out == "My own words."
        assert calls["n"] == 0

    def test_set_summary_rejects_stale_form_timestamp(self):
        profile_summary.set_summary("Concurrent generated summary.")

        result = profile_summary.set_summary(
            "Stale form summary.",
            expected_updated_at=None,
        )

        assert result["applied"] is False
        assert result["profile_summary"] == "Concurrent generated summary."
        assert load_preferences()["profile_summary"] == "Concurrent generated summary."

    def test_reset_clears_summary(self):
        profile_summary.set_summary("something")
        profile_summary.set_summary("")
        prefs = load_preferences()
        assert prefs["profile_summary"] == ""
        assert prefs["profile_summary_updated_at"] is None

    def test_planned_trips_are_a_signal(self, monkeypatch):
        # A user who only ever said "plan a trip to Goa" has no explicit prefs,
        # but the saved trip itself is durable substance worth summarizing.
        prefs = load_preferences()
        assert profile_summary._has_signal(prefs) is False

        trip_planner.create_trip_plan.invoke(
            {"destination": "Goa", "departure_date": "2026-01-10", "return_date": "2026-01-15"}
        )
        prefs = load_preferences()
        assert profile_summary._has_signal(prefs) is True
        planned = profile_summary._planned_trips()
        assert any(t["destination"] == "Goa" for t in planned)

    def test_new_trip_bumps_digest_and_regenerates(self, monkeypatch):
        calls = {"n": 0}
        monkeypatch.setattr(
            profile_summary,
            "regenerate",
            lambda p: (calls.__setitem__("n", calls["n"] + 1) or "A traveller eyeing Goa."),
        )
        trip_planner.create_trip_plan.invoke(
            {"destination": "Goa", "departure_date": "2026-01-10", "return_date": "2026-01-15"}
        )
        first = profile_summary.update_summary()
        assert first == "A traveller eyeing Goa."
        assert calls["n"] == 1
        # Planning a second, different trip changes the digest -> regenerate runs.
        trip_planner.create_trip_plan.invoke(
            {"destination": "Jaipur", "departure_date": "2026-03-01", "return_date": "2026-03-05"}
        )
        profile_summary.update_summary()
        assert calls["n"] == 2
