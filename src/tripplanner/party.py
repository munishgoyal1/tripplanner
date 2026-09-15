"""Shared party counts; ages and unclassified prose are not headcounts."""

import math
import re


def party_counts(value) -> dict[str, int]:
    words = {
        "adults": r"adults?",
        "children": r"children|child|kids?",
        "infants": r"infants?|babies|baby",
    }
    if isinstance(value, dict):
        return {key: int(value[key]) for key in words if str(value.get(key, "")).isdigit()}
    text = str(value or "")
    counts = {}
    for key, pattern in words.items():
        matches = re.findall(rf"(?<![\d.])\b(\d+)\s+(?:{pattern})\b", text, re.I)
        if matches:
            counts[key] = sum(map(int, matches))
    for match in re.finditer(r"(?<![\d.])\b(\d+)\s+(?:elderly|seniors?)\b", text, re.I):
        if not re.search(
            r"\b(?:including|includes?|of whom)\b[^,;]*$", text[: match.start()], re.I
        ):
            counts["adults"] = counts.get("adults", 0) + int(match[1])
    return counts


def party_size(value) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if math.isfinite(value) and value > 0 and int(value) == value else None
    counts = party_counts(value)
    if counts:
        return (sum(counts.values()) or None) if "adults" in counts else None
    text = str(value or "").strip()
    match = re.fullmatch(
        r"(\d+)(?:\s+(?:people|persons?|travelers?|travellers?|passengers?|pax))?", text, re.I
    )
    return (int(match[1]) or None) if match else None
