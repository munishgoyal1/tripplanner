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


def _validate_field(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Each input field must be an object")
    field_id = _short_text(raw.get("id"), name="field id", limit=40)
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
    if not isinstance(fields, list) or not 1 <= len(fields) <= 4:
        raise ValueError("input requests must contain between 1 and 4 fields")
    clean_fields = [_validate_field(field) for field in fields]
    ids = [field["id"] for field in clean_fields]
    if len(ids) != len(set(ids)):
        raise ValueError("input field ids must be unique")

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

    Use only in interactive planning mode. ``fields_json`` is a JSON array of 1-4
    fields. Supported kinds are ``single``, ``multi``, ``boolean``, ``number``,
    ``text``, and ``date``. Every field must include a sensible prefilled ``value``.
    Choice fields also include 2-6 ``options`` with ``value``, ``label``, and optional
    ``detail``. Use ``date`` (ISO ``YYYY-MM-DD``) for a start date, ``number`` for trip
    length, and ``text`` for an origin city, leaving its value empty when none is known.
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
