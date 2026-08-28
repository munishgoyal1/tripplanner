"""The validation harness, tested without an emulator or a provider."""

from __future__ import annotations

import dataclasses
import http.client
import importlib.util
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from tripplanner.validation import (
    budget,
    corpus,
    findings,
    generate,
    india_heuristic_matrix,
    india_outbound_matrix,
    matrix,
    mutations,
    observations,
    quality,
    registry,
    render,
    runner,
)
from tripplanner.validation.catalog import Catalog
from tripplanner.validation.checks import check_record, plan_names
from tripplanner.validation.emulator import assert_generation_database, assert_sandbox_database
from tripplanner.validation.matrix import TripRequest

_PLACES = {
    "kempegowda international airport|paris": {"lat": 13.1986, "lng": 77.7066},
    "hotel lutetia|paris": {"lat": 48.8515, "lng": 2.3266},
}


def _plan(**extra: Any) -> dict[str, Any]:
    return {
        "trip_id": "paris_2026-09-06",
        "origin": "Bangalore",
        "destination": "Paris",
        "day_wise_itinerary": [
            {
                "day": 1,
                "stops": [
                    {
                        "name": "Kempegowda International Airport",
                        "kind": "transport",
                        "time": "05:00",
                    },
                    {"name": "Hotel Lutetia", "kind": "hotel", "time": "23:59"},
                ],
            }
        ],
        **extra,
    }


def _record(**extra: Any) -> corpus.CorpusRecord:
    return corpus.CorpusRecord(
        id="test:1", provenance=corpus.REAL, source="test", plan=_plan(**extra), places=_PLACES
    )


# ---- corpus ---------------------------------------------------------------


def test_a_trip_seen_from_two_sources_is_counted_once() -> None:
    same = [_record(), _record()]
    [logical] = corpus.deduplicate(same)
    assert len(logical.links) == 2
    assert logical.cohorts == (corpus.OWNER_CURRENT, corpus.CLONE)


def test_identity_and_lane_metadata_do_not_split_one_logical_trip() -> None:
    first = _record(user_id="owner", trip_id="owner-trip", revision=1)
    clone = dataclasses.replace(
        _record(user_id="corpus-copy", trip_id="lane-copy", revision=99),
        id="lane:copy",
        source="another-lane",
    )

    [logical] = corpus.deduplicate([first, clone])

    assert logical.logical_trip_id == first.logical_trip_id == clone.logical_trip_id
    assert {link.id for link in logical.links} == {"test:1", "lane:copy"}
    assert logical.cohorts == (corpus.GENERATED_FINAL, corpus.CLONE)


def test_a_meaningful_itinerary_revision_is_a_distinct_logical_trip() -> None:
    revised = _record(
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Kempegowda International Airport", "kind": "transport"},
                    {"name": "Eiffel Tower", "kind": "attraction"},
                ],
            }
        ]
    )

    assert len(corpus.deduplicate([_record(), revised])) == 2


def test_a_plan_without_an_itinerary_is_partial_not_current() -> None:
    partial = _record(day_wise_itinerary=[])

    assert partial.cohorts == (corpus.PARTIAL,)
    assert not partial.executive


def test_committed_generated_plans_retain_their_shared_place_facts(tmp_path: Path) -> None:
    directory = tmp_path / "trips"
    directory.mkdir()
    (directory / "paris.json").write_text(json.dumps(_plan()), encoding="utf-8")

    [generated] = corpus.from_generated_finals(directory, places=_PLACES)

    assert generated.cohorts == (corpus.GENERATED_FINAL,)
    assert generated.places == _PLACES


def test_provenance_is_tallied_for_the_report() -> None:
    records = [
        _record(),
        corpus.CorpusRecord(id="b", provenance=corpus.GOLDEN, source="s", plan=_plan()),
    ]
    assert corpus.counts_by_provenance(records) == {corpus.REAL: 1, corpus.GOLDEN: 1}


def test_debug_store_records_contribute_their_intermediate_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan is usually right when finished and wrong somewhere in the middle."""
    users = tmp_path / "users" / "owner"
    users.mkdir(parents=True)
    (users / "0001__paris.json").write_text(
        json.dumps(
            {
                "archive_no": 1,
                "trip_id": "paris",
                "revisions": [
                    {"plan": _plan(status="draft")},
                    {"plan": _plan(status="final")},
                ],
                "bundle": {"places": _PLACES},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRIPPLANNER_DEBUG_STORE_DIR", str(tmp_path))

    every = corpus.from_debug_store(tmp_path / "users")
    assert [item.provenance for item in every] == [corpus.REVISION, corpus.REAL]
    assert len(corpus.from_debug_store(tmp_path / "users", revisions=False)) == 1


# ---- isolation ------------------------------------------------------------


@pytest.mark.parametrize("name", ["tripplanner-prod", "tripplanner-canary", "tripplanner-local"])
def test_the_audit_cannot_read_a_database_that_is_not_a_sandbox(name: str) -> None:
    with pytest.raises(ValueError):
        assert_sandbox_database(name)


def test_generation_accepts_isolated_primary_and_sandbox_databases_only() -> None:
    assert assert_generation_database("tripplanner-local") == "tripplanner-local"
    assert assert_generation_database("tripplanner-sbx-4-test") == "tripplanner-sbx-4-test"
    for name in ("tripplanner-canary", "tripplanner-prod", "unscoped"):
        with pytest.raises(ValueError):
            assert_generation_database(name)


def test_a_fresh_generation_database_has_no_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    from azure.cosmos.exceptions import CosmosResourceNotFoundError

    from tripplanner.validation import emulator

    class MissingContainer:
        def query_items(self, **_kwargs: object) -> list[dict[str, Any]]:
            raise CosmosResourceNotFoundError(message="Collection 'trips' not found")

    class Database:
        def get_container_client(self, _name: str) -> MissingContainer:
            return MissingContainer()

    class Client:
        def get_database_client(self, _name: str) -> Database:
            return Database()

    monkeypatch.setattr(emulator, "_client", lambda: Client())

    assert emulator.read_generation_trips("tripplanner-sbx-fresh") == []


def test_generated_trip_acceptance_requires_two_stops_per_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thin = {"day_wise_itinerary": [{"day": 1, "stops": [{"name": "Fort"}]}]}
    rich = {
        "day_wise_itinerary": [
            {"day": 1, "stops": [{"name": "Fort"}, {"name": "Museum"}]},
            {"day": 2, "stops": [{"name": "Market"}, {"name": "Palace"}]},
        ]
    }
    monkeypatch.setattr(generate, "read_generation_trips", lambda *_args, **_kwargs: [thin])
    assert generate._saved_trip("tripplanner-sbx-test", "user") is None

    monkeypatch.setattr(generate, "read_generation_trips", lambda *_args, **_kwargs: [rich])
    assert generate._saved_trip("tripplanner-sbx-test", "user") == rich


# ---- checks ---------------------------------------------------------------


def test_a_stay_in_another_city_is_reported_without_a_provider() -> None:
    """AC-05 in miniature: the known Paris shape, found from stored facts alone."""
    reported = check_record(_record())

    assert any(finding.rule == "I9" for finding in reported)


def test_a_gap_that_only_repeats_a_violation_is_not_reported_twice() -> None:
    reported = check_record(_record())
    messages = {finding.message for finding in reported if finding.rule == "gap"}

    assert not any("Itinerary is not coherent" in message for message in messages)


def test_plan_names_gathers_every_proper_noun_the_symptom_must_lose() -> None:
    names = plan_names(_plan())

    assert "Paris" in names
    assert "Hotel Lutetia" in names


# ---- findings -------------------------------------------------------------


def test_the_same_shape_from_different_trips_is_one_group() -> None:
    names = ["Mandu Fort", "Rajwada Palace"]
    first = findings.Finding(
        "I9",
        findings.symptom_of("Mandu Fort is far from X on Day 3.", names),
        "m",
        "trip-a",
        corpus.REAL,
    )
    second = findings.Finding(
        "I9",
        findings.symptom_of("Rajwada Palace is far from X on Day 7.", names),
        "m",
        "trip-b",
        corpus.REAL,
    )

    grouped = findings.group([first, second])
    assert len(grouped) == 1
    assert grouped[0].count == 2


def test_only_findings_absent_from_the_baseline_are_new() -> None:
    finding = findings.Finding("I9", "shape", "message", "trip", corpus.REAL)
    grouped = findings.group([finding])

    assert findings.new_groups(grouped, {"accepted": {}}) == grouped
    assert findings.new_groups(grouped, findings.accept(grouped, {"accepted": {}})) == []


def test_accepting_twice_keeps_the_original_acceptance_date() -> None:
    grouped = findings.group([findings.Finding("I9", "shape", "message", "t", corpus.REAL)])
    first = findings.accept(grouped, {"accepted": {}})
    first["accepted"]["I9|shape"]["accepted_on"] = "2020-01-01"

    again = findings.accept(grouped, first)
    assert again["accepted"]["I9|shape"]["accepted_on"] == "2020-01-01"


def test_an_accepted_finding_that_stopped_occurring_is_offered_for_pruning() -> None:
    baseline = {"accepted": {"I9|gone": {}, "I4|still-here": {}}}
    grouped = findings.group([findings.Finding("I4", "still-here", "m", "t", corpus.REAL)])

    assert findings.stale_keys(grouped, baseline) == ["I9|gone"]


def test_a_saved_baseline_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "audit-baseline.json"
    grouped = findings.group([findings.Finding("I9", "shape", "message", "t", corpus.REAL)])
    findings.save_baseline(path, findings.accept(grouped, {"accepted": {}}))

    assert findings.new_groups(grouped, findings.load_baseline(path)) == []


# ---- runner ---------------------------------------------------------------


def test_the_audit_reports_the_corpus_it_actually_read(tmp_path: Path) -> None:
    result = runner.audit(
        tmp_path, records=[_record()], baseline={"accepted": {}}, render=False, mutate=False
    )

    assert result.corpus_size == 1
    assert result.provenance_mix == {corpus.REAL: 1}
    assert any(item.rule == "I9" for item in result.new)


# ---- render ---------------------------------------------------------------


def test_a_leg_drawn_as_ground_travel_across_a_continent_is_reported() -> None:
    record = _record()
    view = {
        "pins": [
            {"id": "airport", "name": "Kempegowda International Airport"},
            {"id": "hotel", "name": "Hotel Lutetia"},
        ],
        "days": [
            {
                "day": 1,
                "legs": [
                    {
                        "from_pin_id": "airport",
                        "to_pin_id": "hotel",
                        "mode": "Taxi",
                        "distance_km": 7700,
                        "duration_min": 16 * 60 + 1,
                    }
                ],
            }
        ],
    }

    reported = render._leg_findings(record, view, [])

    assert any(finding.rule == render.RULE_GROUND_LEG for finding in reported)
    assert any(finding.rule == render.RULE_LEG_DURATION for finding in reported)


def test_unresolved_shinkansen_does_not_draw_kyoto_meal_to_tokyo_airport_as_taxi() -> None:
    from tripplanner.web import trip_view

    plan = _plan(
        destination="Japan (Tokyo & Kyoto)",
        day_wise_itinerary=[
            {
                "day": 6,
                "stops": [
                    {
                        "name": "GYUKATSU Kyoto Katsugyu Teramachi Kyogoku",
                        "kind": "meal",
                    },
                    {"name": "Shinkansen: Kyoto to Tokyo", "kind": "transport"},
                    {"name": "Flight: Tokyo to Delhi", "kind": "flight"},
                ],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="tokyo-departure",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "gyukatsu kyoto katsugyu teramachi kyogoku|japan (tokyo & kyoto)": {
                "place_id": "kyoto-meal",
                "name": "GYUKATSU Kyoto Katsugyu Teramachi Kyogoku",
                "lat": 35.005,
                "lng": 135.768,
            },
            "tokyo airport|": {
                "place_id": "tokyo-airport",
                "name": "Tokyo Airport",
                "lat": 35.549,
                "lng": 139.779,
            },
        },
    )

    reported = render.check_render(record)
    with render.render_facts(record.places):
        view = trip_view.build_map_view(record.plan)
    pins = {str(pin["id"]): pin for pin in view["pins"]}
    circuit_names = [pins[pin_id]["name"] for pin_id in view["days"][0]["circuit_pin_ids"]]

    assert not any(finding.rule == render.RULE_GROUND_LEG for finding in reported)
    assert circuit_names == ["Tokyo Airport"]


def test_an_unresolved_flight_endpoint_is_not_drawn_as_ground_travel() -> None:
    plan = _plan(
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Flight: Bangalore to Paris", "kind": "flight"},
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                ],
            }
        ]
    )
    record = corpus.CorpusRecord(
        id="unresolved-flight",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            **_PLACES,
            "bangalore airport|": {"lat": 13.1986, "lng": 77.7066},
        },
    )

    reported = render.check_render(record)

    assert not any(finding.rule == render.RULE_GROUND_LEG for finding in reported)


def test_render_does_not_bind_an_unresolved_flight_to_the_next_local_pin() -> None:
    plan = _plan(
        destination="Goa",
        day_wise_itinerary=[
            {
                "day": 1,
                "city": "Goa",
                "stops": [
                    {"name": "Basilica of Bom Jesus", "kind": "attraction"},
                    {"name": "Flight to an unresolved airport", "kind": "flight"},
                    {"name": "Se Cathedral", "kind": "attraction"},
                ],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="partial-flight",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "basilica of bom jesus|goa": {"lat": 15.5009, "lng": 73.9116},
            "se cathedral|goa": {"lat": 15.5036, "lng": 73.9122},
        },
    )

    reported = render.check_render(record)

    assert not any(finding.rule == render.RULE_EMPTY_LEG for finding in reported)


def test_render_does_not_draw_a_departure_flight_as_an_all_day_local_leg() -> None:
    plan = _plan(
        destination="Bhutan",
        day_wise_itinerary=[
            {
                "day": 5,
                "stops": [
                    {"name": "Hotel in Paro", "kind": "hotel", "time": "07:00"},
                    {
                        "name": "Paro Town Walk",
                        "kind": "attraction",
                        "time": "08:00",
                        "duration_min": 60,
                    },
                    {
                        "name": "Flight: Paro to Delhi",
                        "kind": "flight",
                        "time": "11:00",
                        "duration_min": 180,
                    },
                ],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="bhutan-departure",
        provenance=corpus.SYNTHETIC,
        source="test",
        plan=plan,
        places={
            "hotel in paro|bhutan": {
                "place_id": "paro-hotel",
                "name": "Hotel in Paro",
                "lat": 27.43,
                "lng": 89.42,
            },
            "paro town walk|bhutan": {
                "place_id": "paro-walk",
                "name": "Paro Town Walk",
                "lat": 27.43,
                "lng": 89.41,
            },
            "delhi airport|": {
                "place_id": "delhi-airport",
                "name": "Delhi Airport",
                "lat": 28.56,
                "lng": 77.10,
            },
        },
    )

    reported = render.check_render(record)

    assert not any(finding.rule == render.RULE_LEG_DURATION for finding in reported)


def test_render_does_not_route_a_post_checkout_home_day_from_the_expired_stay() -> None:
    plan = _plan(
        destination="Varanasi and Ayodhya",
        selected_hotels=[
            {
                "name": "Clarks Inn Express Ayodhya",
                "city": "Ayodhya",
                "checkin": "2027-02-05",
                "checkout": "2027-02-07",
            }
        ],
        day_wise_itinerary=[
            {
                "day": 6,
                "date": "2027-02-08",
                "title": "Arrival in Pune",
                "stops": [{"name": "Pune", "kind": "other", "note": "Trip ends"}],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="post-checkout-home",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "clarks inn express ayodhya|ayodhya": {
                "place_id": "ayodhya-hotel",
                "name": "Clarks Inn Express Ayodhya",
                "lat": 26.79,
                "lng": 82.20,
            },
            "pune|varanasi and ayodhya": {
                "place_id": "pune",
                "name": "Pune",
                "lat": 18.52,
                "lng": 73.86,
            },
        },
    )

    reported = render.check_render(record)

    assert not any(finding.rule == render.RULE_LEG_DURATION for finding in reported)


def test_render_does_not_reuse_a_duplicate_brand_from_another_city() -> None:
    plan = _plan(
        destination="Kaziranga",
        day_wise_itinerary=[
            {
                "day": 1,
                "city": "Kaziranga",
                "stops": [
                    {"name": "Drive: Kaziranga to Kohora", "kind": "transport"},
                    {"name": "Dosa Plaza", "kind": "restaurant"},
                ],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="duplicate-brand",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "kaziranga|": {"lat": 26.5775, "lng": 93.1711},
            "dosa plaza|bengaluru": {
                "place_id": "bengaluru-dosa-plaza",
                "name": "Dosa Plaza",
                "address": "Bengaluru, Karnataka",
                "lat": 12.9716,
                "lng": 77.5946,
            },
        },
    )

    reported = render.check_render(record)

    assert not any(
        finding.rule in {render.RULE_GROUND_LEG, render.RULE_LEG_DURATION} for finding in reported
    )


def test_render_name_fallback_requires_destination_compatible_identity() -> None:
    get_details = render._lookup(
        {
            "museum cafe|old goa": {
                "place_id": "goa-cafe",
                "name": "Museum Cafe",
                "address": "Old Goa, Goa",
            },
            "dosa plaza|bengaluru": {
                "place_id": "bengaluru-dosa-plaza",
                "name": "Dosa Plaza",
                "address": "Bengaluru, Karnataka",
            },
        }
    )

    assert get_details("Museum Cafe", "Goa")["place_id"] == "goa-cafe"
    assert get_details("Dosa Plaza", "Kaziranga") is None


def test_render_ignores_wrong_provider_identity_for_context_free_drive_endpoint() -> None:
    plan = _plan(
        destination="Guwahati and Kaziranga",
        day_wise_itinerary=[
            {
                "day": 3,
                "title": "Transfer to Kaziranga",
                "stops": [
                    {"name": "Drive: Guwahati to Kaziranga", "kind": "transport"},
                    {"name": "IORA - The Retreat, Kaziranga", "kind": "hotel"},
                ],
            }
        ],
    )
    record = corpus.CorpusRecord(
        id="wrong-drive-endpoint",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "guwahati|kaziranga": {
                "place_id": "kaziranga-national-park",
                "name": "Kaziranga National Park",
                "lat": 26.6445,
                "lng": 93.3525,
            },
            "iora - the retreat, kaziranga|kaziranga": {
                "place_id": "iora",
                "name": "IORA - The Retreat, Kaziranga",
                "lat": 26.5775,
                "lng": 93.1711,
            },
        },
    )

    reported = render.check_render(record)

    assert not any(
        finding.rule == render.RULE_UNMAPPED and "Guwahati" in finding.message
        for finding in reported
    )


def test_render_checks_stay_silent_without_the_facts_to_measure_with() -> None:
    blind = corpus.CorpusRecord(id="x", provenance=corpus.REAL, source="s", plan=_plan())

    assert render.check_render(blind) == []


def test_a_stop_missing_from_the_stored_facts_is_not_called_unmapped() -> None:
    """The audit's own blind spot must not be reported as the product's defect."""
    view = {"unmapped_stops": [{"name": "Somewhere Uncached", "day": 1, "reason": "no_location"}]}

    assert render._unmapped_findings(_record(), view, []) == []


def test_a_coordinate_less_stored_fact_is_not_called_unmapped() -> None:
    view = {"unmapped_stops": [{"name": "Bodh Gaya", "day": 3, "reason": "no_location"}]}
    record = dataclasses.replace(
        _record(),
        places={
            "bodh gaya|bodh gaya, nalanda, rajgir": {
                "name": "Bodh Gaya",
                "place_id": "bodh-gaya",
            }
        },
    )

    assert render._unmapped_findings(record, view, []) == []


def test_a_located_stored_fact_that_failed_to_map_is_reported() -> None:
    view = {"unmapped_stops": [{"name": "Hotel Lutetia", "day": 1, "reason": "no_location"}]}

    reported = render._unmapped_findings(_record(), view, [])

    assert [finding.rule for finding in reported] == [render.RULE_UNMAPPED]


def test_a_place_the_provider_swapped_for_another_is_reported() -> None:
    view = {"unmapped_stops": [{"name": "Seine River Cruise", "day": 2, "reason": "no_match"}]}

    reported = render._unmapped_findings(_record(), view, [])
    assert [finding.rule for finding in reported] == [render.RULE_UNMAPPED]


def test_a_generic_activity_with_an_explicit_map_explanation_is_not_reported() -> None:
    view = {
        "unmapped_stops": [
            {"name": "Scuba Diving Centre", "day": 5, "reason": "not_a_place"}
        ]
    }

    assert render._unmapped_findings(_record(), view, []) == []


# ---- metamorphic ----------------------------------------------------------


def test_every_mutation_is_offered_in_a_fixed_order() -> None:
    plan = _plan()

    assert [item.name for item in mutations.mutations_of(plan)] == [
        item.name for item in mutations.mutations_of(plan)
    ]


def test_a_mutation_never_edits_the_plan_it_was_given() -> None:
    plan = _plan()
    before = json.dumps(plan, sort_keys=True)

    mutations.mutations_of(plan)
    assert json.dumps(plan, sort_keys=True) == before


def test_blanking_an_origin_that_is_already_missing_is_not_a_mutation() -> None:
    assert mutations.blank_origin(_plan(origin="")) is None


def test_break_time_order_introduces_a_new_chronology_defect() -> None:
    plan = _plan(
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Origin station", "kind": "transport", "time": "07:00"},
                    {"name": "Outbound train", "kind": "transport", "time": "07:30"},
                    {"name": "Destination station", "kind": "transport", "time": "17:30"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Hotel", "kind": "hotel", "time": "07:00"},
                    {"name": "Museum", "kind": "attraction", "time": "08:00"},
                    {"name": "Market", "kind": "attraction", "time": "12:00"},
                    {"name": "Hotel", "kind": "hotel", "time": "15:00"},
                ],
            },
        ]
    )

    mutation = mutations.break_time_order(plan)

    assert mutation is not None
    assert mutation.plan["day_wise_itinerary"][0] == plan["day_wise_itinerary"][0]
    assert mutation.plan["day_wise_itinerary"][1]["stops"][-1]["time"] == "00:05"


def test_reverse_days_keeps_each_days_findings_attached_to_its_evidence() -> None:
    plan = _plan(
        destination="New York",
        departure_date="2027-10-11",
        day_wise_itinerary=[
            {
                "day": 1,
                "date": "2027-10-11",
                "title": "Arrival",
                "stops": [{"name": "Hotel", "kind": "hotel"}],
            },
            {
                "day": 2,
                "date": "2027-10-12",
                "title": "Museum day",
                "stops": [
                    {"name": "Closed Museum", "kind": "attraction", "time": "10:00"},
                    {"name": "Central Park", "kind": "attraction", "time": "14:00"},
                ],
            },
            {
                "day": 3,
                "date": "2027-10-13",
                "title": "Market day",
                "stops": [{"name": "Market", "kind": "attraction", "time": "10:00"}],
            },
            {
                "day": 4,
                "date": "2027-10-14",
                "title": "Departure",
                "stops": [{"name": "Hotel", "kind": "hotel"}],
            },
        ],
    )
    record = corpus.CorpusRecord(
        id="new-york",
        provenance=corpus.REAL,
        source="test",
        plan=plan,
        places={
            "closed museum|new york": {
                "name": "Closed Museum",
                "lat": 40.0,
                "lng": -74.0,
                "weekday_descriptions": ["Tuesday: Closed"],
            }
        },
    )

    mutation = mutations.reverse_days(plan)

    assert mutation is not None
    assert [day["day"] for day in mutation.plan["day_wise_itinerary"]] == [4, 3, 2, 1]
    assert mutation.plan["day_wise_itinerary"][2] == plan["day_wise_itinerary"][1]
    before = {finding.key for finding in check_record(record)}
    after = {
        finding.key
        for finding in check_record(dataclasses.replace(record, plan=mutation.plan))
    }
    assert any(key.startswith("I11|") for key in before)
    assert before <= after
    assert not [
        finding
        for finding in mutations.check_metamorphic(record)
        if finding.rule == mutations.RULE_QUIETER and "reverse-days" in finding.message
    ]


def test_drop_first_leg_is_not_unnoticed_without_hotel_rows() -> None:
    record = _record(
        destination="Spiti Valley",
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Drive: Bangalore to Narkanda", "kind": "transport"},
                    {"name": "Local Restaurant, Narkanda", "kind": "meal"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Drive: Narkanda to Bangalore", "kind": "transport"},
                ],
            },
        ],
    )

    assert not [
        finding
        for finding in mutations.check_metamorphic(record)
        if finding.rule == mutations.RULE_UNNOTICED and "drop-first-leg" in finding.message
    ]


def test_drop_last_leg_skips_terminal_markers_and_removes_the_journey() -> None:
    record = _record(
        origin="Guwahati",
        destination="Meghalaya",
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Drive: Guwahati to Shillong", "kind": "transport"},
                    {"name": "Hotel in Shillong", "kind": "hotel"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Hotel in Cherrapunji", "kind": "hotel"},
                    {"name": "Drive: Cherrapunji to Guwahati", "kind": "transport"},
                    {"name": "Guwahati Airport", "kind": "transport"},
                ],
            },
        ],
    )

    mutation = mutations.drop_last_leg(record.plan)

    assert mutation is not None
    assert [stop["name"] for stop in mutation.plan["day_wise_itinerary"][-1]["stops"]] == [
        "Hotel in Cherrapunji",
        "Guwahati Airport",
    ]
    assert not [
        finding
        for finding in mutations.check_metamorphic(record)
        if finding.rule == mutations.RULE_UNNOTICED and "drop-last-leg" in finding.message
    ]


def test_drop_last_leg_skips_redundant_homebound_routes() -> None:
    plan = _plan(
        day_wise_itinerary=[
            {
                "day": 1,
                "stops": [
                    {"name": "Flight: Bangalore to Paris", "kind": "flight"},
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                ],
            },
            {
                "day": 2,
                "stops": [
                    {"name": "Hotel Lutetia", "kind": "hotel"},
                    {"name": "Flight: Paris to Bangalore", "kind": "flight"},
                    {"name": "Flight: CDG to Bangalore", "kind": "flight"},
                ],
            },
        ]
    )

    assert mutations.drop_last_leg(plan) is None


def test_an_edit_that_changes_nothing_must_change_no_finding() -> None:
    record = _record()
    for mutation in mutations.mutations_of(record.plan):
        if mutation.kind != mutations.NEUTRAL:
            continue
        mutated = dataclasses.replace(record, plan=mutation.plan)
        assert {f.key for f in check_record(mutated)} == {f.key for f in check_record(record)}


def test_a_guard_that_stops_running_is_caught_by_the_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07: silence the origin guards and losing the origin goes unnoticed.

    Two rules cover a missing origin today, so both have to go before the hole
    opens -- which is itself the evidence that the coverage is real.
    """
    from tripplanner.tools import trip_guard, trip_validation

    record = _record()
    assert not [
        finding
        for finding in mutations.check_metamorphic(record)
        if finding.rule == mutations.RULE_UNNOTICED
    ]

    monkeypatch.setattr(trip_guard, "_coverage_violations", lambda plan: [])
    monkeypatch.setattr(trip_validation, "_round_trip_transport_warnings", lambda plan: [])

    blinded = mutations.check_metamorphic(record)
    assert [f.rule for f in blinded if "blank-origin" in f.message] == [mutations.RULE_UNNOTICED]


# ---- registry -------------------------------------------------------------


def test_every_rule_the_harness_can_report_is_described_in_the_registry() -> None:
    """A new rule cannot arrive without a sentence explaining what it means."""
    record = _record()
    emitted = {
        finding.rule
        for finding in [
            *check_record(record),
            *render.check_render(record),
            *mutations.check_metamorphic(record),
        ]
    }

    assert emitted
    assert emitted <= registry.codes()


def test_every_code_the_guard_names_is_registered() -> None:
    """The fixture above only proves what happened to fire on one trip.

    I11 and I13 shipped, fired on the real corpus, and stayed absent from the
    registry because no synthetic record triggered them. Assert over the code
    sets the system declares instead, which no choice of fixture can dodge.
    """
    from tripplanner.tools import trip_guard
    from tripplanner.web import trip_verification

    declared = (
        set(trip_guard.KNOWN_FACT_CODES)
        | set(trip_verification.CONTRADICTION_CODES)
        | set(trip_verification.ADVISORY_CODES)
        | set(trip_verification.COVERAGE_CODES)
        | set(trip_verification._REQUIREMENTS)
    )

    assert declared <= registry.codes()


def test_a_rule_states_itself_and_declares_how_hard_it_bites() -> None:
    for rule in registry.registry():
        assert rule.statement.strip().endswith(".")
        assert rule.severity in {registry.GATE, registry.REPORT, registry.OBSERVE}
        assert rule.evaluated_in.startswith("tripplanner.")


def test_the_gate_severity_follows_the_completion_gate_itself() -> None:
    from tripplanner.tools.trip_validation import _COHERENCE_CODES

    gated = {rule.code for rule in registry.registry() if rule.severity == registry.GATE}
    assert set(_COHERENCE_CODES) <= gated


def test_fidelity_and_requested_budget_evidence_are_registered_as_gates() -> None:
    rules = {rule.code: rule for rule in registry.registry()}

    assert rules["QG1"].severity == registry.GATE
    assert rules["QG2"].severity == registry.GATE


def test_an_explicit_quality_gate_failure_is_an_audit_finding(tmp_path: Path) -> None:
    ratings = quality.empty_ratings()
    ratings["ratings"]["test:1"] = {
        "hard_gates": {
            "scenario_preference_fidelity": {
                "outcome": "fail",
                "evidence": "The Jain request was not carried into meal choices.",
            }
        }
    }

    result = runner.audit(
        tmp_path,
        records=[_record()],
        baseline={"accepted": {}},
        render=False,
        mutate=False,
        quality_ratings=ratings,
    )

    assert any(finding.rule == "QG1" for finding in result.findings)


# ---- observations ---------------------------------------------------------


def test_observations_describe_the_corpus_without_judging_it() -> None:
    described = observations.observe([_record()])
    labels = {item.label for item in described}

    assert "Trips" in labels
    assert "Days with a named meal" in labels
    # An observation is never a finding: it carries no rule to violate.
    assert all(not hasattr(item, "rule") for item in described)


def test_an_empty_corpus_describes_itself_without_dividing_by_zero() -> None:
    described = observations.observe([])

    assert any(item.label == "Trips" and item.value == "0" for item in described)


def test_taste_scores_stay_informational_even_with_a_reference_rating() -> None:
    ratings = quality.empty_ratings()
    ratings["ratings"]["test:1"] = {
        "reference": True,
        "taste": {
            dimension.key: {"score": 4, "evidence": "Owner review"}
            for dimension in quality.TASTE_DIMENSIONS
        },
    }

    summary = quality.report([_record()], ratings)

    assert summary["reference_cohort"]["size"] == 1
    assert summary["reference_cohort"]["owner_approved"] is False
    assert summary["subjective_regression_gates_enabled"] is False
    assert all(item["regression_gate"] is False for item in summary["taste_dimensions"])


# ---- budget ---------------------------------------------------------------


def test_a_first_run_may_spend_the_default_and_no_more(tmp_path: Path) -> None:
    allowed = budget.authorize(tmp_path)

    assert allowed.budget_inr == budget.DEFAULT_RUN_BUDGET_INR
    assert allowed.spent_inr == 0.0
    assert allowed.remaining_inr == budget.CUMULATIVE_CAP_INR


def test_what_was_already_spent_is_remembered_between_runs(tmp_path: Path) -> None:
    budget.record(
        tmp_path, spent_inr_amount=900, trips=12, model="gpt-4.1", stopped_because="budget"
    )
    budget.record(
        tmp_path, spent_inr_amount=600, trips=8, model="gpt-4.1", stopped_because="target"
    )

    assert budget.spent_inr(tmp_path) == 1500.0
    assert budget.authorize(tmp_path).spent_inr == 1500.0


def test_a_run_is_clamped_to_the_headroom_the_cap_leaves(tmp_path: Path) -> None:
    budget.record(
        tmp_path,
        spent_inr_amount=budget.CUMULATIVE_CAP_INR - 300,
        trips=60,
        model="gpt-4.1",
        stopped_because="budget",
    )

    assert budget.authorize(tmp_path).budget_inr == 300.0


def test_the_cumulative_cap_refuses_a_further_run(tmp_path: Path) -> None:
    budget.record(
        tmp_path,
        spent_inr_amount=budget.CUMULATIVE_CAP_INR,
        trips=64,
        model="gpt-4.1",
        stopped_because="budget",
    )

    with pytest.raises(budget.BudgetExhaustedError):
        budget.authorize(tmp_path)


def test_an_unreadable_ledger_never_reads_as_nothing_spent(tmp_path: Path) -> None:
    budget.ledger_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    budget.ledger_path(tmp_path).write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(budget.BudgetExhaustedError):
        budget.authorize(tmp_path)


def test_the_conversion_rate_is_recorded_with_every_run(tmp_path: Path) -> None:
    entry = budget.record(
        tmp_path, spent_inr_amount=10, trips=1, model="gpt-4.1", stopped_because="target"
    )

    assert entry["usd_inr"] > 0
    assert entry["model"] == "gpt-4.1"


def test_the_audit_never_reaches_for_a_provider_even_without_facts() -> None:
    """A record with no cached places must not send the audit to the network.

    Leaving the real lookup in place made an offline audit hang on live Places
    calls, which is both slow and billable.
    """
    from tripplanner.tools import trip_common
    from tripplanner.validation.checks import place_facts

    called: list[str] = []

    def provider(name: str, city: str = "", **_kwargs: Any) -> dict[str, Any]:
        called.append(name)
        return {}

    original = trip_common._summary_for_place
    trip_common._summary_for_place = provider
    try:
        with place_facts({}):
            trip_common._summary_for_place("Eiffel Tower", "Paris")
    finally:
        trip_common._summary_for_place = original

    assert called == []


# ---- report ---------------------------------------------------------------


def _audit_of(*records: corpus.CorpusRecord, tmp_path: Path) -> runner.AuditResult:
    return runner.audit(tmp_path, records=list(records), baseline={"accepted": {}})


def test_every_reported_finding_names_a_record_that_is_in_the_corpus(tmp_path: Path) -> None:
    """A finding that cannot be traced back to a trip cannot be opened."""
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    payload = report_module.build_report(result, {"accepted": {}})

    known = {item["id"] for item in payload["records"]}
    assert payload["groups"]
    for item in payload["groups"]:
        assert item["findings"]
        for finding in item["findings"]:
            assert finding["record_id"] in known


def test_a_rule_that_never_fired_is_still_listed(tmp_path: Path) -> None:
    """Absence from the report would read as "no such rule" instead of "no hits"."""
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    payload = report_module.build_report(result, {"accepted": {}})

    listed = {item["code"] for item in payload["rules"]}
    assert listed == registry.codes()
    assert any(item["hits"] == 0 for item in payload["rules"])


def test_rules_distinguish_failed_clean_and_absent_facts(tmp_path: Path) -> None:
    from tripplanner.validation import report as report_module

    grounded = _record()
    absent = dataclasses.replace(
        _record(user_id="other"),
        id="test:without-facts",
        plan=_plan(
            user_id="other",
            day_wise_itinerary=[
                {"day": 1, "stops": [{"name": "Eiffel Tower", "kind": "attraction"}]}
            ],
        ),
        places={},
    )
    partial = dataclasses.replace(
        _record(day_wise_itinerary=[]),
        id="test:partial",
        plan=_plan(day_wise_itinerary=[]),
    )
    result = _audit_of(grounded, absent, partial, tmp_path=tmp_path)

    payload = report_module.build_report(result, {"accepted": {}})
    render_rule = next(item for item in payload["rules"] if item["code"] == "R1")

    assert payload["corpus"]["executive_size"] == 2
    assert payload["corpus"]["cohorts"][corpus.PARTIAL] == 1
    assert render_rule["eligible"] == 2
    assert render_rule["evaluated"] == 1
    assert render_rule["unverified"] == 1
    assert render_rule["failed"] <= render_rule["evaluated"]
    assert render_rule["by_cohort"][corpus.PARTIAL]["eligible"] == 0


def test_a_rule_counts_the_trips_it_touches_not_just_the_times_it_fired(
    tmp_path: Path,
) -> None:
    """One trip repeating a mistake daily is not every trip making it once."""
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    payload = report_module.build_report(result, {"accepted": {}})

    fired = [item for item in payload["rules"] if item["hits"]]
    assert fired, "the fixture is expected to trip at least one rule"
    for item in fired:
        assert 1 <= item["trips"] <= payload["corpus"]["size"]
        assert item["trips"] <= item["hits"]


def test_a_rule_reports_how_far_it_moved_since_the_previous_audit(
    tmp_path: Path,
) -> None:
    """A count with nothing to compare against cannot show whether work helped."""
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    first = report_module.build_report(result, {"accepted": {}})
    assert all(item["first_seen"] for item in first["rules"])
    assert first["compared_with"] == ""

    second = report_module.build_report(result, {"accepted": {}}, first)

    assert second["compared_with"] == first["generated_at"]
    by_code = {item["code"]: item for item in first["rules"]}
    for item in second["rules"]:
        assert not item["first_seen"]
        assert item["was_trips"] == by_code[item["code"]]["trips"]
        assert item["was_hits"] == by_code[item["code"]]["hits"]


def test_reports_with_the_same_corpus_and_rules_are_comparable(tmp_path: Path) -> None:
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    first = report_module.build_report(result, {"accepted": {}})
    second = report_module.build_report(result, {"accepted": {}}, first)

    assert first["comparison"]["status"] == "not_comparable"
    assert second["comparison"]["status"] == "comparable"
    assert second["comparison"]["new_groups"] == []
    assert second["comparison"]["resolved_groups"] == []
    assert second["comparison"]["worsened_rules"] == []


def test_saving_a_report_keeps_immutable_history_and_latest_pointer(tmp_path: Path) -> None:
    from tripplanner.validation import report as report_module

    payload = report_module.build_report(_audit_of(_record(), tmp_path=tmp_path), {"accepted": {}})
    history_path = report_module.save_report(tmp_path, payload)

    assert history_path.parent.name == payload["run_id"]
    assert history_path.name == "report.json"
    assert json.loads(history_path.read_text(encoding="utf-8"))["run_id"] == payload["run_id"]
    assert (history_path.parent / "summary.md").exists()
    latest = json.loads((tmp_path / "audit" / "latest.json").read_text())
    assert latest["run_id"] == payload["run_id"]
    [indexed] = json.loads((tmp_path / "audit" / "index.json").read_text())["runs"]
    assert indexed["run_id"] == payload["run_id"]
    assert payload["version"] == 4
    assert payload["evidence"]["fresh_generation"]["status"] == "not_run"


def test_generation_evidence_separates_old_trips_from_commit_attributed_runs() -> None:
    from tripplanner.validation import report as report_module

    evidence = report_module.generation_evidence(
        {
            "produced": [
                {"slug": "old"},
                {"slug": "new-a", "generated_by_commit": "abc", "generation_run_id": "run-1"},
                {"slug": "new-b", "generated_by_commit": "abc", "generation_run_id": "run-1"},
            ]
        }
    )

    assert evidence == {
        "trips": 3,
        "by_commit": {"abc": 2},
        "by_run": {"run-1": 2},
        "unattributed_pre_provenance": 1,
    }


def test_a_rule_added_after_the_last_audit_reads_as_new_not_as_a_regression(
    tmp_path: Path,
) -> None:
    """Without this, every new rule would look like quality suddenly got worse."""
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    previous = report_module.build_report(result, {"accepted": {}})
    previous["rules"] = [item for item in previous["rules"] if item["code"] != "R1"]

    payload = report_module.build_report(result, {"accepted": {}}, previous)

    fresh = next(item for item in payload["rules"] if item["code"] == "R1")
    assert fresh["first_seen"]
    assert fresh["was_trips"] == 0


def test_a_record_without_a_stored_identity_is_not_offered_as_openable(
    tmp_path: Path,
) -> None:
    """Debug-store revisions never existed in a database, so nothing can load them."""
    from tripplanner.validation import report as report_module

    stored = corpus.CorpusRecord(
        id="db:trip-1",
        provenance=corpus.REAL,
        source="tripplanner-sbx-2-auto-validation",
        plan=_plan(user_id="corpus-hampi", trip_id="hampi_2027-01-05"),
        places=_PLACES,
    )
    result = _audit_of(_record(), stored, tmp_path=tmp_path)
    payload = report_module.build_report(result, {"accepted": {}})

    by_id = {item["id"]: item for item in payload["records"]}
    assert by_id["db:trip-1"]["openable"] is True
    assert by_id["db:trip-1"]["user_id"] == "corpus-hampi"
    assert by_id["test:1"]["openable"] is False


def test_an_accepted_group_carries_the_date_it_was_accepted(tmp_path: Path) -> None:
    from tripplanner.validation import report as report_module

    result = _audit_of(_record(), tmp_path=tmp_path)
    key = result.groups[0].key
    baseline = {"accepted": {key: {"accepted_on": "2026-08-01"}}}

    payload = report_module.build_report(
        runner.audit(tmp_path, records=result.records, baseline=baseline), baseline
    )

    accepted = {item["key"]: item for item in payload["groups"]}[key]
    assert accepted["new"] is False
    assert accepted["accepted_on"] == "2026-08-01"


_ONE_REQUEST = (TripRequest("corpus-slug", "a shape", "Plan a trip"),)


def test_paid_corpus_generation_defaults_to_one_turn_at_a_time() -> None:
    assert generate.DEFAULT_WORKERS == 1


def _stub_generate(monkeypatch: pytest.MonkeyPatch, usage: dict[str, Any]) -> None:
    monkeypatch.setattr(generate, "assert_generation_database", lambda name: name)
    monkeypatch.setattr(generate, "_saved_trip", lambda database, user_id: None)
    monkeypatch.setattr(generate, "_usage_for", lambda database, user_id: dict(usage))


def test_a_repeated_attempt_never_reuses_its_request_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reusing one id lets the API replay the first turn, so a failed slug can never recover."""
    seen: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: seen.append(request_id),
    )

    for _ in range(2):
        generate.build(
            tmp_path,
            database="tripplanner-sbx-test",
            api="http://127.0.0.1:0",
            target=1,
            requests=_ONE_REQUEST,
        )

    assert len(seen) == len(set(seen))


def test_a_repeated_attempt_never_reuses_failed_principal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed slug's empty trip and interrupted chat must not poison its next run."""
    seen: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: seen.append(user_id),
    )

    for _ in range(2):
        generate.build(
            tmp_path,
            database="tripplanner-sbx-test",
            api="http://127.0.0.1:0",
            target=1,
            requests=_ONE_REQUEST,
        )

    assert len(seen) == 4
    assert len(set(seen)) == 2
    assert all(user_id.startswith("corpus-corpus-slug-") for user_id in seen)


def test_an_empty_first_turn_gets_one_bounded_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str]] = []
    saved = iter(
        (
            None,
            {
                "id": "recovered-trip",
                "day_wise_itinerary": [
                    {"day": 1, "stops": [{"name": "Amber Fort"}]}
                ],
            },
        )
    )
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: asked.append(
            (message, user_id, request_id)
        ),
    )
    monkeypatch.setattr(generate, "_saved_trip", lambda database, user_id: next(saved))

    result = generate._attempt(
        _ONE_REQUEST[0],
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        usd_inr=80.0,
    )

    assert result.trip is not None
    assert result.trip["id"] == "recovered-trip"
    assert len(asked) == 2
    assert asked[1][0] == generate._RECOVERY_MESSAGE
    assert asked[1][1] == asked[0][1]
    assert asked[1][2] != asked[0][2]


def test_a_failed_first_turn_is_not_repeated_as_paid_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 1)

    def fail(_api: str, _message: str, _user_id: str, request_id: str) -> None:
        asked.append(request_id)
        raise http.client.RemoteDisconnected("closed without response")

    monkeypatch.setattr(generate, "_ask", fail)

    result = generate._attempt(
        _ONE_REQUEST[0],
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        usd_inr=80.0,
    )

    assert result.error.startswith("RemoteDisconnected:")
    assert len(asked) == 1


def test_a_run_is_charged_only_for_what_that_attempt_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage = {"cost_usd": 1.0}
    _stub_generate(monkeypatch, usage)

    def _spend(api: str, message: str, user_id: str, request_id: str) -> None:
        usage["cost_usd"] = 1.25

    monkeypatch.setattr(generate, "_ask", _spend)
    monkeypatch.setattr(generate, "_usage_for", lambda database, user_id: dict(usage))

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        target=1,
        requests=_ONE_REQUEST,
    )

    assert result["spent_inr"] == pytest.approx(0.25 * budget.usd_inr())


def _primary(phrase: str) -> str:
    for word in phrase.split():
        if word[:1].isupper():
            return word.lower()
    return phrase.lower()


def test_a_generated_destination_is_never_one_a_seed_already_uses() -> None:
    """The generated pool is disjoint from the seeds, so it cannot repeat one."""
    for destination in matrix.DESTINATIONS:
        name = _primary(destination.phrase)
        for seed in matrix.REQUESTS:
            assert name not in seed.message.lower()


def test_every_generated_request_says_where_the_traveller_starts() -> None:
    for request in matrix.candidates(Catalog(), limit=40):
        assert " from " in request.message
        assert request.days > 0
        assert str(request.days) in request.message
        assert request.scenario_expectations


def test_only_an_explicit_budget_scenario_requires_budget_evidence() -> None:
    budget_request = next(
        request
        for request in matrix.candidates(Catalog(), limit=500)
        if request.emphasis == "budget"
    )
    non_budget_request = next(
        request
        for request in matrix.candidates(Catalog(), limit=500)
        if request.emphasis == "heritage"
    )

    assert budget_request.budget_evidence_required
    assert not non_budget_request.budget_evidence_required


def test_a_request_the_corpus_already_holds_is_never_offered_again() -> None:
    first = matrix.candidates(Catalog(), limit=1)[0]
    catalog = Catalog(
        [
            {
                "slug": first.slug,
                "trip_id": "trip-1",
                "signature": first.signature.key,
                "destination": first.destination,
                "emphasis": first.emphasis,
            }
        ]
    )

    again = matrix.candidates(catalog, limit=300)

    assert first.slug not in {request.slug for request in again}
    assert first.signature.key not in {request.signature.key for request in again}


def test_a_destination_is_not_repeated_until_the_others_have_been_tried() -> None:
    picked = matrix.candidates(Catalog(), limit=len(matrix.DESTINATIONS))

    assert len({request.destination for request in picked}) == len(matrix.DESTINATIONS)


def test_unused_seeds_are_offered_before_generated_requests() -> None:
    queue = matrix.pending(Catalog(), limit=len(matrix.REQUESTS) + 6)

    seeds = [request.slug for request in queue[: len(matrix.REQUESTS)]]
    assert seeds == [request.slug for request in matrix.REQUESTS]
    assert all(request.destination for request in queue[len(matrix.REQUESTS) :])


def test_a_produced_seed_drops_out_of_the_queue() -> None:
    produced = matrix.REQUESTS[0]
    catalog = Catalog([{"slug": produced.slug, "trip_id": "trip-1"}])

    queue = matrix.pending(catalog, limit=len(matrix.REQUESTS))

    assert produced.slug not in {request.slug for request in queue}


def test_india_matrix_balances_destinations_before_adding_depth() -> None:
    queue = india_heuristic_matrix.candidates(
        Catalog(), limit=len(india_heuristic_matrix.DESTINATIONS)
    )

    assert len({request.destination for request in queue}) == len(
        india_heuristic_matrix.DESTINATIONS
    )
    assert all(request.destination.startswith("india:") for request in queue)
    assert all("within India" in request.message for request in queue)


def test_india_matrix_uses_destination_specific_duration_guidance() -> None:
    all_requests = india_heuristic_matrix.candidates(Catalog(), limit=0)
    goa = [request for request in all_requests if request.destination == "india:goa"]
    ladakh = [request for request in all_requests if request.destination == "india:ladakh"]

    assert {request.days for request in goa} == {3, 4, 5, 7}
    assert {request.days for request in ladakh} == {7, 8, 9, 10}


def test_india_matrix_prioritizes_likely_destination_audiences() -> None:
    queue = india_heuristic_matrix.candidates(
        Catalog(), limit=len(india_heuristic_matrix.DESTINATIONS)
    )
    tamil_nadu = next(request for request in queue if request.destination == "india:tamil-nadu")
    goa = next(request for request in queue if request.destination == "india:goa")

    assert tamil_nadu.emphasis == "pilgrimage"
    assert tamil_nadu.party in {"three-generation", "senior-couple"}
    assert tamil_nadu.days in {4, 5}
    assert goa.emphasis in {"celebration", "relaxation"}
    assert any("Heuristic audience rationale" in item for item in tamil_nadu.scenario_expectations)


def test_india_matrix_deduplicates_only_the_exact_scenario() -> None:
    first = next(
        request
        for request in india_heuristic_matrix.candidates(Catalog(), limit=0)
        if request.destination == "india:goa" and request.emphasis == "relaxation"
    )
    catalog = Catalog(
        [
            {
                "slug": first.slug,
                "signature": first.signature.key,
                "destination": first.destination,
                "emphasis": first.emphasis,
            }
        ]
    )

    remaining = india_heuristic_matrix.candidates(catalog, limit=0)
    matching = [
        request
        for request in remaining
        if request.destination == first.destination and request.emphasis == first.emphasis
    ]

    assert first.slug not in {request.slug for request in remaining}
    assert matching
    assert any(request.party != first.party or request.days != first.days for request in matching)


def test_outbound_matrix_balances_destinations_and_prioritizes_mainstream() -> None:
    queue = india_outbound_matrix.candidates(
        Catalog(), limit=len(india_outbound_matrix.DESTINATIONS)
    )

    assert len({request.destination for request in queue}) == len(
        india_outbound_matrix.DESTINATIONS
    )
    assert all(request.destination.startswith("india-outbound:") for request in queue)
    assert {request.destination for request in queue[:8]} == {
        "india-outbound:uae",
        "india-outbound:thailand",
        "india-outbound:singapore",
        "india-outbound:bali",
        "india-outbound:vietnam",
        "india-outbound:maldives",
        "india-outbound:malaysia",
        "india-outbound:schengen-classic",
    }


def test_outbound_matrix_uses_destination_specific_durations_and_evidence() -> None:
    all_requests = india_outbound_matrix.candidates(Catalog(), limit=0)
    uae = [request for request in all_requests if request.destination == "india-outbound:uae"]
    europe = [
        request
        for request in all_requests
        if request.destination == "india-outbound:schengen-classic"
    ]

    assert {request.days for request in uae} == {4, 5, 6}
    assert {request.days for request in europe} == {9, 11, 14}
    assert all("Indian passport" in request.message for request in all_requests)
    assert all(
        any("Evidence posture" in item for item in request.scenario_expectations)
        for request in all_requests
    )


def test_outbound_matrix_deduplicates_only_the_exact_scenario() -> None:
    first = next(
        request
        for request in india_outbound_matrix.candidates(Catalog(), limit=0)
        if request.destination == "india-outbound:uae" and request.emphasis == "family"
    )
    catalog = Catalog(
        [
            {
                "slug": first.slug,
                "signature": first.signature.key,
                "destination": first.destination,
                "emphasis": first.emphasis,
            }
        ]
    )

    remaining = india_outbound_matrix.candidates(catalog, limit=0)
    matching = [
        request
        for request in remaining
        if request.destination == first.destination and request.emphasis == first.emphasis
    ]

    assert first.slug not in {request.slug for request in remaining}
    assert matching
    assert any(request.party != first.party or request.days != first.days for request in matching)


def test_build_corpus_scope_distinguishes_country_from_market(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = Path(__file__).parents[1] / "scripts" / "dev" / "build_corpus.py"
    spec = importlib.util.spec_from_file_location("build_corpus", script)
    assert spec and spec.loader
    build_corpus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_corpus)

    assert build_corpus._selected_scope(None, None) == ("matrix", "global")
    assert build_corpus._selected_scope(None, "india") == ("country", "india")
    assert build_corpus._selected_scope("india", None) == ("market", "india")
    with pytest.raises(ValueError, match="not both"):
        build_corpus._selected_scope("india", "india")

    country = build_corpus._requests_for_scope(("country", "india"), Catalog(), limit=4)
    market = build_corpus._requests_for_scope(("market", "india"), Catalog(), limit=4)

    assert all(request.destination.startswith("india:") for request in country)
    assert [request.destination.startswith("india-outbound:") for request in market] == [
        False,
        True,
        False,
        True,
    ]

    assert build_corpus.main(["--market", "India", "--dry-run"]) == 0
    assert "request scope      market:india" in capsys.readouterr().out

    with pytest.raises(SystemExit) as error:
        build_corpus.main(["--country", "india", "--market", "india", "--dry-run"])
    assert error.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_build_corpus_returns_failure_when_planner_is_barren(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = Path(__file__).parents[1] / "scripts" / "dev" / "build_corpus.py"
    spec = importlib.util.spec_from_file_location("build_corpus_barren", script)
    assert spec and spec.loader
    build_corpus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_corpus)
    monkeypatch.setattr(build_corpus.runner, "corpus_root", lambda _root: tmp_path)
    monkeypatch.setattr(build_corpus.generate, "api_health_error", lambda _api: None)
    monkeypatch.setattr(
        build_corpus.generate,
        "build",
        lambda *_args, **_kwargs: {
            "produced": [],
            "attempts": 3,
            "spent_inr": 120.0,
            "stopped_because": "barren",
            "corpus_total": 0,
            "generation_run_id": "run-1",
            "generated_by_commit": "abc123",
        },
    )

    exit_code = build_corpus.main(["--budget", "1000"])

    assert exit_code == 4
    assert "accepted yield      0/3 (0%)" in capsys.readouterr().out


def test_build_corpus_runtime_defaults_follow_the_current_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Path(__file__).parents[1] / "scripts" / "dev" / "build_corpus.py"
    spec = importlib.util.spec_from_file_location("build_corpus_runtime", script)
    assert spec and spec.loader
    build_corpus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_corpus)

    primary = tmp_path / "tripplanner"
    sandbox = tmp_path / "tripplanner.worktrees" / "sbx-4-test"
    registry = tmp_path / "tripplanner.worktrees" / "sandboxes.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            [
                {
                    "worktree": str(sandbox),
                    "apiPort": 8130,
                    "database": "tripplanner-sbx-4-test",
                }
            ]
        )
    )

    class Result:
        returncode = 0
        stdout = str(primary / ".git")

    monkeypatch.setattr(build_corpus.subprocess, "run", lambda *args, **kwargs: Result())

    assert build_corpus._runtime_defaults(primary) == (
        "http://127.0.0.1:8000",
        "tripplanner-local",
    )
    assert build_corpus._runtime_defaults(sandbox) == (
        "http://127.0.0.1:8130",
        "tripplanner-sbx-4-test",
    )


def test_a_run_keeps_asking_until_the_budget_is_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage = {"cost_usd": 0.0}
    _stub_generate(monkeypatch, usage)
    monkeypatch.setattr(
        generate,
        "_saved_trip",
        lambda database, user_id: {
            "id": user_id,
            "day_wise_itinerary": [{"stops": [{"name": "a stop"}]}],
        },
    )

    def _spend(api: str, message: str, user_id: str, request_id: str) -> None:
        usage["cost_usd"] += 1.0

    monkeypatch.setattr(generate, "_ask", _spend)

    budget_inr = 3.5 * budget.usd_inr()
    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requested_budget_inr=budget_inr,
        workers=1,
    )

    assert result["stopped_because"] == "budget"
    assert len(result["produced"]) == 3
    assert result["spent_inr"] <= budget_inr
    manifest = generate.load_manifest(tmp_path)
    assert manifest["produced"][0]["generation_run_id"] == result["generation_run_id"]
    assert "generated_by_commit" in manifest["produced"][0]


def test_turns_in_flight_together_still_cannot_overshoot_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reserving before asking is what keeps four open turns inside one cap."""
    usage = {"cost_usd": 0.0}
    lock = threading.Lock()
    _stub_generate(monkeypatch, usage)
    monkeypatch.setattr(
        generate,
        "_saved_trip",
        lambda database, user_id: {
            "id": user_id,
            "day_wise_itinerary": [{"stops": [{"name": "a stop"}]}],
        },
    )

    def _spend(api: str, message: str, user_id: str, request_id: str) -> None:
        with lock:
            usage["cost_usd"] += 1.0

    monkeypatch.setattr(generate, "_ask", _spend)

    budget_inr = 6.0 * budget.usd_inr()
    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requested_budget_inr=budget_inr,
        workers=4,
    )

    assert result["spent_inr"] <= budget_inr
    assert result["stopped_because"] == "budget"


def test_planning_turns_are_asked_at_the_same_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The barrier only clears if three turns are genuinely open at once."""
    barrier = threading.Barrier(3, timeout=10)
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: barrier.wait(),
    )

    generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=matrix.candidates(Catalog(), limit=3),
        requested_budget_inr=1000,
        workers=3,
    )

    assert not barrier.broken


def test_a_dropped_connection_is_retried_with_the_same_request_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server may have finished the turn, so the retry must be able to replay it."""
    seen: list[tuple[str, str]] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(generate.time, "sleep", lambda seconds: None)

    def _ask(api: str, message: str, user_id: str, request_id: str) -> None:
        seen.append((user_id, request_id))
        if len(seen) == 1:
            raise http.client.RemoteDisconnected("closed without response")

    monkeypatch.setattr(generate, "_ask", _ask)

    generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=_ONE_REQUEST,
        requested_budget_inr=1000,
        workers=1,
    )

    assert len(seen) == 3
    assert seen[0] == seen[1]
    assert seen[2][0] == seen[0][0]
    assert seen[2][1] != seen[0][1]


def test_a_full_request_timeout_is_not_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One 15-minute allowance is enough; repeating it can stall a request for an hour."""
    seen: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 4)

    def _ask(api: str, message: str, user_id: str, request_id: str) -> None:
        seen.append(request_id)
        raise TimeoutError("timed out")

    monkeypatch.setattr(generate, "_ask", _ask)

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=_ONE_REQUEST,
        requested_budget_inr=1000,
        workers=1,
    )

    assert len(seen) == 1
    assert result["stopped_because"] == "exhausted"


def test_a_complete_persisted_trip_survives_a_dropped_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response can fail after the server has already completed and saved the turn."""
    _stub_generate(monkeypatch, {"cost_usd": 0.25})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: (_ for _ in ()).throw(
            http.client.RemoteDisconnected("closed without response")
        ),
    )
    monkeypatch.setattr(
        generate,
        "_saved_trip",
        lambda database, user_id: {
            "id": "saved-after-disconnect",
            "day_wise_itinerary": [{"day": 1, "stops": [{"name": "Fort"}]}],
        },
    )

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=_ONE_REQUEST,
        requested_budget_inr=1000,
        workers=1,
    )

    assert len(result["produced"]) == 1
    assert result["produced"][0]["trip_id"] == "saved-after-disconnect"


def test_a_turn_that_keeps_failing_is_reported_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines: list[str] = []
    asked: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 1)

    def _ask(api: str, message: str, user_id: str, request_id: str) -> None:
        asked.append(user_id)
        if len(asked) == 1:
            raise http.client.RemoteDisconnected("closed without response")

    monkeypatch.setattr(generate, "_ask", _ask)

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=matrix.candidates(Catalog(), limit=3),
        requested_budget_inr=1000,
        workers=1,
        on_progress=lines.append,
    )

    assert len(asked) == 5
    assert result["stopped_because"] == "exhausted"
    assert any("RemoteDisconnected" in line for line in lines)


def test_a_request_is_announced_before_the_slow_call_not_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(
        generate,
        "_ask",
        lambda api, message, user_id, request_id: events.append("asked"),
    )

    generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        target=1,
        requests=_ONE_REQUEST,
        on_progress=events.append,
    )

    assert events[0].startswith("  -> corpus-slug")
    assert events[1] == "asked"


# ---- place cache ----------------------------------------------------------


def test_a_failed_lookup_is_not_worth_preserving() -> None:
    """Re-trying a miss is cheap; storing it forever is not."""
    from tripplanner.validation import place_cache

    assert place_cache._worth_keeping({"lat": 12.9, "lng": 77.6})
    assert not place_cache._worth_keeping({"name": "Nowhere"})
    assert not place_cache._worth_keeping(None)


def test_volatile_photo_urls_are_never_written_to_the_file() -> None:
    """Signed URLs expire within the hour; the references outlive them."""
    from tripplanner.validation import place_cache

    portable = place_cache._portable(
        {"lat": 1.0, "photo_urls": ["https://signed"], "__photos_at__": 1.0, "photo_refs": ["a"]}
    )

    assert "photo_urls" not in portable
    assert "__photos_at__" not in portable
    assert portable["photo_refs"] == ["a"]


def test_only_the_photos_the_app_can_show_are_kept() -> None:
    from tripplanner.validation import place_cache

    portable = place_cache._portable({"lat": 1.0, "photo_refs": [str(n) for n in range(10)]})

    assert portable["photo_refs"] == ["0"]


def test_warm_everything_keeps_the_complete_cache_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    from tripplanner.config import get_settings
    from tripplanner.validation import place_cache

    monkeypatch.setattr(get_settings(), "cache_warm_everything", True)
    entry = {
        "photo_urls": ["https://signed"],
        "__photos_at__": 1.0,
        "photo_refs": [str(n) for n in range(10)],
        "reviews": [{"text": "lovely"}],
    }

    assert place_cache._portable(entry) == entry
    assert place_cache._worth_keeping({"__at__": 1.0})


def test_the_photo_cap_matches_what_the_app_renders() -> None:
    """Trimming below what the product shows would lose images silently."""
    from tripplanner.validation import place_cache
    from tripplanner.web import places_cache as app_cache

    assert place_cache._MAX_PHOTO_REFS == app_cache._MAX_PHOTOS_PER_PLACE


def test_merging_prefers_the_more_recently_fetched_copy() -> None:
    """Two lanes cache the same place; the newer fetch is the better one."""
    from tripplanner.validation import place_cache

    merged = place_cache.merge(
        {"a|goa": {"lat": 1.0, "__at__": 100.0}, "b|goa": {"lat": 2.0, "__at__": 50.0}},
        {"a|goa": {"lat": 9.9, "__at__": 200.0}, "c|goa": {"lat": 3.0, "__at__": 10.0}},
    )

    assert merged["a|goa"]["lat"] == 9.9
    assert merged["b|goa"]["lat"] == 2.0
    assert sorted(merged) == ["a|goa", "b|goa", "c|goa"]


def test_a_saved_cache_round_trips(tmp_path: Path) -> None:
    from tripplanner.validation import place_cache

    path = place_cache.cache_path(tmp_path)
    place_cache.save(path, {"eiffel tower|paris": {"lat": 48.8, "__at__": 1.0}})

    assert place_cache.load(path)["eiffel tower|paris"]["lat"] == 48.8
    assert place_cache.load(tmp_path / "absent.json") == {}


def test_the_cache_file_is_not_rewritten_by_an_identical_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unchanged export must preserve bytes and mtime during discard."""
    from tripplanner.validation import place_cache

    places = {"b|goa": {"lat": 2.0}, "a|goa": {"lat": 1.0}}
    path = tmp_path / "places.json"
    timestamps = iter(["2026-08-18T01:00:00Z", "2026-08-18T02:00:00Z"])
    monkeypatch.setattr(place_cache.time, "strftime", lambda *_: next(timestamps))
    place_cache.save(path, places)
    original = path.read_bytes()
    original_mtime = path.stat().st_mtime_ns

    place_cache.save(path, dict(reversed(list(places.items()))))

    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == original_mtime


def test_restoring_refuses_a_database_that_is_not_a_sandbox() -> None:
    from tripplanner.validation import place_cache

    with pytest.raises(ValueError):
        place_cache.restore("tripplanner-prod", {"a|b": {"lat": 1.0}})


# ---- lane snapshots -------------------------------------------------------


def test_a_saved_lane_keeps_its_trips_after_the_database_is_gone(tmp_path: Path) -> None:
    """Discarding a sandbox drops its database; the audit still needs the trips."""
    from tripplanner.validation import lane_trips

    path = lane_trips.snapshot_path(tmp_path, "tripplanner-sbx-9-gone")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "database": "tripplanner-sbx-9-gone",
                "trips": [{"trip_id": "goa_2027", "destination": "Goa"}],
            }
        ),
        encoding="utf-8",
    )

    restored = corpus.from_lane_snapshots(tmp_path)

    assert [record.destination for record in restored] == ["Goa"]
    assert restored[0].provenance == corpus.REAL
    assert "saved" in restored[0].source


def test_a_snapshot_of_a_living_lane_is_deduplicated_away(tmp_path: Path) -> None:
    """A snapshot must not double-count a trip the database still holds."""
    from tripplanner.validation import lane_trips

    plan = {"trip_id": "goa_2027", "destination": "Goa"}
    path = lane_trips.snapshot_path(tmp_path, "tripplanner-sbx-9-live")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"database": "tripplanner-sbx-9-live", "trips": [plan]}))

    live = corpus.CorpusRecord(
        id="tripplanner-sbx-9-live:goa_2027", provenance=corpus.REAL, source="db", plan=plan
    )
    merged = corpus.deduplicate([live, *corpus.from_lane_snapshots(tmp_path)])

    assert len(merged) == 1


def test_saving_refuses_a_database_that_is_not_a_sandbox(tmp_path: Path) -> None:
    from tripplanner.validation import lane_trips

    with pytest.raises(ValueError):
        lane_trips.save(tmp_path, "tripplanner-prod")


def test_an_unchanged_lane_snapshot_is_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tripplanner.validation import lane_trips

    trip = {"trip_id": "goa_2027", "destination": "Goa"}
    timestamps = iter(["2026-08-18T01:00:00Z", "2026-08-18T02:00:00Z"])
    monkeypatch.setattr(lane_trips, "read_trips", lambda _: [trip])
    monkeypatch.setattr(lane_trips.time, "strftime", lambda *_: next(timestamps))
    lane_trips.save(tmp_path, "tripplanner-sbx-6-lab-factory")
    path = lane_trips.snapshot_path(tmp_path, "tripplanner-sbx-6-lab-factory")
    original = path.read_bytes()
    original_mtime = path.stat().st_mtime_ns

    lane_trips.save(tmp_path, "tripplanner-sbx-6-lab-factory")

    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == original_mtime


def test_the_cache_containers_expire_and_the_data_ones_never_do() -> None:
    """A TTL on users or trips would delete the product's own records."""
    from tripplanner import storage_cosmos

    assert storage_cosmos._CACHE_TTL_SECONDS == 30 * 24 * 60 * 60
    assert storage_cosmos._CACHE_CONTAINERS == {"places_cache", "tool_cache"}
    for owned in ("users", "trips", "shared_trips", "documents"):
        assert owned not in storage_cosmos._CACHE_CONTAINERS


def test_the_primary_local_database_may_hold_cache_but_hosted_ones_may_not() -> None:
    """Master is never discarded, so it only ever fills by hand -- but it is local."""
    from tripplanner.validation import place_cache

    assert place_cache.assert_cache_target("tripplanner-local") == "tripplanner-local"
    assert place_cache.assert_cache_target("tripplanner-sbx-2-auto-validation")
    for hosted in ("tripplanner-prod", "tripplanner-canary"):
        with pytest.raises(ValueError):
            place_cache.assert_cache_target(hosted)
    with pytest.raises(ValueError):
        place_cache.assert_cache_target("something-else")


def test_the_central_dump_is_a_cache_target_and_no_lane_reads_it_at_request_time() -> None:
    """It is a copy kept for the hooks, not a database the app is ever pointed at."""
    from tripplanner.validation import place_cache

    assert place_cache.assert_cache_target(place_cache.CENTRAL_DATABASE)
    assert place_cache.CENTRAL_DATABASE != place_cache.PRIMARY_DATABASE

    source_root = Path(place_cache.__file__).resolve().parents[1]
    naming_it = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if place_cache.CENTRAL_DATABASE in path.read_text(encoding="utf-8")
    }
    assert naming_it == {"validation/place_cache.py"}


def test_a_sync_writes_only_what_the_other_side_does_not_already_have() -> None:
    """Every stack start runs this, so a warm cache must cost no writes at all."""
    from tripplanner.validation import place_cache

    central = {
        "eiffel tower|paris": {"lat": 48.8, "__at__": 100.0},
        "louvre|paris": {"lat": 48.86, "__at__": 100.0},
    }
    live = {
        "eiffel tower|paris": {"lat": 48.8, "__at__": 50.0},  # older, keep central's
        "louvre|paris": {"lat": 48.861, "__at__": 200.0},  # newer, hand it over
        "orsay|paris": {"lat": 48.85, "__at__": 60.0},  # unseen, hand it over
    }
    changed = place_cache.delta(central, live)
    assert set(changed) == {"louvre|paris", "orsay|paris"}
    assert place_cache.delta(central, central) == {}


def test_a_throttled_run_waits_as_long_as_the_server_asked() -> None:
    """A token-per-minute window outlasts any backoff we would have guessed."""
    import urllib.error
    from email.message import Message

    from tripplanner.validation import generate

    headers = Message()
    headers["Retry-After"] = "120"
    throttled = urllib.error.HTTPError("u", 429, "Too Many Requests", headers, None)

    assert generate._retry_delay(throttled, attempt=1) == 120.0

    plain = urllib.error.HTTPError("u", 503, "Unavailable", Message(), None)
    assert generate._retry_delay(plain, attempt=1) == 2.0


def test_a_throttle_never_waits_without_bound() -> None:
    import urllib.error
    from email.message import Message

    from tripplanner.validation import generate

    headers = Message()
    headers["Retry-After"] = "99999"
    forever = urllib.error.HTTPError("u", 429, "Too Many Requests", headers, None)

    assert generate._retry_delay(forever, attempt=1) == generate._MAX_RETRY_WAIT_SEC


def test_api_health_check_explains_a_refused_local_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error
    import urllib.request

    from tripplanner.validation import generate

    def refused(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)

    error = generate.api_health_error("http://127.0.0.1:8110")

    assert error is not None
    assert "Connection refused" in error


def test_exhausted_connection_refusals_are_an_api_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    from tripplanner.validation import generate

    def refused(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(generate, "_ask", refused)
    monkeypatch.setattr(generate.time, "sleep", lambda _seconds: None)

    error = generate._send_with_retry("http://127.0.0.1:8110", "plan", "user", "request")

    assert error is not None
    assert error.startswith("API unavailable:")


def test_reviews_are_kept_in_the_cache_file() -> None:
    """Owner decision: keep the grounding whole while the product is small."""
    from tripplanner.validation import place_cache

    portable = place_cache._portable({"lat": 1.0, "reviews": [{"text": "lovely"}]})

    assert portable["reviews"] == [{"text": "lovely"}]


def test_a_run_that_saves_almost_nothing_stops_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Left overnight, a broken planner would spend the whole budget on nothing."""
    lines: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.001})
    monkeypatch.setattr(generate, "_ask", lambda api, message, user_id, request_id: None)
    monkeypatch.setattr(generate, "_saved_trip", lambda database, user_id: None)

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=matrix.candidates(Catalog(), limit=200),
        requested_budget_inr=1000,
        workers=1,
        on_progress=lines.append,
    )

    assert result["stopped_because"] == "barren"
    assert len(result["produced"]) == 0
    assert any("Stopping:" in line for line in lines)
    assert sum(1 for line in lines if "no itinerary saved" in line) == (
        generate.MAX_CONSECUTIVE_BARREN
    )


def test_a_run_with_a_few_barren_requests_keeps_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Some requests genuinely need a question; that is not a broken run."""
    seen: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.001})
    monkeypatch.setattr(
        generate, "_ask", lambda api, message, user_id, request_id: seen.append(user_id)
    )
    # One in five saves nothing -- under the quarter that means something is wrong.
    monkeypatch.setattr(
        generate,
        "_saved_trip",
        lambda database, user_id: (
            None
            if user_id.endswith("0d")
            else {"day_wise_itinerary": [{"day": 1, "stops": [{"name": "Fort"}]}]}
        ),
    )

    result = generate.build(
        tmp_path,
        database="tripplanner-sbx-test",
        api="http://127.0.0.1:0",
        requests=matrix.candidates(Catalog(), limit=20),
        requested_budget_inr=1000,
        workers=1,
    )

    assert result["stopped_because"] != "barren"
    assert len(result["produced"]) > 10
