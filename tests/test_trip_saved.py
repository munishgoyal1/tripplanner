"""Ownership-focused tests split from the former tests/test_trip.py module."""

# ruff: noqa: E501, F403, F405, I001

from tests.support.trip import *  # noqa: F403

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
