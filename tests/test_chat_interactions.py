from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from tripplanner.chat_interactions import extract_input_request, request_trip_input


def _fields() -> list[dict]:
    return [
        {
            "id": "pace",
            "label": "Pace",
            "kind": "single",
            "value": "balanced",
            "options": [
                {"value": "easy", "label": "Easy"},
                {"value": "balanced", "label": "Balanced"},
            ],
        },
        {
            "id": "travelers",
            "label": "Travelers",
            "kind": "number",
            "value": 2,
            "min": 1,
            "max": 8,
        },
    ]


def test_request_trip_input_emits_valid_prefilled_contract() -> None:
    result = request_trip_input.invoke(
        {
            "question": "Anything different for this trip?",
            "known_context_json": json.dumps(["Boutique stays", "Vegetarian-friendly"]),
            "fields_json": json.dumps(_fields()),
        }
    )

    payload = extract_input_request(ToolMessage(content=result, tool_call_id="input"))

    assert payload is not None
    assert payload["version"] == 1
    assert len(payload["request_id"]) == 16
    assert payload["known_context"] == ["Boutique stays", "Vegetarian-friendly"]
    assert payload["fields"][0] == {
        "id": "adults",
        "label": "Adults (13+)",
        "kind": "number",
        "value": 2,
        "min": 1,
        "max": 8,
        "step": 1,
    }
    assert payload["fields"][1] == {
        "id": "children",
        "label": "Children (0-12)",
        "kind": "number",
        "value": 0,
        "min": 0,
        "max": 8,
        "step": 1,
    }
    assert payload["fields"][2]["id"] == "party_type"
    assert payload["fields"][2]["value"] == "group"
    assert payload["fields"][3]["value"] == "balanced"


def test_kickoff_can_ask_for_dates_length_and_origin() -> None:
    fields = [
        {"id": "start_date", "label": "Start date", "kind": "date", "value": "2026-11-12"},
        {"id": "days", "label": "Days", "kind": "number", "value": 4, "min": 2, "max": 10},
        {
            "id": "origin",
            "label": "Travelling from",
            "kind": "text",
            "value": "",
            "placeholder": "Your city",
        },
    ]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Confirm a few details", "fields_json": json.dumps(fields)}
        )
    )

    assert payload is not None
    assert [field["kind"] for field in payload["fields"]] == [
        "number", "number", "single", "single", "text", "date",
    ]
    assert payload["fields"][3]["id"] == "travel_scope"
    assert payload["fields"][3]["value"] == "round_trip"
    # An unknown origin stays empty rather than being invented for the traveller.
    assert payload["fields"][4]["value"] == ""
    assert payload["fields"][4]["placeholder"] == "Your city"
    assert payload["fields"][5]["value"] == "2026-11-12"
    assert payload["allow_skip"] is False


def test_kickoff_rejects_a_malformed_date() -> None:
    fields = [{"id": "start_date", "label": "Start date", "kind": "date", "value": "12 Nov"}]

    result = request_trip_input.invoke(
        {"question": "Confirm a few details", "fields_json": json.dumps(fields)}
    )

    assert "Invalid trip input request" in result
    assert extract_input_request(result) is None


def test_known_context_survives_object_shaped_facts() -> None:
    payload = extract_input_request(
        request_trip_input.invoke(
            {
                "question": "Confirm a few details",
                "known_context_json": json.dumps(
                    [{"trip_style": "balanced"}, {"budget_level": "moderate"}, "Vegetarian"]
                ),
                "fields_json": json.dumps(_fields()),
            }
        )
    )

    assert payload is not None
    assert payload["known_context"] == [
        "trip_style: balanced",
        "budget_level: moderate",
        "Vegetarian",
    ]


def test_known_context_overflow_trims_instead_of_losing_the_card() -> None:
    payload = extract_input_request(
        request_trip_input.invoke(
            {
                "question": "Confirm a few details",
                "known_context_json": json.dumps([f"fact {index}" for index in range(9)]),
                "fields_json": json.dumps(_fields()),
            }
        )
    )

    assert payload is not None
    assert payload["known_context"] == [f"fact {index}" for index in range(6)]


def test_extra_fields_are_trimmed_instead_of_losing_the_card() -> None:
    extra = [
        {"id": f"choice_{index}", "label": f"Choice {index}", "kind": "boolean", "value": True}
        for index in range(7)
    ]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Confirm a few details", "fields_json": json.dumps(extra)}
        )
    )

    assert payload is not None
    assert len(payload["fields"]) == 6
    assert [field["id"] for field in payload["fields"][:3]] == [
        "adults", "children", "party_type",
    ]


def test_field_ids_are_derived_and_one_bad_field_does_not_lose_the_card() -> None:
    fields = [
        {"label": "Trip start date", "kind": "date", "value": "2026-11-12"},
        {"label": "Days", "kind": "number", "value": 4, "min": 2, "max": 10},
        {"label": "Broken", "kind": "carousel", "value": "nope"},
    ]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Confirm a few details", "fields_json": json.dumps(fields)}
        )
    )

    assert payload is not None
    assert [field["id"] for field in payload["fields"]] == [
        "adults", "children", "party_type", "trip_start_date", "days",
    ]


def test_request_id_is_stable_for_replay() -> None:
    arguments = {
        "question": "Anything different for this trip?",
        "fields_json": json.dumps(_fields()),
    }

    first = extract_input_request(request_trip_input.invoke(arguments))
    second = extract_input_request(request_trip_input.invoke(arguments))

    assert first is not None and second is not None
    assert first["request_id"] == second["request_id"]


def test_request_drops_a_choice_without_a_prefilled_value() -> None:
    fields = _fields()
    del fields[0]["value"]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Choose a pace", "fields_json": json.dumps(fields)}
        )
    )

    assert payload is not None
    # The unprefilled field is never presented, but it no longer costs the card.
    assert [field["id"] for field in payload["fields"]] == [
        "adults", "children", "party_type",
    ]


def test_request_preserves_explicit_adult_and_child_defaults() -> None:
    fields = [
        {"id": "adults", "label": "Adults", "kind": "number", "value": 2, "min": 1, "max": 10},
        {"id": "children", "label": "Kids", "kind": "number", "value": 2, "min": 0, "max": 6},
    ]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Who is travelling?", "fields_json": json.dumps(fields)}
        )
    )

    assert payload is not None
    assert [(field["id"], field["value"]) for field in payload["fields"]] == [
        ("adults", 2),
        ("children", 2),
        ("party_type", "family"),
    ]
    assert [field["label"] for field in payload["fields"][:2]] == [
        "Adults (13+)",
        "Children (0-12)",
    ]


def test_request_preserves_an_explicit_party_relationship() -> None:
    fields = [
        {"id": "adults", "label": "Adults", "kind": "number", "value": 2, "min": 1, "max": 10},
        {"id": "children", "label": "Kids", "kind": "number", "value": 0, "min": 0, "max": 6},
        {
            "id": "party_type",
            "label": "Trip group",
            "kind": "single",
            "value": "couple",
            "options": [
                {"value": "solo", "label": "Solo"},
                {"value": "couple", "label": "Couple"},
            ],
        },
    ]

    payload = extract_input_request(
        request_trip_input.invoke(
            {"question": "Who is travelling?", "fields_json": json.dumps(fields)}
        )
    )

    assert payload is not None
    assert payload["fields"][2]["value"] == "couple"
    assert [option["value"] for option in payload["fields"][2]["options"]] == [
        "solo", "couple", "family", "friends", "group",
    ]


def test_request_rejects_an_empty_questionnaire() -> None:
    result = request_trip_input.invoke(
        {"question": "Nothing to ask", "fields_json": json.dumps([])}
    )

    assert "at least one field" in result
