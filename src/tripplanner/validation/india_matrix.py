"""India-focused planner requests with deliberate within-destination variation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from tripplanner.validation.catalog import Catalog
from tripplanner.validation.matrix import Emphasis, Party, TripRequest


@dataclass(frozen=True)
class IndiaDestination:
    key: str
    phrase: str
    origin: str
    month: int
    durations: tuple[int, ...]


DESTINATIONS: tuple[IndiaDestination, ...] = (
    IndiaDestination("goa", "Goa", "Bangalore", 2, (3, 4, 5, 7)),
    IndiaDestination("kerala", "Kochi, Munnar and Alleppey", "Bangalore", 12, (5, 7, 9)),
    IndiaDestination("rajasthan", "Jaipur, Jodhpur and Udaipur", "Mumbai", 2, (5, 7, 9)),
    IndiaDestination("ladakh", "Leh, Nubra Valley and Pangong", "Delhi", 7, (7, 9)),
    IndiaDestination("kashmir", "Srinagar, Gulmarg and Pahalgam", "Delhi", 5, (5, 7, 9)),
    IndiaDestination("himachal", "Shimla and Manali", "Delhi", 10, (5, 7, 9)),
    IndiaDestination("uttarakhand", "Rishikesh and Mussoorie", "Delhi", 3, (4, 5, 7)),
    IndiaDestination("sikkim", "Gangtok and north Sikkim", "Kolkata", 10, (5, 7, 9)),
    IndiaDestination("meghalaya", "Shillong, Cherrapunji and Dawki", "Guwahati", 11, (5, 7)),
    IndiaDestination("andaman", "Port Blair, Havelock and Neil Island", "Kolkata", 1, (5, 7, 9)),
    IndiaDestination("varanasi", "Varanasi and Ayodhya", "Delhi", 2, (3, 5, 7)),
    IndiaDestination("gujarat", "Ahmedabad, Bhuj and the Rann of Kutch", "Mumbai", 12, (5, 7, 9)),
    IndiaDestination("madhya-pradesh", "Khajuraho, Panna and Orchha", "Delhi", 11, (5, 7)),
    IndiaDestination("karnataka-heritage", "Hampi, Badami and Aihole", "Bangalore", 1, (4, 5, 7)),
    IndiaDestination("tamil-nadu", "Madurai, Rameswaram and Thanjavur", "Chennai", 1, (5, 7)),
    IndiaDestination("odisha", "Bhubaneswar, Puri and Konark", "Kolkata", 12, (4, 5, 7)),
    IndiaDestination("assam", "Guwahati and Kaziranga", "Kolkata", 2, (4, 5, 7)),
    IndiaDestination("maharashtra", "Mumbai, Lonavala and Mahabaleshwar", "Pune", 1, (4, 5, 7)),
    IndiaDestination("pondicherry", "Pondicherry and Mahabalipuram", "Chennai", 3, (3, 4, 5)),
    IndiaDestination("lakshadweep", "Lakshadweep", "Kochi", 2, (5, 7)),
)

PARTIES: tuple[Party, ...] = (
    Party("solo", "1 adult travelling solo"),
    Party("solo-woman", "1 woman travelling solo, with practical evening safety constraints"),
    Party("couple", "2 adults travelling as a couple"),
    Party("friends", "4 adult friends"),
    Party("three-couples", "6 adults travelling as three couples"),
    Party("young-family", "2 adults and 2 children aged 4 and 8"),
    Party("teen-family", "2 adults and 2 children aged 13 and 16"),
    Party("three-generation", "4 adults and 1 child aged 8, including grandparents aged 68 and 72"),
)

EMPHASES: tuple[Emphasis, ...] = (
    Emphasis(
        "relaxation",
        "relaxation with generous free time",
        "Prioritize relaxation, one main outing per day and free afternoons.",
    ),
    Emphasis(
        "packed",
        "dense sightseeing",
        "Fit in the major highlights with early starts and efficient geographic grouping.",
    ),
    Emphasis(
        "food",
        "regional food",
        "Make regional food central, with concrete lunch and dinner choices.",
    ),
    Emphasis(
        "heritage",
        "history and culture",
        "Focus on history, architecture, museums and local culture.",
    ),
    Emphasis(
        "nature",
        "nature and outdoors",
        "Focus on scenery, wildlife and practical outdoor experiences.",
    ),
    Emphasis(
        "celebration",
        "celebration and nightlife",
        "Include lively evenings and one special celebration experience where appropriate.",
    ),
    Emphasis(
        "budget",
        "tight whole-trip budget",
        "Keep the whole trip under INR 80000 and support the total with priced evidence.",
    ),
    Emphasis(
        "premium",
        "premium stays and comfort",
        "Prioritize excellent premium stays, comfort and low-friction transfers.",
    ),
    Emphasis(
        "accessible",
        "limited walking and stairs",
        "One traveller cannot manage long walks or stairs; minimize difficult access.",
    ),
)


def _stable(value: str) -> int:
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:8], 16)


def _date_phrase(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day} to {end.day} {start.strftime('%B')} {start.year}"
    return f"{start.day} {start.strftime('%B')} to {end.day} {end.strftime('%B')} {end.year}"


def _compose(
    destination: IndiaDestination, party: Party, emphasis: Emphasis, days: int, year: int
) -> TripRequest:
    slug = f"india-{destination.key}-{emphasis.key}-{party.key}-{days}d"
    start = date(year, destination.month, 1) + timedelta(days=_stable(slug) % 18)
    dates = _date_phrase(start, start + timedelta(days=days))
    return TripRequest(
        slug=slug,
        shape=f"India: {destination.phrase}, {emphasis.shape}, {party.key}, {days} days",
        message=(
            f"Plan a {days} day trip to {destination.phrase} from {destination.origin} for "
            f"{party.phrase}, {dates}. {emphasis.clause} This is a domestic trip within India."
        ),
        destination=f"india:{destination.key}",
        emphasis=emphasis.key,
        party=party.key,
        days=days,
        scenario_expectations=(
            f"Keep the trip within {destination.phrase}.",
            f"Plan appropriately for {party.phrase}.",
            emphasis.clause,
            f"Keep the requested {days}-day duration.",
        ),
        budget_evidence_required=emphasis.key == "budget",
    )


def candidates(catalog: Catalog, *, limit: int = 500, year: int = 2027) -> tuple[TripRequest, ...]:
    """Balance destinations while retaining exact party, emphasis and duration combinations."""
    grouped: dict[str, list[TripRequest]] = {}
    for destination in DESTINATIONS:
        requests = [
            _compose(destination, party, emphasis, days, year)
            for party in PARTIES
            for emphasis in EMPHASES
            for days in destination.durations
        ]
        grouped[destination.key] = [
            request
            for request in sorted(requests, key=lambda item: _stable(item.slug))
            if request.slug not in catalog.slugs and request.signature.key not in catalog.keys
        ]

    order = sorted(grouped, key=_stable)
    picked: list[TripRequest] = []
    depth = 0
    while order and (limit <= 0 or len(picked) < limit):
        progressed = False
        for key in order:
            if depth >= len(grouped[key]):
                continue
            picked.append(grouped[key][depth])
            progressed = True
            if limit > 0 and len(picked) >= limit:
                break
        if not progressed:
            break
        depth += 1
    return tuple(picked)
