"""Structured, backward-compatible input requests for assistant turns."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from langchain_core.tools import tool

_INPUT_REQUEST_PREFIX = "TRIP_INPUT_REQUEST:"
_FIELD_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FIELD_KINDS = {"single", "multi", "boolean", "number", "text", "date"}
_ADULT_FIELD_IDS = {"adults", "adult_travelers", "adult_travellers", "travelers", "travellers"}
_CHILD_FIELD_IDS = {"children", "child_travelers", "child_travellers", "kids"}
_PARTY_TYPE_FIELD_IDS = {"party_type", "group_type", "travel_party", "trip_group"}
_PARTY_TYPE_OPTIONS = [
    {"value": "solo", "label": "Solo"},
    {"value": "couple", "label": "Couple"},
    {"value": "family", "label": "Family"},
    {"value": "friends", "label": "Friends"},
    {"value": "group", "label": "Other group"},
]


def _short_text(value: Any, *, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return text


def _validate_option(raw: Any, field_id: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"Options for {field_id} must be objects")
    option = {
        "value": _short_text(raw.get("value"), name=f"{field_id} option value", limit=80),
        "label": _short_text(raw.get("label"), name=f"{field_id} option label", limit=80),
    }
    detail = raw.get("detail")
    if detail:
        option["detail"] = _short_text(
            detail, name=f"{field_id} option detail", limit=160
        )
    return option


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if text and not text[0].isalpha():
        text = f"field_{text}"
    return text[:40].strip("_")


def _validate_field(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Each input field must be an object")
    # The id is a machine key the model often omits; the label already carries it.
    field_id = _slug(raw.get("id")) or _slug(raw.get("label"))
    if not _FIELD_ID.fullmatch(field_id):
        raise ValueError("Field ids must use lower-case letters, digits, and underscores")
    kind = raw.get("kind")
    if kind not in _FIELD_KINDS:
        raise ValueError(f"Unsupported field kind for {field_id}")
    if "value" not in raw:
        raise ValueError(f"{field_id} must include a prefilled value")

    field: dict[str, Any] = {
        "id": field_id,
        "label": _short_text(raw.get("label"), name=f"{field_id} label", limit=100),
        "kind": kind,
        "value": raw["value"],
    }
    if kind in {"single", "multi"}:
        raw_options = raw.get("options")
        if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 6:
            raise ValueError(f"{field_id} must have between 2 and 6 options")
        options = [_validate_option(option, field_id) for option in raw_options]
        option_values = {option["value"] for option in options}
        value = raw["value"]
        selected = value if isinstance(value, list) else [value]
        if kind == "single" and len(selected) != 1:
            raise ValueError(f"{field_id} must have one selected value")
        if kind == "multi" and not isinstance(value, list):
            raise ValueError(f"{field_id} must use a list value")
        if not set(selected).issubset(option_values):
            raise ValueError(f"{field_id} contains an unknown selected value")
        field["options"] = options
    elif kind == "boolean":
        if not isinstance(raw["value"], bool):
            raise ValueError(f"{field_id} must use a boolean value")
    elif kind in {"text", "date"}:
        value = raw["value"]
        if not isinstance(value, str):
            raise ValueError(f"{field_id} must use a string value")
        # An empty string is how a prefilled field says "not answered yet", so a
        # missing origin or an undecided date stays askable without inventing one.
        text = value.strip()
        if len(text) > 80:
            raise ValueError(f"{field_id} must be at most 80 characters")
        if kind == "date" and text and not _ISO_DATE.fullmatch(text):
            raise ValueError(f"{field_id} must use an ISO YYYY-MM-DD date")
        field["value"] = text
        placeholder = raw.get("placeholder")
        if placeholder:
            field["placeholder"] = _short_text(
                placeholder, name=f"{field_id} placeholder", limit=60
            )
    else:
        value = raw["value"]
        minimum = raw.get("min", 1)
        maximum = raw.get("max", 12)
        step = raw.get("step", 1)
        if not all(isinstance(item, int) for item in (value, minimum, maximum, step)):
            raise ValueError(f"{field_id} number values must be integers")
        if step < 1 or minimum > value or value > maximum or maximum - minimum > 50:
            raise ValueError(f"{field_id} has an invalid numeric range")
        field.update({"min": minimum, "max": maximum, "step": step})
    return field


def _context_line(value: Any) -> str:
    """Render one already-applied fact as a short line.

    The model reasonably emits ``{"trip_style": "balanced"}`` as often as a plain
    string, and rejecting that shape used to discard the entire card.
    """
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, dict):
        text = ", ".join(
            f"{key}: {item}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        )
    elif isinstance(value, (list, tuple)):
        text = ", ".join(_context_line(item) for item in value)
    elif isinstance(value, bool) or value is None:
        text = ""
    else:
        text = str(value).strip()
    return text[:120].strip()


def _with_party_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reserve canonical trip-party controls without trusting model field selection."""
    adults = next(
        (
            field for field in fields
            if field["id"] in _ADULT_FIELD_IDS and field["kind"] == "number"
        ),
        None,
    )
    children = next(
        (
            field for field in fields
            if field["id"] in _CHILD_FIELD_IDS and field["kind"] == "number"
        ),
        None,
    )
    party_type = next(
        (
            field for field in fields
            if field["id"] in _PARTY_TYPE_FIELD_IDS and field["kind"] == "single"
        ),
        None,
    )
    adult_field = {
        **(adults or {"kind": "number", "value": 1, "min": 1, "max": 12, "step": 1}),
        "id": "adults",
        "label": "Adults (13+)",
        "min": 1,
    }
    child_field = {
        **(children or {"kind": "number", "value": 0, "min": 0, "max": 8, "step": 1}),
        "id": "children",
        "label": "Children (0-12)",
        "min": 0,
    }
    adult_count = int(adult_field["value"])
    child_count = int(child_field["value"])
    inferred_party = "family" if child_count else "solo" if adult_count == 1 else "group"
    party_value = party_type.get("value") if party_type else inferred_party
    if party_value not in {option["value"] for option in _PARTY_TYPE_OPTIONS}:
        party_value = inferred_party
    party_field = {
        "id": "party_type",
        "label": "Trip group",
        "kind": "single",
        "value": party_value,
        "options": _PARTY_TYPE_OPTIONS,
    }
    party_ids = _ADULT_FIELD_IDS | _CHILD_FIELD_IDS | _PARTY_TYPE_FIELD_IDS
    remaining = [field for field in fields if field["id"] not in party_ids]
    return [adult_field, child_field, party_field, *remaining][:6]


def build_input_request(
    question: str,
    known_context: Any,
    fields: Any,
    *,
    submit_label: str = "Use these and continue",
    allow_skip: bool = True,
) -> dict[str, Any]:
    """Validate and normalize one compact assistant input request."""
    clean_question = _short_text(question, name="question", limit=240)
    clean_submit = _short_text(submit_label, name="submit label", limit=60)
    if not isinstance(known_context, list):
        raise ValueError("known context must be a list")
    # Context is cosmetic, so an over-long list is trimmed rather than costing
    # the traveller the whole card.
    clean_context = [line for line in map(_context_line, known_context) if line][:6]
    if not isinstance(fields, list) or not fields:
        raise ValueError("input requests must contain at least one field")
    # Six keeps the card compact. One malformed field is skipped rather than
    # costing the traveller the whole review, which is how it went missing before.
    clean_fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for field in fields[:6]:
        try:
            clean = _validate_field(field)
        except ValueError:
            continue
        while clean["id"] in seen_ids:
            clean["id"] = f"{clean['id'][:37]}_{len(seen_ids)}"
        seen_ids.add(clean["id"])
        clean_fields.append(clean)
    if not clean_fields:
        raise ValueError("input requests must contain at least one usable field")
    clean_fields = _with_party_fields(clean_fields)
    identity = json.dumps(
        {"question": clean_question, "fields": clean_fields},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "version": 1,
        "request_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "question": clean_question,
        "known_context": clean_context,
        "fields": clean_fields,
        "submit_label": clean_submit,
        "allow_skip": bool(allow_skip),
    }


@tool
def request_trip_input(
    question: str,
    fields_json: str,
    known_context_json: str = "[]",
    submit_label: str = "Use these and continue",
    allow_skip: bool = True,
) -> str:
    """Present one compact, prefilled input request when critical trip facts are unresolved.

    Use for the one new-trip review. ``fields_json`` is a JSON array of 1-6
    fields. Supported kinds are ``single``, ``multi``, ``boolean``, ``number``,
    ``text``, and ``date``. Every field must include a sensible prefilled ``value``.
    Choice fields also include 2-6 ``options`` with ``value``, ``label``, and optional
    ``detail``. Use ``date`` (ISO ``YYYY-MM-DD``) for a start date, ``number`` for trip
    length, and ``text`` for an origin city, leaving its value empty when none is known.
    Always provide ``adults`` (ages 13+) and ``children`` (ages 0-12) number fields
    plus a ``party_type`` single choice (solo/couple/family/friends/group), prefilling
    explicit trip facts first and the user's usual party second. The validator supplies
    safe 1/0 and neutral group defaults when fields are omitted.
    ``known_context_json`` lists the saved preferences or inferred facts already
    applied, as short strings such as ``["Balanced pace", "Moderate budget"]``.
    """
    try:
        fields = json.loads(fields_json)
        known_context = json.loads(known_context_json)
        payload = build_input_request(
            question,
            known_context,
            fields,
            submit_label=submit_label,
            allow_skip=allow_skip,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return f"Invalid trip input request: {exc}"
    return _INPUT_REQUEST_PREFIX + json.dumps(payload, ensure_ascii=False)


def extract_input_request(output: Any) -> dict[str, Any] | None:
    """Return a validated request embedded in a tool result, if present."""
    content = output if isinstance(output, str) else getattr(output, "content", None)
    if not isinstance(content, str) or not content.startswith(_INPUT_REQUEST_PREFIX):
        return None
    try:
        payload = json.loads(content[len(_INPUT_REQUEST_PREFIX):])
        return build_input_request(
            payload.get("question"),
            payload.get("known_context"),
            payload.get("fields"),
            submit_label=payload.get("submit_label", "Use these and continue"),
            allow_skip=payload.get("allow_skip", True),
        )
    except (json.JSONDecodeError, AttributeError, ValueError):
        return None
