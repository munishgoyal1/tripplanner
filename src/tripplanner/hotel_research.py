"""Carry city-specific hotel evidence from tool results into the saved plan."""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_REASONS = {
    "no_results": "No properties returned by the hotel and place searches.",
    "no_suitable_property": "No matching hotel with a verified identity and location was found.",
    "provider_unavailable": "Hotel research was incomplete because a provider was unavailable.",
    "rate_and_availability_unverified": "Properties found; a suitable hotel still needs selection.",
    "offers_returned": "Hotel offers were found; a suitable hotel still needs selection.",
}


def current_hotel_research(messages):
    calls = {}
    research = {}
    for message in messages:
        if isinstance(message, HumanMessage):
            calls.clear()
            research.clear()
        elif isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["name"] == "search_hotels":
                    calls[call["id"]] = call["args"]
        elif isinstance(message, ToolMessage) and message.tool_call_id in calls:
            try:
                result = json.loads(message.content)
            except (ValueError, TypeError):
                continue
            row = result.get("hotel_research") if isinstance(result, dict) else None
            if isinstance(row, dict) and row.get("city"):
                row = dict(row)
                row["properties"] = [
                    {key: place[key] for key in ("name", "place_id", "address") if key in place}
                    for place in result.get("candidates", [])
                    if isinstance(place, dict)
                ]
                research[str(row["city"]).strip().casefold()] = row
    return research


def unresearched_hotel_cities(messages, plan):
    attempted = set()
    for message in messages:
        if isinstance(message, HumanMessage):
            attempted.clear()
        elif isinstance(message, AIMessage):
            attempted.update(
                str(call["args"].get("city") or "").strip().casefold()
                for call in message.tool_calls if call["name"] == "search_hotels"
            )
    cities = set()
    for day in plan.get("day_wise_itinerary") or []:
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict) or stop.get("kind") != "hotel":
                continue
            name = str(stop.get("name") or "")
            if not re.search(r"\b(?:tbd|tbc|to be decided|to be confirmed)\b", name, re.I):
                continue
            city = str(stop.get("city") or day.get("city") or "").strip()
            if not city:
                city = re.sub(
                    r"\b(?:hotel|stay|tbd|tbc|to be decided|to be confirmed|in|at)\b",
                    "", name, flags=re.I,
                ).strip(" ()-,")
            if city and city.casefold() not in attempted:
                cities.add(city)
    return sorted(cities)


def lodging_concern(stop, plan, day_date=""):
    rows = plan.get("lodging_research")
    rows = rows if isinstance(rows, dict) else {}
    name = str(stop.get("name") or "")
    placeholder = bool(re.search(r"\b(?:tbd|tbc|to be (?:decided|confirmed))\b", name, re.I))
    if not placeholder:
        hotel = next(
            (
                hotel
                for hotel in plan.get("selected_hotels", [])
                if isinstance(hotel, dict) and hotel.get("name") == name
            ),
            {},
        )
        metadata_only = any(
            row.get("reason") == "rate_and_availability_unverified"
            and any(place.get("name") == name for place in row.get("properties", []))
            for row in rows.values()
            if isinstance(row, dict)
        )
        if (
            not stop.get("booked")
            and not hotel.get("booked")
            and (
                metadata_only
                or stop.get("availability_status") == "unverified"
                or hotel.get("availability_status") == "unverified"
            )
        ):
            return "Recommended property; room rate and availability for your dates are unverified."
        return ""
    matches = [
        row
        for city, row in rows.items()
        if isinstance(row, dict)
        and re.search(rf"\b{re.escape(city)}\b", name, re.I)
        and (
            not day_date
            or (str(row.get("checkin") or "") <= day_date <= str(row.get("checkout") or "9999"))
        )
    ]
    if len(matches) != 1:
        return "Hotel TBD: no matching hotel research is recorded for this city and date."
    return "Hotel TBD: " + _REASONS.get(
        matches[0].get("reason"), "The reason for the missing hotel is unverified."
    )
