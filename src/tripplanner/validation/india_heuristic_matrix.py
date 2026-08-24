"""India requests sampled from destination-specific planning heuristics.

These are reviewable product hypotheses informed by general travel-planning
knowledge, not measured tourism statistics. Real trip evidence can replace them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from tripplanner.validation.catalog import Catalog
from tripplanner.validation.matrix import Emphasis, Party, TripRequest


@dataclass(frozen=True)
class VisitorProfile:
    party: str
    emphasis: str
    weight: int
    rationale: str


@dataclass(frozen=True)
class IndiaDestination:
    key: str
    phrase: str
    origin: str
    month: int
    durations: tuple[tuple[int, int], ...]
    profiles: tuple[VisitorProfile, ...]


PARTIES = {
    party.key: party
    for party in (
        Party("solo", "1 adult travelling solo"),
        Party(
            "solo-woman",
            "1 woman travelling solo, with practical evening safety constraints",
        ),
        Party("couple", "2 adults travelling as a couple"),
        Party("friends", "4 adult friends"),
        Party("three-couples", "6 adults travelling as three couples"),
        Party("young-family", "2 adults and 2 children aged 4 and 8"),
        Party("teen-family", "2 adults and 2 children aged 13 and 16"),
        Party("senior-couple", "2 adults aged 64 and 70"),
        Party(
            "three-generation",
            "4 adults and 1 child aged 8, including grandparents aged 68 and 72",
        ),
    )
}

EMPHASES = {
    emphasis.key: emphasis
    for emphasis in (
        Emphasis(
            "relaxation",
            "relaxation with free time",
            "Prioritize relaxation, one main outing per day and free afternoons.",
        ),
        Emphasis(
            "packed",
            "dense sightseeing",
            "Fit in major highlights with early starts and efficient geographic grouping.",
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
            "pilgrimage",
            "pilgrimage and temple access",
            "Prioritize worship timings, temple access, modest pacing and practical meals.",
        ),
        Emphasis(
            "nature",
            "nature and outdoors",
            "Focus on scenery, wildlife and practical outdoor experiences.",
        ),
        Emphasis(
            "celebration",
            "celebration and nightlife",
            "Include lively evenings and one special celebration experience where suitable.",
        ),
        Emphasis(
            "budget",
            "tight whole-trip budget",
            "Keep the trip under INR 80000 and support the total with priced evidence.",
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
}


def _p(party: str, emphasis: str, weight: int, rationale: str) -> VisitorProfile:
    return VisitorProfile(party, emphasis, weight, rationale)


DESTINATIONS: tuple[IndiaDestination, ...] = (
    IndiaDestination("goa", "Goa", "Bangalore", 2, ((4, 10), (3, 9), (5, 8), (7, 5)), (
        _p("friends", "celebration", 10, "Common friends and nightlife break."),
        _p("couple", "relaxation", 10, "Couples combine beaches and downtime."),
        _p("young-family", "relaxation", 8, "Families need short transfers and pool time."),
        _p("three-couples", "premium", 6, "Small groups often share a comfort-led holiday."),
        _p("solo-woman", "food", 5, "Solo visitors need safe logistics and local character."),
    )),
    IndiaDestination("kerala", "Kochi, Munnar and Alleppey", "Bangalore", 12,
        ((7, 10), (6, 9), (8, 7), (10, 4)), (
        _p("young-family", "nature", 10, "Strong family holiday circuit."),
        _p("couple", "premium", 9, "Couples often seek resorts and a houseboat."),
        _p("senior-couple", "relaxation", 7, "Scenic travel suits senior leisure."),
        _p("three-generation", "accessible", 6, "Mixed ages stress transfer quality."),
    )),
    IndiaDestination("rajasthan", "Jaipur, Jodhpur and Udaipur", "Mumbai", 2,
        ((7, 10), (8, 9), (6, 7), (10, 5)), (
        _p("couple", "heritage", 10, "Classic circuit is strongly heritage-led."),
        _p("young-family", "heritage", 8, "Families combine forts and culture."),
        _p("three-couples", "premium", 7, "Heritage hotels suit celebratory groups."),
        _p("senior-couple", "accessible", 6, "Fort access and drives need scrutiny."),
    )),
    IndiaDestination("ladakh", "Leh, Nubra Valley and Pangong", "Delhi", 7,
        ((8, 10), (7, 9), (9, 8), (10, 6)), (
        _p("friends", "nature", 10, "Adventure groups are a common shape."),
        _p("couple", "nature", 8, "Couples often take the scenic circuit."),
        _p("solo", "budget", 6, "Solo riders need practical cost coverage."),
        _p("senior-couple", "accessible", 4, "Altitude and acclimatisation are critical."),
    )),
    IndiaDestination("kashmir", "Srinagar, Gulmarg and Pahalgam", "Delhi", 5,
        ((6, 10), (7, 9), (5, 8), (8, 5)), (
        _p("young-family", "nature", 10, "Mainstream family scenic holiday."),
        _p("couple", "premium", 9, "Couples seek scenery and special stays."),
        _p("three-generation", "relaxation", 7, "Mixed-age families need gentle pacing."),
        _p("friends", "nature", 6, "Friends add active mountain experiences."),
    )),
    IndiaDestination("himachal", "Shimla and Manali", "Delhi", 10,
        ((6, 10), (5, 9), (7, 8), (9, 4)), (
        _p("young-family", "nature", 10, "Common school-holiday family circuit."),
        _p("couple", "relaxation", 9, "Couples favor scenic stays and easy pace."),
        _p("friends", "nature", 8, "Friend groups add outdoor activities."),
        _p("senior-couple", "accessible", 5, "Road time and gradients matter."),
    )),
    IndiaDestination("uttarakhand", "Rishikesh and Mussoorie", "Delhi", 3,
        ((5, 10), (4, 9), (6, 7), (8, 4)), (
        _p("friends", "nature", 10, "Common short adventure trip from Delhi."),
        _p("couple", "relaxation", 8, "Couples combine river and hill downtime."),
        _p("young-family", "nature", 7, "Families need age-appropriate activities."),
        _p("senior-couple", "pilgrimage", 6, "Spiritual visits need comfortable access."),
    )),
    IndiaDestination("sikkim", "Gangtok and north Sikkim", "Kolkata", 10,
        ((7, 10), (6, 9), (8, 7), (9, 5)), (
        _p("couple", "nature", 10, "Scenic couples trips are common."),
        _p("young-family", "nature", 8, "Families need careful road-day pacing."),
        _p("friends", "nature", 7, "Groups often prioritize north Sikkim."),
        _p("senior-couple", "accessible", 4, "Altitude and transfers affect feasibility."),
    )),
    IndiaDestination("meghalaya", "Shillong, Cherrapunji and Dawki", "Guwahati", 11,
        ((6, 10), (5, 9), (7, 8), (8, 4)), (
        _p("friends", "nature", 10, "Road-trip groups dominate the active circuit."),
        _p("couple", "nature", 9, "Couples favor waterfalls and scenic stays."),
        _p("solo-woman", "nature", 6, "Solo logistics and evening safety matter."),
        _p("young-family", "nature", 5, "Children change cave and trek selection."),
    )),
    IndiaDestination("andaman", "Port Blair, Havelock and Neil Island", "Kolkata", 1,
        ((7, 10), (6, 9), (8, 7), (5, 6)), (
        _p("couple", "premium", 10, "Island trips are strongly couple-led."),
        _p("young-family", "relaxation", 8, "Families need ferry and beach-day realism."),
        _p("friends", "nature", 7, "Groups add diving and water activities."),
        _p("senior-couple", "accessible", 4, "Ferry boarding access is material."),
    )),
    IndiaDestination("varanasi", "Varanasi and Ayodhya", "Delhi", 2,
        ((4, 10), (3, 9), (5, 8), (6, 4)), (
        _p("three-generation", "pilgrimage", 10, "Pilgrimage families are a primary audience."),
        _p("senior-couple", "pilgrimage", 10, "Older pilgrims need access-aware schedules."),
        _p("couple", "heritage", 6, "Some combine spirituality and history."),
        _p("solo", "pilgrimage", 5, "Solo spiritual travel is plausible."),
    )),
    IndiaDestination("gujarat", "Ahmedabad, Bhuj and the Rann of Kutch", "Mumbai", 12,
        ((7, 10), (6, 9), (8, 7), (9, 4)), (
        _p("young-family", "heritage", 9, "Families combine culture and the Rann."),
        _p("three-generation", "food", 8, "Food and culture suit family groups."),
        _p("couple", "premium", 7, "Couples choose festival-season comfort."),
        _p("senior-couple", "pilgrimage", 6, "Temple additions are common."),
    )),
    IndiaDestination("madhya-pradesh", "Khajuraho, Panna and Orchha", "Delhi", 11,
        ((6, 10), (5, 9), (7, 7), (8, 4)), (
        _p("couple", "heritage", 10, "Circuit combines monuments and wildlife."),
        _p("friends", "nature", 7, "Groups can emphasize safari and outdoors."),
        _p("senior-couple", "heritage", 6, "Heritage travelers need gentle pacing."),
        _p("young-family", "nature", 5, "Safari-led family trips are plausible."),
    )),
    IndiaDestination("karnataka-heritage", "Hampi, Badami and Aihole", "Bangalore", 1,
        ((5, 10), (4, 9), (6, 7), (7, 5)), (
        _p("couple", "heritage", 10, "Heritage couples are a core shape."),
        _p("friends", "heritage", 8, "Road-trip groups cover the circuit."),
        _p("solo", "budget", 7, "Hampi is popular with solo budget travelers."),
        _p("senior-couple", "accessible", 5, "Heat, terrain and walking matter."),
    )),
    IndiaDestination("tamil-nadu", "Madurai, Rameswaram and Thanjavur", "Chennai", 1,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)), (
        _p("three-generation", "pilgrimage", 10, "Temple circuits commonly involve families."),
        _p("senior-couple", "pilgrimage", 10, "Many visitors are middle-aged or elderly pilgrims."),
        _p("young-family", "pilgrimage", 7, "Family worship needs child-aware pacing."),
        _p("couple", "heritage", 5, "Architecture leisure is a secondary shape."),
    )),
    IndiaDestination("odisha", "Bhubaneswar, Puri and Konark", "Kolkata", 12,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)), (
        _p("three-generation", "pilgrimage", 10, "Puri drives family pilgrimage."),
        _p("senior-couple", "pilgrimage", 9, "Older pilgrims need temple-access realism."),
        _p("young-family", "relaxation", 7, "Families combine beach and temples."),
        _p("couple", "heritage", 6, "Konark supports a heritage trip."),
    )),
    IndiaDestination("assam", "Guwahati and Kaziranga", "Kolkata", 2,
        ((5, 10), (4, 9), (6, 7), (7, 5)), (
        _p("young-family", "nature", 10, "Wildlife holidays are family-friendly."),
        _p("couple", "nature", 8, "Couples choose short safari breaks."),
        _p("friends", "nature", 7, "Groups add active nature experiences."),
        _p("senior-couple", "accessible", 5, "Safari comfort and transfers matter."),
    )),
    IndiaDestination("maharashtra", "Mumbai, Lonavala and Mahabaleshwar", "Pune", 1,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)), (
        _p("young-family", "relaxation", 10, "Nearby hill breaks are family-heavy."),
        _p("friends", "food", 8, "Friends combine city food and hill time."),
        _p("couple", "premium", 8, "Couples choose resort-led breaks."),
        _p("three-generation", "accessible", 5, "Mixed ages stress road choices."),
    )),
    IndiaDestination("pondicherry", "Pondicherry and Mahabalipuram", "Chennai", 3,
        ((4, 10), (3, 9), (5, 7), (6, 3)), (
        _p("couple", "food", 10, "Common short couples and food break."),
        _p("friends", "food", 8, "Friend groups favor cafes and coast."),
        _p("young-family", "heritage", 6, "Families combine beaches and monuments."),
        _p("solo-woman", "relaxation", 5, "Solo slow travel is plausible."),
    )),
    IndiaDestination("lakshadweep", "Lakshadweep", "Kochi", 2,
        ((6, 10), (5, 9), (7, 8), (8, 4)), (
        _p("couple", "premium", 10, "Island access favors planned couples holidays."),
        _p("friends", "nature", 7, "Groups prioritize water activities."),
        _p("young-family", "relaxation", 6, "Families need transfer coverage."),
        _p("senior-couple", "accessible", 3, "Access constraints make a useful edge case."),
    )),
)


def _stable(value: str) -> int:
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:8], 16)


def _date_phrase(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day} to {end.day} {start.strftime('%B')} {start.year}"
    return f"{start.day} {start.strftime('%B')} to {end.day} {end.strftime('%B')} {end.year}"


def _compose(
    destination: IndiaDestination,
    profile: VisitorProfile,
    days: int,
    duration_weight: int,
    year: int,
) -> tuple[int, TripRequest]:
    party = PARTIES[profile.party]
    emphasis = EMPHASES[profile.emphasis]
    slug = f"india-{destination.key}-{emphasis.key}-{party.key}-{days}d"
    start = date(year, destination.month, 1) + timedelta(days=_stable(slug) % 18)
    request = TripRequest(
        slug=slug,
        shape=f"India: {destination.phrase}, {emphasis.shape}, {party.key}, {days} days",
        message=(
            f"Plan a {days} day trip to {destination.phrase} from {destination.origin} for "
            f"{party.phrase}, {_date_phrase(start, start + timedelta(days=days))}. "
            f"{emphasis.clause} This is a domestic trip within India."
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
            f"Heuristic audience rationale: {profile.rationale}",
        ),
        budget_evidence_required=emphasis.key == "budget",
    )
    return profile.weight * duration_weight, request


def candidates(catalog: Catalog, *, limit: int = 500, year: int = 2027) -> tuple[TripRequest, ...]:
    """Balance destinations, then choose their most plausible uncovered scenarios."""
    grouped: dict[str, list[TripRequest]] = {}
    for destination in DESTINATIONS:
        weighted = [
            _compose(destination, profile, days, duration_weight, year)
            for profile in destination.profiles
            for days, duration_weight in destination.durations
        ]
        weighted.sort(key=lambda item: (-item[0], _stable(item[1].slug)))
        grouped[destination.key] = [
            request
            for _, request in weighted
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
