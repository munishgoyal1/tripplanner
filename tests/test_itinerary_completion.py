from tripplanner.tools.trip_validation import _itinerary_time_errors


def test_chronology_rejection_reports_cascading_corrections_in_one_pass():
    stops = [
        {"name": "Temple", "kind": "attraction", "time": "09:00", "duration_min": 60},
        {"name": "Waterfront", "kind": "attraction", "time": "09:45", "duration_min": 60},
        {"name": "Lunch", "kind": "meal", "time": "11:00", "duration_min": 60},
    ]
    errors = _itinerary_time_errors([{"day": 3, "stops": stops}])
    assert len(errors) == 2
    assert "not before 10:30" in errors[0]
    assert "not before 12:00" in errors[1]
    stops[1]["time"] = "10:30"
    stops[2]["time"] = "12:00"
    assert _itinerary_time_errors([{"day": 3, "stops": stops}]) == []
