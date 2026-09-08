from __future__ import annotations

import pytest

from tripplanner import debug_store


@pytest.fixture(autouse=True)
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE_DIR", str(tmp_path / "debug-store"))
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "local")
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE", "1")
    return tmp_path


def make_plan(**overrides):
    plan = {
        "trip_id": "maui_2026-07-12_2026-07-17",
        "destination": "Maui",
        "departure_date": "2026-07-12",
        "return_date": "2026-07-17",
        "created_at": "2026-07-01T09:00:00",
        "updated_at": "2026-07-01T09:00:00",
        "status": "draft",
        "selected_hotels": [{"name": "Grand Wailea"}],
        "selected_activities": [{"name": "Road to Hana"}],
        "itinerary": [{"title": "Wailea Beach day", "stops": [{"place": "Wailea Beach"}]}],
    }
    plan.update(overrides)
    return plan


def test_nights_and_summary_read_like_a_person_would_say_it():
    plan = make_plan()
    assert debug_store.nights_between("2026-07-12", "2026-07-17") == 5
    summary = debug_store.summarize(plan)
    assert summary.startswith("5-night Maui")
    assert "Jul 2026" in summary


def test_keywords_include_nested_named_entities():
    keywords = [word.lower() for word in debug_store.collect_keywords(make_plan())]
    assert "grand wailea" in keywords
    assert "road to hana" in keywords
    assert "wailea beach" in keywords


def test_content_hash_ignores_volatile_fields_but_sees_real_change():
    base = make_plan()
    untouched = make_plan(updated_at="2026-07-02T10:00:00")
    changed = make_plan(selected_hotels=[{"name": "Four Seasons"}])
    assert debug_store.content_hash(base) == debug_store.content_hash(untouched)
    assert debug_store.content_hash(base) != debug_store.content_hash(changed)


def test_first_capture_numbers_from_one():
    path = debug_store.capture_trip(make_plan(), "google-123")
    assert path is not None
    record = debug_store.load_record(path)
    assert record["archive_no"] == 1
    assert record["trip_id"] == "maui_2026-07-12_2026-07-17"
    assert len(record["revisions"]) == 1


def test_resaving_identical_plan_adds_no_revision():
    debug_store.capture_trip(make_plan(), "google-123")
    path = debug_store.capture_trip(make_plan(updated_at="2026-07-02T11:00:00"), "google-123")
    record = debug_store.load_record(path)
    assert len(record["revisions"]) == 1
    assert len(debug_store.iter_records()) == 1


def test_resaving_identical_plan_does_not_rewrite_archive():
    path = debug_store.capture_trip(make_plan(), "google-123")
    original = path.read_bytes()

    debug_store.capture_trip(make_plan(updated_at="2026-07-02T11:00:00"), "google-123")

    assert path.read_bytes() == original


def test_meaningful_change_appends_a_revision_to_the_same_run():
    debug_store.capture_trip(make_plan(), "google-123")
    path = debug_store.capture_trip(
        make_plan(selected_hotels=[{"name": "Four Seasons"}]), "google-123"
    )
    record = debug_store.load_record(path)
    assert len(record["revisions"]) == 2
    assert len(debug_store.iter_records()) == 1
    assert record["descriptor"]["auto_summary"].startswith("5-night Maui")


def test_replanning_on_a_different_day_is_kept_as_a_separate_run():
    debug_store.capture_trip(make_plan(), "google-123")
    debug_store.capture_trip(make_plan(created_at="2026-07-20T08:00:00"), "google-123")
    records = sorted(record["archive_no"] for _, record in debug_store.iter_records())
    assert records == [1, 2]


def test_different_dates_are_a_different_trip():
    debug_store.capture_trip(make_plan(), "google-123")
    debug_store.capture_trip(
        make_plan(
            trip_id="maui_2026-09-01_2026-09-10",
            departure_date="2026-09-01",
            return_date="2026-09-10",
        ),
        "google-123",
    )
    assert len(debug_store.iter_records()) == 2


def test_users_are_partitioned_but_share_the_counter():
    debug_store.capture_trip(make_plan(), "google-123")
    path = debug_store.capture_trip(make_plan(), "web-guest")
    record = debug_store.load_record(path)
    assert record["archive_no"] == 2
    assert len(debug_store.iter_records()) == 2


def test_hosted_environment_never_archives(monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_ENVIRONMENT", "prod")
    assert debug_store.is_enabled() is False
    assert debug_store.capture_trip(make_plan(), "google-123") is None
    assert debug_store.iter_records() == []


def test_capture_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE", "0")
    assert debug_store.capture_trip(make_plan(), "google-123") is None


def test_record_trip_swallows_bad_input():
    debug_store.record_trip({"trip_id": object()}, "google-123")
    assert debug_store.iter_records() == []


def test_capture_attaches_an_offline_render_bundle():
    path = debug_store.capture_trip(make_plan(), "google-123")
    bundle = debug_store.load_record(path)["bundle"]
    assert set(bundle) == {"captured_at", "user_id", "chat", "preferences", "places"}
    assert bundle["user_id"] == "google-123"


def test_bundle_is_only_refreshed_when_a_revision_is_added():
    first = debug_store.capture_trip(make_plan(), "google-123")
    original = debug_store.load_record(first)["bundle"]["captured_at"]
    debug_store.capture_trip(make_plan(updated_at="2026-07-09T10:00:00"), "google-123")
    unchanged = debug_store.load_record(first)["bundle"]["captured_at"]
    assert unchanged == original


def test_referenced_places_keeps_only_this_trip_and_destination(monkeypatch):
    import time

    from tripplanner.web import places_cache

    now = time.time()
    cache = {
        "grand wailea|maui": {"rating": 4.8, "__at__": now},
        "some cafe|maui": {"rating": 4.1, "__at__": now},
        "eiffel tower|paris": {"rating": 4.7, "__at__": now},
    }
    monkeypatch.setattr(places_cache, "_CACHE", cache)
    found = debug_store.referenced_places(make_plan())
    assert "grand wailea|maui" in found
    assert "some cafe|maui" in found
    assert "eiffel tower|paris" not in found


def test_saving_a_real_trip_writes_through_to_the_archive(tmp_path, monkeypatch):
    """The capture hook must fire from the real trip save path, not just directly."""
    from tripplanner.tools import trip_history, trip_planner, user_preferences

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(user_preferences, "_PREFS_DIR", home)
    monkeypatch.setattr(user_preferences, "_PREFS_FILE", home / "preferences.json")
    monkeypatch.setattr(trip_planner, "_TRIPS_DIR", home)
    monkeypatch.setattr(trip_planner, "_ACTIVE_TRIP_FILE", home / "active_trip.json")
    monkeypatch.setattr(trip_planner, "_TRIP_HISTORY_DIR", home / "trips")
    monkeypatch.setattr(trip_history, "_TRIPS_DIR", home)
    monkeypatch.setattr(trip_history, "_ACTIVE_TRIP_FILE", home / "active_trip.json")
    monkeypatch.setattr(trip_history, "_TRIP_HISTORY_DIR", home / "trips")

    trip_planner.create_trip_plan.invoke(
        {
            "destination": "Maui",
            "departure_date": "2026-07-12",
            "return_date": "2026-07-17",
        }
    )

    records = debug_store.iter_records()
    assert len(records) == 1
    _, record = records[0]
    assert record["trip_id"] == "maui_2026-07-12_2026-07-17"
    assert record["descriptor"]["destination"] == "Maui"
    assert record["descriptor"]["nights"] == 5
    assert record["revisions"]
    assert set(record["bundle"]) == {"captured_at", "user_id", "chat", "preferences", "places"}


def test_reopening_an_unchanged_trip_elsewhere_does_not_restamp_it():
    plan = make_plan()
    bundle = {
        "captured_at": "2026-08-15T11:32:23Z",
        "user_id": "u",
        "chat": [],
        "preferences": {},
        "places": {},
    }
    first = {
        "at": "2026-08-15T11:32:23Z",
        "workspace": "sbx-7",
        "branch": "sandbox/7",
        "database": "d7",
    }
    record = debug_store.merge_revision({}, plan, first, bundle)
    revision_at = record["revisions"][-1]["at"]

    later = {
        "at": "2026-08-15T12:44:03Z",
        "workspace": "sbx-6",
        "branch": "sandbox/6",
        "database": "d6",
    }
    record = debug_store.merge_revision(
        record, plan, later, {**bundle, "captured_at": later["at"]}
    )

    assert record["revisions"][-1]["at"] == revision_at
    assert record["bundle"]["captured_at"] == "2026-08-15T11:32:23Z"
    assert len(record["revisions"]) == 1
    assert record["last_seen_at"] == later["at"]
    assert [entry["workspace"] for entry in record["seen_in"]] == ["sbx-7", "sbx-6"]


def test_a_real_edit_still_adds_a_stamped_revision():
    where = {"at": "2026-08-15T11:00:00Z", "workspace": "w", "branch": "b", "database": "d"}
    record = debug_store.merge_revision({}, make_plan(), where, None)
    later = {**where, "at": "2026-08-15T13:00:00Z"}
    record = debug_store.merge_revision(record, make_plan(destination="Kauai"), later, None)

    assert len(record["revisions"]) == 2
    assert record["revisions"][-1]["at"] == "2026-08-15T13:00:00Z"
