"""Pure merge policies for shared durable cache documents."""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def merge_place_documents(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Merge independently observed place metadata, reviews, and photo URLs."""
    left_entry = left.get("entry") if isinstance(left.get("entry"), dict) else {}
    right_entry = right.get("entry") if isinstance(right.get("entry"), dict) else {}
    if _number(right_entry.get("__at__")) >= _number(left_entry.get("__at__")):
        newest, newest_entry, older_entry = right, right_entry, left_entry
    else:
        newest, newest_entry, older_entry = left, left_entry, right_entry

    merged_entry = dict(newest_entry)
    for fields, timestamp in (
        (("reviews", "__reviews_at__"), "__reviews_at__"),
        (("photo_urls", "__photos_at__"), "__photos_at__"),
    ):
        if _number(older_entry.get(timestamp)) > _number(newest_entry.get(timestamp)):
            for field in fields:
                merged_entry.pop(field, None)
            merged_entry.update(
                {field: older_entry[field] for field in fields if field in older_entry}
            )

    merged = dict(newest)
    merged["entry"] = merged_entry
    return merged


def merge_tool_documents(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Keep the tool result with the newest original cache timestamp."""
    right_is_newer = _number(right.get("cached_at")) >= _number(left.get("cached_at"))
    return dict(right if right_is_newer else left)


def merge_cache_documents(
    container: str, left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    if container == "places_cache":
        return merge_place_documents(left, right)
    if container == "tool_cache":
        return merge_tool_documents(left, right)
    raise ValueError(f"unsupported shared cache container: {container}")
