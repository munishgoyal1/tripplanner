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
    assert payload["fields"][0]["value"] == "balanced"
    assert payload["fields"][1]["value"] == 2


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
    assert [field["kind"] for field in payload["fields"]] == ["date", "number", "text"]
    assert payload["fields"][0]["value"] == "2026-11-12"
    # An unknown origin stays empty rather than being invented for the traveller.
    assert payload["fields"][2]["value"] == ""
    assert payload["fields"][2]["placeholder"] == "Your city"


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


def test_request_id_is_stable_for_replay() -> None:
    arguments = {
        "question": "Anything different for this trip?",
        "fields_json": json.dumps(_fields()),
    }

    first = extract_input_request(request_trip_input.invoke(arguments))
    second = extract_input_request(request_trip_input.invoke(arguments))

    assert first is not None and second is not None
    assert first["request_id"] == second["request_id"]


def test_request_rejects_choice_without_prefilled_value() -> None:
    fields = _fields()
    del fields[0]["value"]

    result = request_trip_input.invoke(
        {"question": "Choose a pace", "fields_json": json.dumps(fields)}
    )

    assert result.startswith("Invalid trip input request:")
    assert extract_input_request(result) is None


def test_request_rejects_oversized_questionnaire() -> None:
    field = {
        "id": "choice",
        "label": "Choice",
        "kind": "boolean",
        "value": True,
    }
    fields = [{**field, "id": f"choice_{index}"} for index in range(5)]

    result = request_trip_input.invoke(
        {"question": "Too many questions", "fields_json": json.dumps(fields)}
    )

    assert "between 1 and 4 fields" in result
