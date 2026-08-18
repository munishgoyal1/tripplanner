"""The validation harness, tested without an emulator or a provider."""

from __future__ import annotations

import dataclasses
import http.client
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
    matrix,
    mutations,
    observations,
    registry,
    render,
    runner,
)
from tripplanner.validation.catalog import Catalog
from tripplanner.validation.checks import check_record, plan_names
from tripplanner.validation.emulator import assert_sandbox_database
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
                    {"name": "Kempegowda International Airport", "kind": "transport",
                     "time": "05:00"},
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
    assert len(corpus.deduplicate(same)) == 1


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
        "I9", findings.symptom_of("Mandu Fort is far from X on Day 3.", names),
        "m", "trip-a", corpus.REAL,
    )
    second = findings.Finding(
        "I9", findings.symptom_of("Rajwada Palace is far from X on Day 7.", names),
        "m", "trip-b", corpus.REAL,
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
    """The reported defect: a taxi from Bengaluru to a Paris hotel."""
    return_day = _plan()
    return_day["day_wise_itinerary"] = [
        {
            "day": 1,
            "stops": [
                {"name": "Charles de Gaulle Airport", "kind": "transport", "time": "09:55"},
                {"name": "Kempegowda International Airport", "kind": "transport",
                 "time": "23:20"},
                {"name": "Hotel Lutetia", "kind": "hotel", "time": "23:59"},
            ],
        }
    ]
    record = corpus.CorpusRecord(
        id="return-day",
        provenance=corpus.REAL,
        source="test",
        plan=return_day,
        places={**_PLACES, "charles de gaulle airport|paris": {"lat": 49.0097, "lng": 2.5479}},
    )

    reported = render.check_render(record)

    assert any(finding.rule == render.RULE_GROUND_LEG for finding in reported)
    assert any(finding.rule == render.RULE_LEG_DURATION for finding in reported)


def test_render_checks_stay_silent_without_the_facts_to_measure_with() -> None:
    blind = corpus.CorpusRecord(id="x", provenance=corpus.REAL, source="s", plan=_plan())

    assert render.check_render(blind) == []


def test_a_stop_missing_from_the_stored_facts_is_not_called_unmapped() -> None:
    """The audit's own blind spot must not be reported as the product's defect."""
    view = {"unmapped_stops": [{"name": "Somewhere Uncached", "day": 1, "reason": "no_location"}]}

    assert render._unmapped_findings(_record(), view, []) == []


def test_a_place_the_provider_swapped_for_another_is_reported() -> None:
    view = {"unmapped_stops": [{"name": "Seine River Cruise", "day": 2, "reason": "no_match"}]}

    reported = render._unmapped_findings(_record(), view, [])
    assert [finding.rule for finding in reported] == [render.RULE_UNMAPPED]


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
    assert [f.rule for f in blinded if "blank-origin" in f.message] == [
        mutations.RULE_UNNOTICED
    ]



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
        tmp_path, spent_inr_amount=4700, trips=60, model="gpt-4.1", stopped_because="budget"
    )

    assert budget.authorize(tmp_path).budget_inr == 300.0


def test_the_cumulative_cap_refuses_a_further_run(tmp_path: Path) -> None:
    budget.record(
        tmp_path, spent_inr_amount=5000, trips=64, model="gpt-4.1", stopped_because="budget"
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

    payload = report_module.build_report(runner.audit(
        tmp_path, records=result.records, baseline=baseline
    ), baseline)

    accepted = {item["key"]: item for item in payload["groups"]}[key]
    assert accepted["new"] is False
    assert accepted["accepted_on"] == "2026-08-01"


_ONE_REQUEST = (TripRequest("corpus-slug", "a shape", "Plan a trip"),)


def _stub_generate(monkeypatch: pytest.MonkeyPatch, usage: dict[str, Any]) -> None:
    monkeypatch.setattr(generate, "assert_sandbox_database", lambda name: name)
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
    seen: list[str] = []
    _stub_generate(monkeypatch, {"cost_usd": 0.0})
    monkeypatch.setattr(generate, "_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(generate.time, "sleep", lambda seconds: None)

    def _ask(api: str, message: str, user_id: str, request_id: str) -> None:
        seen.append(request_id)
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

    assert len(seen) == 2
    assert seen[0] == seen[1]


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

    assert len(asked) == 3
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

    assert portable["photo_refs"] == ["0", "1", "2"]


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


def test_the_cache_file_is_stable_between_identical_saves(tmp_path: Path) -> None:
    """An unchanged export must not produce a diff, or the file churns."""
    from tripplanner.validation import place_cache

    places = {"b|goa": {"lat": 2.0}, "a|goa": {"lat": 1.0}}
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    place_cache.save(first, places)
    place_cache.save(second, dict(reversed(list(places.items()))))

    strip = lambda text: [line for line in text.splitlines() if "saved_at" not in line]  # noqa: E731
    assert strip(first.read_text()) == strip(second.read_text())


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
    # Judged only once enough have run to tell a bad run from an odd request.
    assert len(result["produced"]) == 0
    assert any("Stopping:" in line for line in lines)
    assert sum(1 for line in lines if "no itinerary saved" in line) == (
        generate.MIN_ATTEMPTS_BEFORE_GIVING_UP
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
