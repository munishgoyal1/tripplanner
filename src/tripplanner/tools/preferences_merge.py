"""Shared, framework-agnostic logic for merging an "About me" free-text blurb
into a user's saved preferences.

Both frontends use this:
  * the Chainlit settings form (``web/app.py``), and
  * the standalone SPA backend (``api.py`` ``POST /preferences``).

Keeping it here (no Chainlit, no FastAPI imports) means the extraction +
additive-overlay rules are single-sourced. The rules are strictly additive:
list fields are unioned, blank scalars are filled, family members are
appended/extended — nothing the user already saved is ever removed.
"""

from __future__ import annotations

from typing import Any

from tripplanner.tools import about_me_extractor

ABOUT_ME_MAX_CHARS = 8000

# Path-aware merge rules for fields extracted from the free-text About-me.
# Anything not listed here falls back to "set only if currently empty".
_ADDITIVE_LIST_PATHS: frozenset[str] = frozenset({
    "interests",
    "dislikes",
    "food_preferences.dietary",
    "food_preferences.cuisine_likes",
    "food_preferences.cuisine_dislikes",
})


def union_keep_existing_case(existing: list[Any], incoming: list[Any]) -> list[str]:
    """Append items from ``incoming`` to ``existing`` with case-insensitive
    dedupe. The casing already saved by the user wins; nothing is removed."""
    out: list[str] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(incoming or []):
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def merge_family_member(existing: dict, incoming: dict) -> dict:
    """Fill in blank scalar fields on ``existing`` and union the list-typed
    sub-fields (dietary/mobility/interests). Never overwrites a populated
    scalar; never removes a list item."""
    merged = dict(existing)
    for key in ("name", "age", "notes"):
        if not merged.get(key) and incoming.get(key) is not None:
            merged[key] = incoming[key]
    for key in ("dietary", "mobility", "interests"):
        if incoming.get(key):
            merged[key] = union_keep_existing_case(
                merged.get(key) or [], incoming.get(key) or []
            )
    return merged


def additive_overlay_extracted(
    prefs: dict[str, Any], extracted: dict[str, Any]
) -> dict[str, Any]:
    """Layer LLM-extracted fields onto saved prefs **additively**.

    Rules (per the user's request "always additive, never remove"):
      * List fields in ``_ADDITIVE_LIST_PATHS`` → union with existing.
      * Scalar fields → only set when the saved value is empty/None. Never
        overwrites an explicit prior value.
      * ``family_members`` → append new entries by (relationship, lowercase
        name). Existing entries get sub-field fills (blanks only) and
        list-typed sub-fields get unioned.

    The extractor may also emit ``_learned_notes_to_append``; the caller
    handles that separately.
    """
    result = dict(prefs)

    # --- 1. nested groups (profile / food / transport / hotel) ----------
    for group in ("profile", "food_preferences", "transport_preferences", "hotel_preferences"):
        new_group = extracted.get(group)
        if not isinstance(new_group, dict):
            continue
        cur_group = dict(result.get(group) or {})
        for sub_key, sub_val in new_group.items():
            path = f"{group}.{sub_key}"
            if path in _ADDITIVE_LIST_PATHS:
                cur_group[sub_key] = union_keep_existing_case(
                    cur_group.get(sub_key) or [], sub_val if isinstance(sub_val, list) else []
                )
            else:  # scalar — fill only when blank
                if cur_group.get(sub_key) in (None, "", [], {}):
                    cur_group[sub_key] = sub_val
        result[group] = cur_group

    # --- 2. top-level scalars (trip_style, budget_level) ----------------
    for key in ("trip_style", "budget_level"):
        if key in extracted and result.get(key) in (None, "", [], {}):
            result[key] = extracted[key]

    # --- 3. top-level lists (interests, dislikes) -----------------------
    for key in ("interests", "dislikes"):
        if key in extracted:
            result[key] = union_keep_existing_case(
                result.get(key) or [], extracted.get(key) or []
            )

    # --- 4. family_members ----------------------------------------------
    new_fams = extracted.get("family_members")
    if isinstance(new_fams, list) and new_fams:
        existing: list[dict] = list(result.get("family_members") or [])
        index: dict[tuple[str, str], int] = {}
        for i, m in enumerate(existing):
            if not isinstance(m, dict):
                continue
            rel = str(m.get("relationship") or "").lower()
            name = str(m.get("name") or "").strip().lower()
            if name:
                index[(rel, name)] = i
        for incoming in new_fams:
            if not isinstance(incoming, dict):
                continue
            rel = str(incoming.get("relationship") or "").lower()
            name = str(incoming.get("name") or "").strip().lower()
            key = (rel, name)
            if name and key in index:
                existing[index[key]] = merge_family_member(existing[index[key]], incoming)
            else:
                existing.append(incoming)
        result["family_members"] = existing

    return result


def flatten_keys(d: dict[str, Any], prefix: str = "") -> list[str]:
    """Flatten the top-level dotted paths for a status message.

    Only goes one level deep (e.g. ``profile.home_city``) which is enough for
    a friendly summary of what changed.
    """
    out: list[str] = []
    for key, val in d.items():
        path = f"{prefix}{key}"
        if isinstance(val, dict):
            for sub in val.keys():
                out.append(f"{path}.{sub}")
        else:
            out.append(path)
    return out


def apply_about_me(
    prefs: dict[str, Any], new_about: str, old_about: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """Store the raw blurb on ``prefs['about_me']`` and, when it changed,
    extract structured fields and overlay them additively.

    Returns ``(updated_prefs, extracted_keys)`` where ``extracted_keys`` is a
    flat list of the dotted paths that were touched (for a friendly summary).
    Mutates a copy — the input ``prefs`` is not modified in place beyond the
    returned dict.
    """
    prefs = dict(prefs)
    new_about = (new_about or "").strip()
    if len(new_about) > ABOUT_ME_MAX_CHARS:
        new_about = new_about[:ABOUT_ME_MAX_CHARS]
    old_about = (old_about or str(prefs.get("about_me") or "")).strip()
    prefs["about_me"] = new_about

    extracted_keys: list[str] = []
    if not new_about or new_about == old_about:
        return prefs, extracted_keys

    extracted = about_me_extractor.extract_about_me(new_about)
    learned_to_append = extracted.pop("_learned_notes_to_append", None)
    if extracted:
        prefs = additive_overlay_extracted(prefs, extracted)
        extracted_keys = flatten_keys(extracted)
    if learned_to_append:
        existing = list(prefs.get("learned_notes") or [])
        seen = {(n.get("note") or "").strip().lower() for n in existing if isinstance(n, dict)}
        for entry in learned_to_append:
            key = entry["note"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            existing.append(entry)
        prefs["learned_notes"] = existing
        extracted_keys.append("learned_notes")

    return prefs, extracted_keys

