"""Read a travel document once, propose fields, keep nothing.

The bytes handed to this module exist for the length of one request. They are
never written to disk, never written to a temporary file, and never logged. No
caller receives a path back, because none is created. What comes out is a list
of *proposals* — each field with the confidence the extractor had — which the
person then confirms, corrects, or discards before anything is stored.

Accepted input in this stage is a photo (JPEG, PNG, HEIC) or pasted text. A PDF
is refused here on purpose: PDF handling belongs with booking confirmations,
and silently accepting one now would mean guessing at its text.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any

from tripplanner.web.travel_documents import (
    DOCUMENT_TYPES,
    FIELD_ALLOWLIST,
    TYPE_LABELS,
    sanitize_fields,
)

log = logging.getLogger(__name__)

MAX_BYTES = 6 * 1024 * 1024
MAX_TEXT_CHARS = 8000

_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"}

FIELD_LABELS: dict[str, str] = {
    "holder_name": "Name",
    "issuing_country": "Issuing country",
    "nationality": "Nationality",
    "number_last4": "Document number",
    "date_of_birth": "Date of birth",
    "expiry": "Expiry",
    "destination_country": "Valid for",
    "entry_type": "Entries",
    "valid_from": "Valid from",
    "valid_to": "Valid to",
    "provider": "Provider",
    "policy_reference": "Policy number",
    "medical_cover_amount": "Medical cover",
    "currency": "Currency",
    "assistance_phone": "Assistance line",
    "vaccine": "Vaccine",
    "administered_on": "Given on",
    "certificate_reference": "Certificate",
    "categories": "Categories",
    "linked_licence": "Linked licence",
    "program": "Programme",
    "membership_reference": "Membership",
    "tier": "Tier",
}

_MASKED_FIELDS = {"number_last4"}


class ExtractionError(ValueError):
    """The submitted input cannot be read as a travel document."""


def detect_image_type(payload: bytes) -> str:
    """Identify an image by its magic bytes, never by its filename.

    Raises :class:`ExtractionError` for anything that is not a photo, which
    includes the formats that carry executable or fetching behaviour (SVG,
    HTML) and the ones that hide further files (archives).
    """
    if len(payload) < 12:
        raise ExtractionError("That file is too small to be a document photo.")
    head = payload[:12]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[4:8] == b"ftyp" and head[8:12].lower() in _HEIC_BRANDS:
        return "image/heic"
    if head.startswith(b"%PDF"):
        raise ExtractionError(
            "PDFs are not read yet. Photograph the page, or paste the text instead."
        )
    lowered = head.lower()
    if lowered.startswith((b"<svg", b"<?xml", b"<!doctype", b"<html")):
        raise ExtractionError("That looks like a web file, not a document photo.")
    if head.startswith((b"PK\x03\x04", b"Rar!", b"\x1f\x8b", b"7z\xbc\xaf", b"MZ")):
        raise ExtractionError("That looks like an archive or a program, not a document photo.")
    raise ExtractionError("That file is not a JPEG, PNG, or HEIC photo.")


def decode_payload(content_base64: str) -> bytes:
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExtractionError("The upload could not be decoded.") from exc
    if not payload:
        raise ExtractionError("The upload was empty.")
    if len(payload) > MAX_BYTES:
        raise ExtractionError("That photo is larger than 6 MB. Send a smaller one.")
    return payload


def _prompt(document_type: str) -> str:
    allowed = sorted(FIELD_ALLOWLIST[document_type])
    return (
        "You read one travel document and return JSON only. "
        f"The document is a {TYPE_LABELS[document_type].lower()}.\n"
        f"Return an object with exactly these keys: {json.dumps(allowed)}.\n"
        "Alongside it return an object 'confidence' with the same keys, each a "
        "number from 0 to 1 describing how clearly you could read that field.\n"
        "Shape: {\"fields\": {...}, \"confidence\": {...}}.\n"
        "Rules: dates use YYYY-MM-DD. Countries use their common English name. "
        "For 'number_last4' return only the last four characters of the document "
        "number and nothing else. Omit any key you cannot read rather than "
        "guessing it. Never invent a value."
    )


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _invoke(document_type: str, content: Any) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import AzureChatOpenAI

    from tripplanner.config import get_settings

    settings = get_settings()
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        temperature=0.0,
    )
    response = llm.invoke(
        [SystemMessage(content=_prompt(document_type)), HumanMessage(content=content)]
    )
    raw = getattr(response, "content", "")
    if not isinstance(raw, str):
        raw = str(raw)
    parsed = json.loads(_strip_fence(raw))
    return parsed if isinstance(parsed, dict) else {}


def _proposals(document_type: str, parsed: dict[str, Any]) -> list[dict[str, Any]]:
    fields = sanitize_fields(document_type, parsed.get("fields"))
    scores = parsed.get("confidence") if isinstance(parsed.get("confidence"), dict) else {}
    proposals: list[dict[str, Any]] = []
    for key, value in fields.items():
        try:
            confidence = round(float(scores.get(key, 0.9)), 3)
        except (TypeError, ValueError):
            confidence = 0.9
        proposals.append(
            {
                "key": key,
                "label": FIELD_LABELS.get(key, key.replace("_", " ").capitalize()),
                "value": value,
                "masked": key in _MASKED_FIELDS,
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )
    proposals.sort(key=lambda item: sorted(FIELD_ALLOWLIST[document_type]).index(item["key"]))
    return proposals


def extract(
    document_type: str, *, content_base64: str = "", text: str = ""
) -> dict[str, Any]:
    """Propose the fields of one document. Nothing is persisted here."""
    kind = str(document_type or "").strip().lower()
    if kind not in DOCUMENT_TYPES:
        raise ExtractionError(f"Unknown document type: {kind or '(missing)'}")

    if content_base64:
        payload = decode_payload(content_base64)
        media_type = detect_image_type(payload)
        content: Any = [
            {"type": "text", "text": f"Read this {TYPE_LABELS[kind].lower()}."},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,"
                    + base64.b64encode(payload).decode("ascii")
                },
            },
        ]
        source_kind = "image"
        del payload
    else:
        pasted = str(text or "").strip()
        if not pasted:
            raise ExtractionError("Send a photo or paste the document text.")
        content = pasted[:MAX_TEXT_CHARS]
        source_kind = "text"

    try:
        parsed = _invoke(kind, content)
    except json.JSONDecodeError as exc:
        log.warning("document extract: model returned non-JSON for type=%s (%s)", kind, exc)
        raise ExtractionError("The document could not be read. Enter the details yourself.")
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a read failure
        log.warning("document extract: read failed for type=%s (%s)", kind, type(exc).__name__)
        raise ExtractionError("The document could not be read. Enter the details yourself.")

    proposals = _proposals(kind, parsed)
    if not proposals:
        raise ExtractionError("Nothing readable was found. Enter the details yourself.")
    return {"type": kind, "source_kind": source_kind, "fields": proposals}
