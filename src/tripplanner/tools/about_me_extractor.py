"""LLM-based extractor that converts a user's free-text "About me" blurb
into a partial preferences dict ready to deep-merge over the saved state.

Returned dict only contains keys the model could confidently extract — keys
it didn't see are OMITTED, so deep-merge won't blank out fields the user
didn't mention in the new text.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# Allowed enum values (kept in sync with _DEFAULT_PREFS / ChatSettings widgets).
_TRIP_STYLES = {"balanced", "relaxed", "adventurous", "cultural", "foodie", "luxury", "budget"}
_BUDGET_LEVELS = {"budget", "moderate", "comfortable", "luxury"}
_FLIGHT_CLASSES = {"economy", "premium_economy", "business", "first"}
_ROAD_TRANSPORT = {"own_car", "taxi", "either"}
_AGE_BANDS = {"under_20", "20-30", "30-40", "40-50", "50-60", "60+"}
_VALID_RELATIONSHIPS = {
    "self", "spouse", "partner", "child", "parent", "sibling", "friend", "other",
}

_SYSTEM_PROMPT = """You extract structured travel preferences from a user's free-text
"About me" blurb.

Return STRICT JSON ONLY (no markdown, no commentary). Use exactly these keys —
do NOT invent new ones. OMIT any field the user did not mention; do not return
null, "", [], or {} placeholders for missing data.

Allowed keys and types:

- profile.display_name        string (first name)
- profile.home_city           string
- profile.home_area           string (neighborhood, suburb, or usual pickup area)
- profile.home_country        string
- profile.age_band            one of: "under_20", "20-30", "30-40", "40-50", "50-60", "60+"
- profile.occupation          string
- trip_style                  one of: "balanced", "relaxed", "adventurous", "cultural", "foodie", "luxury", "budget"
- budget_level                one of: "budget", "moderate", "comfortable", "luxury"
- interests                   list of short strings (e.g. ["hiking", "museums"])
- dislikes                    list of short strings
- food_preferences.dietary             list of strings (e.g. ["vegetarian", "no-beef"])
- food_preferences.cuisine_likes       list of strings
- food_preferences.cuisine_dislikes    list of strings
- transport_preferences.flight_class   one of the flight classes above
- transport_preferences.prefer_direct_flights   boolean
- transport_preferences.preferred_road_transport one of: "own_car", "taxi", "either"
- transport_preferences.max_continuous_drive_min integer minutes before a break
- transport_preferences.road_break_duration_min integer minutes per break
- transport_preferences.road_break_preferences list of strings (e.g. ["snack", "restroom"])
- hotel_preferences.star_rating_min    integer 1..5
- family_members              list of objects with keys:
    - relationship   one of: "self", "spouse", "partner", "child", "parent",
                     "sibling", "friend", "other"
    - name           string (optional if not given)
    - age            integer (optional)
    - dietary        list of strings (optional)
    - mobility       list of strings (optional)
    - interests      list of strings (optional)
    - notes          string (optional)
- learned_notes               list of short string observations that don't fit
                              any other field (kept as free-form notes)

Rules:
- Convert an explicit age like "I'm 43" into profile.age_band "40-50".
- If the user says "me - age 43" treat that as a family_members entry with
  relationship="self" AND set profile.age_band.
- Family members: always include a relationship. Names should be capitalised.
- Interests / dislikes / cuisines: short noun phrases, lowercase preferred.
- Be conservative — only include a field if the text clearly supports it.
- If the text is unrelated to travel preferences, return {}.

STRONG-SIGNAL RULE (very important):
The extracted dict is **ADDED** to the user's saved preferences — it can never
be used to delete a prior value. So:
  * Only emit a `likes`-style entry (interests / cuisine_likes) when the text
    contains a clear positive ("love", "favourite", "always pick", a repeated
    mention across multiple trips). Don't emit on mild praise.
  * Only emit a `dislikes`-style entry (dislikes / cuisine_dislikes) when the
    text contains a clearly strong negative ("hate", "never want", "always
    avoid", "can't stand"). Mild language like "didn't really like" or
    "wasn't a fan" is NOT strong enough — OMIT.
  * For scalar fields the user already saved (e.g. home_city), the merge
    layer will keep the existing value. Still emit your best extraction —
    the merge layer chooses, not you.
  * NEVER imagine a "removal" operation. There is no way to remove a saved
    interest via this extraction. If the user contradicts a prior like,
    simply omit it; do not add to dislikes unless the language is strong.

Output: a single JSON object. No markdown fence. No prose."""


def _coerce_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _coerce_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        items = [v]
    elif isinstance(v, (list, tuple)):
        items = list(v)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = _coerce_str(item)
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _coerce_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_enum(v: Any, allowed: set[str]) -> str | None:
    s = _coerce_str(v)
    if s is None:
        return None
    key = s.lower().replace(" ", "_").replace("-", "_")
    # Try direct match against lowercase versions of allowed values
    for a in allowed:
        if a.lower().replace("-", "_") == key:
            return a
    return None


def _sanitize_family(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list):
        return None
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rel = (_coerce_str(entry.get("relationship")) or "").lower()
        if rel not in _VALID_RELATIONSHIPS:
            rel = "other"
        member: dict[str, Any] = {"relationship": rel}
        name = _coerce_str(entry.get("name"))
        if name:
            member["name"] = name
        age = _coerce_int(entry.get("age"))
        if age is not None:
            member["age"] = age
        for list_key in ("dietary", "mobility", "interests"):
            items = _coerce_str_list(entry.get(list_key))
            if items:
                member[list_key] = items
        notes = _coerce_str(entry.get("notes"))
        if notes:
            member["notes"] = notes
        out.append(member)
    return out or None


def _sanitize_extraction(raw: dict[str, Any]) -> dict[str, Any]:
    """Filter the LLM output down to known keys with valid types.

    Returns a dict suitable for ``_deep_merge`` over the saved prefs. Keys
    the model didn't return are not present in the result, so they won't
    overwrite existing values.
    """
    if not isinstance(raw, dict):
        return {}

    out: dict[str, Any] = {}

    # profile.*
    profile_in = raw.get("profile") if isinstance(raw.get("profile"), dict) else {}
    profile_out: dict[str, Any] = {}
    for key in ("display_name", "home_city", "home_area", "home_country", "occupation"):
        v = _coerce_str(profile_in.get(key))
        if v is not None:
            profile_out[key] = v
    age_band = _coerce_enum(profile_in.get("age_band"), _AGE_BANDS)
    if age_band:
        profile_out["age_band"] = age_band
    if profile_out:
        out["profile"] = profile_out

    # top-level enums
    trip_style = _coerce_enum(raw.get("trip_style"), _TRIP_STYLES)
    if trip_style:
        out["trip_style"] = trip_style
    budget_level = _coerce_enum(raw.get("budget_level"), _BUDGET_LEVELS)
    if budget_level:
        out["budget_level"] = budget_level

    # top-level lists
    interests = _coerce_str_list(raw.get("interests")) if "interests" in raw else None
    if interests:
        out["interests"] = interests
    dislikes = _coerce_str_list(raw.get("dislikes")) if "dislikes" in raw else None
    if dislikes:
        out["dislikes"] = dislikes

    # food_preferences.*
    food_in = raw.get("food_preferences") if isinstance(raw.get("food_preferences"), dict) else {}
    food_out: dict[str, Any] = {}
    for key in ("dietary", "cuisine_likes", "cuisine_dislikes"):
        if key in food_in:
            items = _coerce_str_list(food_in.get(key))
            if items:
                food_out[key] = items
    if food_out:
        out["food_preferences"] = food_out

    # transport_preferences.*
    trans_in = raw.get("transport_preferences")
    trans_in = trans_in if isinstance(trans_in, dict) else {}
    trans_out: dict[str, Any] = {}
    fc = _coerce_enum(trans_in.get("flight_class"), _FLIGHT_CLASSES)
    if fc:
        trans_out["flight_class"] = fc
    if "prefer_direct_flights" in trans_in:
        trans_out["prefer_direct_flights"] = bool(trans_in["prefer_direct_flights"])
    road_transport = _coerce_enum(
        trans_in.get("preferred_road_transport"), _ROAD_TRANSPORT
    )
    if road_transport:
        trans_out["preferred_road_transport"] = road_transport
    for key in ("max_continuous_drive_min", "road_break_duration_min"):
        minutes = _coerce_int(trans_in.get(key))
        if minutes is not None:
            trans_out[key] = max(10, min(480, minutes))
    road_breaks = _coerce_str_list(trans_in.get("road_break_preferences"))
    if road_breaks:
        trans_out["road_break_preferences"] = road_breaks
    if trans_out:
        out["transport_preferences"] = trans_out

    # hotel_preferences.star_rating_min
    hotel_in = raw.get("hotel_preferences")
    hotel_in = hotel_in if isinstance(hotel_in, dict) else {}
    star = _coerce_int(hotel_in.get("star_rating_min"))
    if star is not None:
        out["hotel_preferences"] = {"star_rating_min": max(1, min(5, star))}

    # family_members (REPLACE wholesale when present and non-empty)
    fams = _sanitize_family(raw.get("family_members"))
    if fams:
        out["family_members"] = fams

    # learned_notes — accept either ["plain string", ...] or list of dicts
    notes_raw = raw.get("learned_notes")
    if isinstance(notes_raw, list):
        cleaned: list[dict[str, Any]] = []
        for item in notes_raw:
            if isinstance(item, dict):
                text = _coerce_str(item.get("note"))
            else:
                text = _coerce_str(item)
            if text:
                cleaned.append({"note": text, "source": "stated"})
        if cleaned:
            out["_learned_notes_to_append"] = cleaned

    return out


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fence(s: str) -> str:
    s = _JSON_FENCE_RE.sub("", s).strip()
    # Last-ditch: find first { and last }
    if not s.startswith("{"):
        i = s.find("{")
        if i >= 0:
            s = s[i:]
    if not s.endswith("}"):
        i = s.rfind("}")
        if i >= 0:
            s = s[: i + 1]
    return s


def extract_about_me(text: str) -> dict[str, Any]:
    """Call the LLM to extract structured preferences from a free-text blurb.

    Returns a dict ready for ``_deep_merge`` over saved prefs. On any error
    (missing config, network failure, invalid JSON), logs a warning and
    returns ``{}`` so the caller's save still succeeds.

    The returned dict may contain a special key ``_learned_notes_to_append``
    holding learned-note entries the caller should APPEND (not overwrite).
    """
    text = (text or "").strip()
    if not text:
        return {}

    # Lazy import so test files that don't touch the LLM can still import this module.
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import AzureChatOpenAI

        from tripplanner.config import get_settings
    except Exception as exc:  # pragma: no cover - import errors are environmental
        log.warning("about_me extractor: imports failed (%s); skipping", exc)
        return {}

    try:
        s = get_settings()
        llm = AzureChatOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            azure_deployment=s.azure_openai_deployment,
            api_version=s.azure_openai_api_version,
            temperature=0.0,
        )
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=text),
            ]
        )
    except Exception as exc:
        log.warning("about_me extractor: LLM call failed (%s); skipping", exc)
        return {}

    content = getattr(response, "content", "")
    if not isinstance(content, str):
        content = str(content)

    try:
        parsed = json.loads(_strip_fence(content))
    except json.JSONDecodeError as exc:
        log.warning("about_me extractor: model returned non-JSON (%s); skipping", exc)
        return {}

    return _sanitize_extraction(parsed)

