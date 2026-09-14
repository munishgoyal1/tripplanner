from tripplanner.tools import trip_guard
from tripplanner.web import itinerary_view, places_cache
from tripplanner.web.schedule import _enrich_stop_timing, _day_schedule


def test_saved_identity_wins_over_wrong_multicity_search(monkeypatch):
    calls = []
    monkeypatch.setattr(places_cache, "prefetch", lambda *a, **k: None)
    def lookup(name, city):
        calls.append((name, city))
        return (9.93, 78.13) if city == "Madurai" else (11.85, 78.13)
    monkeypatch.setattr(itinerary_view, "_place_coords", lookup)
    monkeypatch.setattr(places_cache, "get_details", lambda *a: {})
    day = {"stops": [
        {"name": "Hotel", "city": "Madurai", "lat": 9.94, "lng": 78.10},
        {"name": "Sree Sabarees", "city": "Madurai"},
    ]}
    coords = itinerary_view._itinerary_place_coords([day], [], [], "Madurai, Kanyakumari")
    assert coords["hotel"] == (9.94, 78.10)
    assert coords["sree sabarees"] == (9.93, 78.13)
    assert calls == [("Sree Sabarees", "Madurai")]


def test_generic_meal_does_not_acquire_an_unrelated_restaurant(monkeypatch):
    monkeypatch.setattr(places_cache, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(places_cache, "get_details", lambda *a: {"name": "Other city restaurant", "lat": 12, "lng": 78})
    monkeypatch.setattr(itinerary_view, "_place_coords", lambda *a: (12, 78))
    assert itinerary_view._itinerary_place_coords(
        [{"city": "Madurai", "stops": [{"name": "Dinner in Madurai", "kind": "meal"}]}], [], [], "Madurai"
    ) == {}


def test_drive_counted_once_and_checkin_time_included():
    stops = [
        {"name": "Drive: Kanyakumari to Madurai", "kind": "transport", "time": "08:25", "duration_min": 360},
        {"name": "Hotel", "kind": "hotel", "time": "14:25", "travel_from_previous": {"mode": "Drive", "duration_min": 360}},
        {"name": "Lunch", "kind": "meal", "time": "15:20", "duration_min": 60, "travel_from_previous": {"duration_min": 10}},
    ]
    _enrich_stop_timing(stops)
    assert stops[0]["departure_time"] == "08:25"
    assert stops[0]["arrival_time"] == "14:25"
    assert stops[1]["expected_arrival_time"] == "14:25"
    assert stops[2]["expected_arrival_time"] == "15:20"
    assert not any(s.get("timing_conflict_min") for s in stops)
    assert _day_schedule(stops, {"duration_min": 10})["travel_duration_min"] == 370


def test_delays_propagate_and_midnight_is_explicit_and_idempotent():
    stops = [
        {"kind": "meal", "time": "19:00", "duration_min": 60},
        {"kind": "attraction", "time": "20:30", "duration_min": 60, "travel_from_previous": {"duration_min": 367}},
        {"kind": "hotel", "time": "22:00", "travel_from_previous": {"duration_min": 20}},
    ]
    _enrich_stop_timing(stops)
    assert stops[1]["expected_arrival_time"] == "02:07 (+1 day)"
    assert stops[2]["expected_arrival_time"] == "03:27 (+1 day)"
    assert _day_schedule(stops, {"duration_min": 387})["end"] == "03:27 (+1 day)"
    stops[1]["travel_from_previous"]["duration_min"] = 10
    _enrich_stop_timing(stops)
    assert "timing_conflict_min" not in stops[2]


def test_guard_catches_saved_long_restaurant_detour_without_cache(monkeypatch):
    monkeypatch.setattr(trip_guard, "_summary_for_place", lambda *a: {})
    stops = [
        {"name": "Hotel", "kind": "hotel", "time": "12:00", "lat": 9.94, "lng": 78.10},
        {"name": "Sree Sabarees", "kind": "meal", "time": "13:00", "duration_min": 60, "lat": 11.85, "lng": 78.10},
        {"name": "Temple", "kind": "attraction", "time": "14:15", "lat": 9.94, "lng": 78.10},
    ]
    violations = trip_guard._feasibility_violations([(2, {}, stops)], "Madurai, Kanyakumari")
    assert len(violations) == 2
    assert all(v.code == "I4" for v in violations)


def test_unknown_coordinates_do_not_hide_overlapping_visits(monkeypatch):
    monkeypatch.setattr(trip_guard, "_summary_for_place", lambda *a: {})
    stops = [{"name": "A", "time": "12:00", "duration_min": 120}, {"name": "B", "time": "13:00"}]
    assert trip_guard._feasibility_violations([(1, {}, stops)], "Madurai")


def test_midday_hotel_rest_keeps_its_position_and_time():
    stops = [
        {"name": "Hotel", "kind": "hotel", "time": "08:00"},
        {"name": "Temple", "kind": "attraction", "time": "10:00"},
        {"name": "Hotel", "kind": "hotel", "time": "16:45"},
        {"name": "Dinner", "kind": "meal", "time": "19:30"},
    ]
    rendered = itinerary_view._wrap_day_in_stay(stops, {}, 2, "Hotel", [], [], "Madurai", "", {})
    assert rendered[:4] == stops
    assert rendered[-1]["kind"] == "hotel"
    assert rendered[-1]["time"] == ""
