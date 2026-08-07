from __future__ import annotations

from datetime import date

from tripplanner.web import document_readiness

TRIP = {
    "destination": "Lisbon",
    "departure_date": "2026-10-08",
    "return_date": "2026-10-13",
    "travelers": "Munish, Priya and Aarav",
}

PREFS = {
    "profile": {"display_name": "Munish"},
    "family_members": [
        {"relationship": "spouse", "name": "Priya"},
        {"relationship": "child", "name": "Aarav"},
    ],
}


def _document(traveller_key, document_type, fields):
    return {
        "id": f"{traveller_key}-{document_type}",
        "scope": "traveler",
        "type": document_type,
        "traveller_key": traveller_key,
        "fields": fields,
    }


def _by_id(result, prefix):
    return [check for check in result["checks"] if check["id"].startswith(prefix)]


# Lisbon from India: the passport, visa, and permit checks only speak when the
# trip is known to cross a border, so every case states its geography.
INTERNATIONAL = {"origin_country": "India", "destination_country": "Portugal"}


def _evaluate(documents, trip=None, prefs=None, **geography):
    return document_readiness.evaluate(
        TRIP if trip is None else trip,
        documents,
        PREFS if prefs is None else prefs,
        **{**INTERNATIONAL, **geography},
    )


class TestTravellerSelection:
    def test_named_family_members_join_the_trip(self):
        people = document_readiness.trip_travellers(TRIP, PREFS)
        assert [person["key"] for person in people] == ["self", "spouse:priya", "child:aarav"]

    def test_a_solo_trip_does_not_pull_in_relatives(self):
        solo = dict(TRIP, travelers="1 adult")
        people = document_readiness.trip_travellers(solo, PREFS)
        assert [person["key"] for person in people] == ["self"]


class TestPassportChecks:
    def test_a_traveller_with_no_passport_is_a_warning_not_a_blocker(self):
        result = _evaluate([])
        missing = _by_id(result, "passport-missing-child:aarav")
        assert missing and missing[0]["severity"] == "warning"
        assert missing[0]["origin"] == "computed"
        assert "leaves India" in missing[0]["detail"]

    def test_a_passport_expiring_inside_the_margin_is_a_blocker(self):
        documents = [_document("spouse:priya", "passport", {"expiry": "2026-11-20"})]
        result = _evaluate(documents)
        margin = _by_id(result, "passport-margin-spouse:priya")
        assert margin and margin[0]["severity"] == "blocker"
        assert "38 days after you return" in margin[0]["detail"]

    def test_a_passport_expiring_during_the_trip_is_a_blocker(self):
        documents = [_document("spouse:priya", "passport", {"expiry": "2026-10-10"})]
        result = _evaluate(documents)
        assert _by_id(result, "passport-expired-spouse:priya")[0]["severity"] == "blocker"

    def test_a_passport_with_room_to_spare_is_clear(self):
        documents = [_document("self", "passport", {"expiry": "2031-04-02"})]
        result = _evaluate(documents)
        assert _by_id(result, "passport-ok-self")[0]["severity"] == "ok"

    def test_a_passport_without_an_expiry_is_a_warning_not_a_guess(self):
        documents = [_document("self", "passport", {"issuing_country": "India"})]
        result = _evaluate(documents)
        assert _by_id(result, "passport-expiry-unknown-self")[0]["severity"] == "warning"

    def test_the_second_passport_of_a_dual_national_does_not_raise_a_blocker(self):
        documents = [
            dict(_document("self", "passport", {"expiry": "2026-10-10"}), id="self-passport-old"),
            dict(_document("self", "passport", {"expiry": "2031-04-02"}), id="self-passport-new"),
        ]
        result = _evaluate(documents)
        assert _by_id(result, "passport-ok-self")[0]["severity"] == "ok"
        assert not _by_id(result, "passport-expired-self")


class TestBorderGate:
    def test_a_domestic_trip_says_nothing_about_passports(self):
        result = _evaluate([], origin_country="India", destination_country="India")
        assert not _by_id(result, "passport-")
        assert result["badge"] == ""
        assert result["crosses_border"] is False

    def test_an_unresolved_origin_keeps_the_check_quiet(self):
        result = _evaluate([], origin_country="", destination_country="Portugal")
        assert not _by_id(result, "passport-")
        assert result["crosses_border"] is False

    def test_a_domestic_trip_still_reports_a_stored_expiry(self):
        documents = [_document("self", "vaccination", {"expiry": "2026-10-09"})]
        result = _evaluate(documents, origin_country="India", destination_country="India")
        assert _by_id(result, "expiring-self-vaccination")[0]["severity"] == "warning"

    def test_a_domestic_trip_still_checks_insurance_it_was_given(self):
        documents = [
            _document("self", "insurance", {"valid_from": "2026-10-01", "valid_to": "2026-10-11"})
        ]
        result = _evaluate(documents, origin_country="India", destination_country="India")
        assert _by_id(result, "insurance-window-self")[0]["severity"] == "warning"


class TestVisaChecks:
    def test_a_visa_window_covering_the_trip_is_clear(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-12-15",
                },
            )
        ]
        result = _evaluate(documents)
        assert _by_id(result, "visa-ok-self")[0]["severity"] == "ok"

    def test_a_visa_ending_before_the_return_is_a_blocker(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-10-11",
                },
            )
        ]
        result = _evaluate(documents)
        assert _by_id(result, "visa-window-self")[0]["severity"] == "blocker"

    def test_no_visa_record_makes_no_claim(self):
        result = _evaluate([])
        assert not [check for check in result["checks"] if check["id"].startswith("visa-")]

    def test_an_untagged_visa_that_fits_makes_no_claim(self):
        documents = [
            _document("self", "visa", {"valid_from": "2026-06-01", "valid_to": "2026-12-15"})
        ]
        result = _evaluate(documents)
        assert not [check for check in result["checks"] if check["id"].startswith("visa-")]

    def test_an_untagged_visa_that_ends_early_only_warns(self):
        documents = [
            _document("self", "visa", {"valid_from": "2026-06-01", "valid_to": "2026-10-11"})
        ]
        result = _evaluate(documents)
        window = _by_id(result, "visa-window-self")[0]
        assert window["severity"] == "warning"
        assert "does not say which country" in window["detail"]

    def test_a_visa_for_another_country_is_not_read_as_this_one(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "United States",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-10-11",
                },
            )
        ]
        result = _evaluate(documents)
        assert not [check for check in result["checks"] if check["id"].startswith("visa-")]

    def test_a_visa_for_this_destination_is_read(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-10-11",
                },
            )
        ]
        result = _evaluate(documents)
        assert _by_id(result, "visa-window-self")[0]["severity"] == "blocker"

    def test_a_visa_that_ran_out_before_departure_says_so(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2025-06-01",
                    "valid_to": "2026-09-30",
                },
            )
        ]
        expired = _by_id(_evaluate(documents), "visa-expired-self")[0]
        assert expired["severity"] == "blocker"
        assert "before this trip starts" in expired["detail"]

    def test_a_visa_starting_after_departure_is_a_blocker(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2026-10-10",
                    "valid_to": "2026-12-15",
                },
            )
        ]
        window = _by_id(_evaluate(documents), "visa-window-self")[0]
        assert window["severity"] == "blocker"
        assert "starts after the trip" in window["title"]

    def test_a_visa_with_only_an_expiry_is_still_checked(self):
        documents = [
            _document("self", "visa", {"destination_country": "Portugal", "expiry": "2026-10-11"})
        ]
        assert _by_id(_evaluate(documents), "visa-window-self")[0]["severity"] == "blocker"

    def test_a_stay_limit_shorter_than_the_trip_blocks(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-12-15",
                    "max_stay_days": 3,
                },
            )
        ]
        limit = _by_id(_evaluate(documents), "visa-stay-limit-self")[0]
        assert limit["severity"] == "blocker"
        assert "permits 3 days" in limit["detail"]

    def test_a_schengen_visa_from_another_member_covers_the_trip(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "France",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-12-15",
                },
            )
        ]
        covered = _by_id(_evaluate(documents), "visa-ok-self")[0]
        assert covered["severity"] == "ok"
        assert "Schengen visa issued for France" in covered["detail"]

    def test_a_single_entry_visa_says_it_cannot_tell_if_it_was_used(self):
        documents = [
            _document(
                "self",
                "visa",
                {
                    "destination_country": "Portugal",
                    "entry_type": "Single entry",
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-12-15",
                },
            )
        ]
        covered = _by_id(_evaluate(documents), "visa-ok-self")[0]
        assert "single-entry" in covered["detail"]


# What the agent found and saved, so the answer outlives the conversation.
_REQUIRED = {
    "passport_country": "Indian",
    "destination_country": "Portugal",
    "status": "required",
    "processing_days_typical": 21,
    "official_url": "https://vistos.mne.gov.pt",
    "source_domain": "mne.gov.pt",
    "checked_on": "2026-07-01",
}


class TestVisaLeadTime:
    def _trip(self, **finding):
        return dict(TRIP, visa={**_REQUIRED, **finding})

    def test_no_saved_finding_makes_no_claim(self):
        result = _evaluate([])
        assert not _by_id(result, "visa-needed") and not _by_id(result, "visa-lead-time")

    def test_processing_longer_than_the_time_left_blocks(self):
        result = _evaluate([], trip=self._trip(), today=date(2026, 10, 1))
        late = _by_id(result, "visa-lead-time")[0]
        assert late["severity"] == "blocker"
        assert "about 21 days and you leave in 7" in late["detail"]
        assert late["action"].endswith("https://vistos.mne.gov.pt")

    def test_an_unofficial_source_can_only_warn(self):
        result = _evaluate(
            [],
            trip=self._trip(source_domain="travelblog.example"),
            today=date(2026, 10, 1),
        )
        assert _by_id(result, "visa-lead-time")[0]["severity"] == "warning"

    def test_a_thin_margin_warns(self):
        result = _evaluate([], trip=self._trip(), today=date(2026, 9, 10))
        margin = _by_id(result, "visa-lead-time")[0]
        assert margin["severity"] == "warning"
        assert "little margin" in margin["title"]

    def test_plenty_of_time_still_names_the_missing_visa(self):
        result = _evaluate([], trip=self._trip(), today=date(2026, 5, 1))
        assert _by_id(result, "visa-needed")[0]["severity"] == "warning"
        assert not _by_id(result, "visa-lead-time")

    def test_an_unknown_processing_time_is_never_invented(self):
        result = _evaluate(
            [], trip=self._trip(processing_days_typical=0), today=date(2026, 10, 1)
        )
        unknown = _by_id(result, "visa-needed")[0]
        assert unknown["severity"] == "warning"
        assert "unknown" in unknown["detail"]

    def test_a_visa_already_held_silences_the_deadline(self):
        documents = [
            _document(key, "visa", {"destination_country": "Portugal", "valid_to": "2026-12-15"})
            for key in ("self", "spouse:priya", "child:aarav")
        ]
        result = _evaluate(documents, trip=self._trip(), today=date(2026, 10, 1))
        assert not _by_id(result, "visa-lead-time") and not _by_id(result, "visa-needed")

    def test_one_traveller_still_missing_a_visa_keeps_the_deadline(self):
        documents = [
            _document("self", "visa", {"destination_country": "Portugal", "valid_to": "2026-12-15"})
        ]
        result = _evaluate(documents, trip=self._trip(), today=date(2026, 10, 1))
        assert _by_id(result, "visa-lead-time")[0]["severity"] == "blocker"

    def test_a_visa_free_finding_is_reassurance_not_a_warning(self):
        result = _evaluate([], trip=self._trip(status="visa_free"), today=date(2026, 5, 1))
        assert _by_id(result, "visa-not-needed")[0]["severity"] == "ok"

    def test_a_domestic_trip_never_reads_the_finding(self):
        result = _evaluate(
            [],
            trip=self._trip(),
            today=date(2026, 10, 1),
            origin_country="Portugal",
            destination_country="Portugal",
        )
        assert not _by_id(result, "visa-lead-time")


class TestOtherChecks:
    def test_insurance_ending_early_is_a_warning(self):
        documents = [
            _document("self", "insurance", {"valid_from": "2026-10-01", "valid_to": "2026-10-11"})
        ]
        result = _evaluate(documents)
        assert _by_id(result, "insurance-window-self")[0]["severity"] == "warning"

    def test_a_licence_without_an_idp_is_a_warning(self):
        documents = [_document("self", "licence", {"issuing_country": "India"})]
        result = _evaluate(documents)
        assert _by_id(result, "idp-missing-self")[0]["severity"] == "warning"

    def test_an_idp_on_file_clears_the_warning(self):
        documents = [
            _document("self", "licence", {"issuing_country": "India"}),
            _document("self", "idp", {"expiry": "2027-01-01"}),
        ]
        result = _evaluate(documents)
        assert not _by_id(result, "idp-missing-self")

    def test_a_licence_issued_by_the_destination_needs_no_permit(self):
        documents = [_document("self", "licence", {"issuing_country": "Portugal"})]
        result = _evaluate(documents)
        assert not _by_id(result, "idp-missing-self")

    def test_a_licence_on_a_domestic_trip_needs_no_permit(self):
        documents = [_document("self", "licence", {"issuing_country": "India"})]
        result = _evaluate(documents, origin_country="India", destination_country="India")
        assert not _by_id(result, "idp-missing-self")

    def test_a_document_expiring_during_the_trip_is_flagged(self):
        documents = [_document("self", "vaccination", {"expiry": "2026-10-09"})]
        result = _evaluate(documents)
        assert _by_id(result, "expiring-self-vaccination")[0]["severity"] == "warning"

    def test_a_lapsed_loyalty_card_is_not_worth_a_badge(self):
        documents = [_document("self", "loyalty", {"expiry": "2026-10-09"})]
        result = _evaluate(documents)
        assert not _by_id(result, "expiring-self-loyalty")


class TestBadge:
    def test_missing_passports_only_ask_to_be_checked(self):
        result = _evaluate([])
        assert result["blockers"] == 0
        assert result["warnings"] == 3
        assert result["badge"] == "3 documents to check"
        assert result["badge_tone"] == "warning"

    def test_the_badge_counts_only_blockers_when_present(self):
        documents = [_document("self", "passport", {"expiry": "2026-10-10"})]
        result = _evaluate(documents)
        assert result["blockers"] == 1
        assert result["badge"] == "1 document to fix"
        assert result["badge_tone"] == "blocker"

    def test_the_badge_falls_back_to_warnings(self):
        documents = [
            _document(key, "passport", {"expiry": "2031-04-02"})
            for key in ("self", "spouse:priya", "child:aarav")
        ] + [_document("self", "licence", {"issuing_country": "India"})]
        result = _evaluate(documents)
        assert result["blockers"] == 0
        assert result["badge"] == "1 document to check"

    def test_a_ready_trip_shows_no_badge(self):
        documents = [
            _document(key, "passport", {"expiry": "2031-04-02"})
            for key in ("self", "spouse:priya", "child:aarav")
        ]
        result = _evaluate(documents)
        assert result["badge"] == ""
        assert result["badge_tone"] == ""

    def test_a_trip_without_dates_makes_no_claims(self):
        result = _evaluate([], trip=dict(TRIP, departure_date=""))
        assert result["checks"] == []
        assert result["reason"] == "trip_dates_missing"


class TestProvenance:
    def test_every_check_states_its_rule_and_is_computed(self):
        result = _evaluate([])
        assert result["checks"]
        for check in result["checks"]:
            assert check["origin"] == "computed"
            assert check["rule"]
