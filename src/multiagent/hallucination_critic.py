"""Deterministic hallucination critic for the agent's final reply.

The trip agent occasionally invents prices, hours, URLs, or phone numbers
that never appeared in any tool output — classic LLM padding. This module
walks the final text, extracts the concrete claims that are easy to
fact-check (currency amounts, times, URLs), and verifies each appears
verbatim somewhere in the tool messages from the same turn.

It's deliberately dumb: no LLM call, no fuzzy matching beyond simple
normalisation. Either the claim shows up in the evidence or it doesn't.
Anything not in the supported claim families (history, weather narrative,
opinions) is left alone so we don't false-positive on prose.

Returns a list of short strings describing each unverified claim, or an
empty list when everything checks out. Callers append the result as a
"Heads up" footer to the user-facing reply when non-empty.
"""

from __future__ import annotations

import re
from typing import Iterable

from langchain_core.messages import BaseMessage


# Currency amount: $42, € 1,200.50, ₹3500, USD 99, INR 12345.
# The digit core accepts either comma/period-grouped thousands (1,200.50) OR a
# plain run of digits (70000) — without the plain-run branch, a bare number
# like INR 70000 would truncate to INR 700 (\d{1,3} grabs the first 3 digits
# then finds no group separator). We keep it permissive so we catch anything
# the agent might write.
_AMOUNT = r"\d{1,3}(?:[,\.]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_PRICE_RE = re.compile(
    rf"""(?ix)
    (?:
      [\$€£¥₹₩]\s?(?:{_AMOUNT})
      |
      (?:USD|EUR|GBP|INR|JPY|AED|SGD|AUD|CAD)\s?(?:{_AMOUNT})
    )
    """,
)

# 12-hour or 24-hour clock times: 9am, 10:30 PM, 14:00, 18:45.
_TIME_RE = re.compile(
    r"""(?ix)
    \b
    (?:
      (?:[01]?\d|2[0-3]) : [0-5]\d (?:\s?[ap]m)?
      |
      (?:1[0-2]|0?[1-9]) \s?[ap]m
    )
    \b
    """,
)

# URLs the agent might cite — http(s)://… or bare host with TLD.
_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+", re.IGNORECASE)


def _normalise(text: str) -> str:
    """Lowercase + strip extra whitespace + drop common thousands separators."""
    out = text.lower()
    out = out.replace("\u00a0", " ")
    # Treat $ 42 same as $42 by collapsing the space.
    out = re.sub(r"([\$€£¥₹₩])\s+", r"\1", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def _extract_evidence(messages: Iterable[BaseMessage]) -> str:
    """Concatenate the text of every tool message in this turn."""
    chunks: list[str] = []
    for msg in messages:
        if getattr(msg, "type", None) == "tool":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                # Some tool messages carry list[dict] (e.g. multi-part).
                for item in content:
                    if isinstance(item, dict):
                        chunks.append(str(item.get("text") or item))
                    else:
                        chunks.append(str(item))
    return _normalise(" || ".join(chunks))


def _claim_in_evidence(claim: str, evidence: str) -> bool:
    """Verbatim membership check after light normalisation.

    For prices we also strip the optional space between currency symbol and
    digits because the agent may format it either way.
    """
    needle = _normalise(claim)
    if needle in evidence:
        return True
    # Try with currency symbol attached to digits.
    if _PRICE_RE.fullmatch(claim.strip()):
        tight = re.sub(r"([\$€£¥₹₩])\s+", r"\1", needle)
        if tight in evidence:
            return True
    return False


def critique(final_text: str, messages: Iterable[BaseMessage]) -> list[str]:
    """Return a list of unverified claim descriptions; empty when clean.

    ``messages`` is the full message list from the agent turn (the same list
    LangGraph maintains in state); we filter to tool messages internally.
    """
    if not final_text or not final_text.strip():
        return []
    evidence = _extract_evidence(messages)
    if not evidence:
        # If the agent answered without calling any tool, we have nothing
        # to verify against — assume it's a conversational reply.
        return []

    issues: list[str] = []
    seen: set[str] = set()

    for match in _PRICE_RE.findall(final_text):
        claim = match.strip()
        key = ("price", _normalise(claim))
        if key in seen:
            continue
        seen.add(key)
        if not _claim_in_evidence(claim, evidence):
            issues.append(f"price {claim} was not found in any tool result")

    for match in _TIME_RE.findall(final_text):
        claim = match.strip()
        key = ("time", _normalise(claim))
        if key in seen:
            continue
        seen.add(key)
        if not _claim_in_evidence(claim, evidence):
            issues.append(f"time {claim} was not found in any tool result")

    for match in _URL_RE.findall(final_text):
        # Trim trailing punctuation that often follows a URL in prose.
        claim = match.rstrip(".,);:'\"")
        key = ("url", _normalise(claim))
        if key in seen:
            continue
        seen.add(key)
        if not _claim_in_evidence(claim, evidence):
            issues.append(f"URL {claim} was not found in any tool result")

    return issues


def format_heads_up(issues: list[str]) -> str:
    """Render the critic output as a short markdown block, or ''."""
    if not issues:
        return ""
    bullets = "\n".join(f"- {i}" for i in issues)
    return (
        "\n\n---\n**Heads up — please double-check:**\n"
        f"{bullets}\n"
    )
