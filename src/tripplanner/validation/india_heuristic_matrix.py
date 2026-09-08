"""India requests sampled from destination-specific planning heuristics.

These are reviewable product hypotheses informed by general travel-planning
knowledge, not measured tourism statistics. Real trip evidence can replace them.
"""

from __future__ import annotations

from datetime import date, timedelta

from tripplanner.validation.catalog import Catalog
from tripplanner.validation.market_catalog import (
    MarketDestination,
    VisitorProfile,
    stable,
    weighted_candidates,
)
from tripplanner.validation.matrix import Emphasis, Party, TripRequest

IndiaDestination = MarketDestination


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
    IndiaDestination(
        "goa",
        "Goa",
        "Bangalore",
        2,
        ((4, 10), (3, 9), (5, 8), (7, 5)),
        (
            _p("friends", "celebration", 10, "Common friends and nightlife break."),
            _p("couple", "relaxation", 10, "Couples combine beaches and downtime."),
            _p("young-family", "relaxation", 8, "Families need short transfers and pool time."),
            _p("three-couples", "premium", 6, "Small groups often share a comfort-led holiday."),
            _p("solo-woman", "food", 5, "Solo visitors need safe logistics and local character."),
        ),
    ),
    IndiaDestination(
        "kerala",
        "Kochi, Munnar and Alleppey",
        "Bangalore",
        12,
        ((7, 10), (6, 9), (8, 7), (10, 4)),
        (
            _p("young-family", "nature", 10, "Strong family holiday circuit."),
            _p("couple", "premium", 9, "Couples often seek resorts and a houseboat."),
            _p("senior-couple", "relaxation", 7, "Scenic travel suits senior leisure."),
            _p("three-generation", "accessible", 6, "Mixed ages stress transfer quality."),
        ),
    ),
    IndiaDestination(
        "rajasthan",
        "Jaipur, Jodhpur and Udaipur",
        "Mumbai",
        2,
        ((7, 10), (8, 9), (6, 7), (10, 5)),
        (
            _p("couple", "heritage", 10, "Classic circuit is strongly heritage-led."),
            _p("young-family", "heritage", 8, "Families combine forts and culture."),
            _p("three-couples", "premium", 7, "Heritage hotels suit celebratory groups."),
            _p("senior-couple", "accessible", 6, "Fort access and drives need scrutiny."),
        ),
    ),
    IndiaDestination(
        "ladakh",
        "Leh, Nubra Valley and Pangong",
        "Delhi",
        7,
        ((8, 10), (7, 9), (9, 8), (10, 6)),
        (
            _p("friends", "nature", 10, "Adventure groups are a common shape."),
            _p("couple", "nature", 8, "Couples often take the scenic circuit."),
            _p("solo", "budget", 6, "Solo riders need practical cost coverage."),
            _p("senior-couple", "accessible", 4, "Altitude and acclimatisation are critical."),
        ),
    ),
    IndiaDestination(
        "kashmir",
        "Srinagar, Gulmarg and Pahalgam",
        "Delhi",
        5,
        ((6, 10), (7, 9), (5, 8), (8, 5)),
        (
            _p("young-family", "nature", 10, "Mainstream family scenic holiday."),
            _p("couple", "premium", 9, "Couples seek scenery and special stays."),
            _p("three-generation", "relaxation", 7, "Mixed-age families need gentle pacing."),
            _p("friends", "nature", 6, "Friends add active mountain experiences."),
        ),
    ),
    IndiaDestination(
        "himachal",
        "Shimla and Manali",
        "Delhi",
        10,
        ((6, 10), (5, 9), (7, 8), (9, 4)),
        (
            _p("young-family", "nature", 10, "Common school-holiday family circuit."),
            _p("couple", "relaxation", 9, "Couples favor scenic stays and easy pace."),
            _p("friends", "nature", 8, "Friend groups add outdoor activities."),
            _p("senior-couple", "accessible", 5, "Road time and gradients matter."),
        ),
    ),
    IndiaDestination(
        "uttarakhand",
        "Rishikesh and Mussoorie",
        "Delhi",
        3,
        ((5, 10), (4, 9), (6, 7), (8, 4)),
        (
            _p("friends", "nature", 10, "Common short adventure trip from Delhi."),
            _p("couple", "relaxation", 8, "Couples combine river and hill downtime."),
            _p("young-family", "nature", 7, "Families need age-appropriate activities."),
            _p("senior-couple", "pilgrimage", 6, "Spiritual visits need comfortable access."),
        ),
    ),
    IndiaDestination(
        "sikkim",
        "Gangtok and north Sikkim",
        "Kolkata",
        10,
        ((7, 10), (6, 9), (8, 7), (9, 5)),
        (
            _p("couple", "nature", 10, "Scenic couples trips are common."),
            _p("young-family", "nature", 8, "Families need careful road-day pacing."),
            _p("friends", "nature", 7, "Groups often prioritize north Sikkim."),
            _p("senior-couple", "accessible", 4, "Altitude and transfers affect feasibility."),
        ),
    ),
    IndiaDestination(
        "meghalaya",
        "Shillong, Cherrapunji and Dawki",
        "Guwahati",
        11,
        ((6, 10), (5, 9), (7, 8), (8, 4)),
        (
            _p("friends", "nature", 10, "Road-trip groups dominate the active circuit."),
            _p("couple", "nature", 9, "Couples favor waterfalls and scenic stays."),
            _p("solo-woman", "nature", 6, "Solo logistics and evening safety matter."),
            _p("young-family", "nature", 5, "Children change cave and trek selection."),
        ),
    ),
    IndiaDestination(
        "andaman",
        "Port Blair, Havelock and Neil Island",
        "Kolkata",
        1,
        ((7, 10), (6, 9), (8, 7), (5, 6)),
        (
            _p("couple", "premium", 10, "Island trips are strongly couple-led."),
            _p("young-family", "relaxation", 8, "Families need ferry and beach-day realism."),
            _p("friends", "nature", 7, "Groups add diving and water activities."),
            _p("senior-couple", "accessible", 4, "Ferry boarding access is material."),
        ),
    ),
    IndiaDestination(
        "varanasi",
        "Varanasi and Ayodhya",
        "Delhi",
        2,
        ((4, 10), (3, 9), (5, 8), (6, 4)),
        (
            _p("three-generation", "pilgrimage", 10, "Pilgrimage families are a primary audience."),
            _p("senior-couple", "pilgrimage", 10, "Older pilgrims need access-aware schedules."),
            _p("couple", "heritage", 6, "Some combine spirituality and history."),
            _p("solo", "pilgrimage", 5, "Solo spiritual travel is plausible."),
        ),
    ),
    IndiaDestination(
        "golden-triangle",
        "Delhi, Agra and Jaipur",
        "Bangalore",
        2,
        ((5, 10), (6, 9), (4, 8), (7, 6)),
        (
            _p(
                "young-family", "heritage", 10, "A first-time family circuit needs paced transfers."
            ),
            _p("couple", "heritage", 9, "The compact circuit is strongly history-led."),
            _p("three-generation", "accessible", 7, "Fort and monument access changes the plan."),
            _p("friends", "packed", 6, "Friends can sustain a denser highlights circuit."),
        ),
    ),
    IndiaDestination(
        "bihar-buddhist",
        "Bodh Gaya, Nalanda and Rajgir",
        "Kolkata",
        1,
        ((4, 10), (3, 9), (5, 8)),
        (
            _p("senior-couple", "pilgrimage", 10, "The Buddhist circuit needs gentle pacing."),
            _p("three-generation", "heritage", 9, "Families combine worship and learning."),
            _p("couple", "heritage", 7, "History-focused visitors can cover the compact circuit."),
            _p("solo", "pilgrimage", 5, "Solo contemplative travel is plausible."),
        ),
    ),
    IndiaDestination(
        "tirupati",
        "Tirupati with an optional Chennai stop",
        "Hyderabad",
        8,
        ((3, 10), (2, 9), (4, 7)),
        (
            _p(
                "three-generation",
                "pilgrimage",
                10,
                "Temple visits often involve mixed-age families.",
            ),
            _p("senior-couple", "pilgrimage", 10, "Darshan access and rest periods are material."),
            _p("young-family", "pilgrimage", 7, "Children change queue and meal planning."),
            _p("couple", "pilgrimage", 5, "A compact couple pilgrimage is common enough to test."),
        ),
    ),
    IndiaDestination(
        "char-dham",
        "Haridwar, Rishikesh and the Char Dham route",
        "Delhi",
        5,
        ((8, 10), (10, 9), (12, 7), (6, 5)),
        (
            _p(
                "three-generation",
                "pilgrimage",
                10,
                "Registration and mixed-age pacing are essential.",
            ),
            _p(
                "senior-couple",
                "accessible",
                9,
                "Health, gradients and road days control feasibility.",
            ),
            _p("young-family", "pilgrimage", 5, "Family suitability needs explicit scrutiny."),
        ),
    ),
    IndiaDestination(
        "amritsar",
        "Amritsar",
        "Delhi",
        11,
        ((3, 10), (2, 9), (4, 7)),
        (
            _p(
                "three-generation", "pilgrimage", 10, "A compact family pilgrimage is a core shape."
            ),
            _p("couple", "food", 9, "Food and history support a short couple break."),
            _p("young-family", "heritage", 8, "Families combine the Golden Temple and history."),
            _p("senior-couple", "accessible", 6, "Low-friction transfers and rest matter."),
        ),
    ),
    IndiaDestination(
        "gujarat",
        "Ahmedabad, Bhuj and the Rann of Kutch",
        "Mumbai",
        12,
        ((7, 10), (6, 9), (8, 7), (9, 4)),
        (
            _p("young-family", "heritage", 9, "Families combine culture and the Rann."),
            _p("three-generation", "food", 8, "Food and culture suit family groups."),
            _p("couple", "premium", 7, "Couples choose festival-season comfort."),
            _p("senior-couple", "pilgrimage", 6, "Temple additions are common."),
        ),
    ),
    IndiaDestination(
        "madhya-pradesh",
        "Khajuraho, Panna and Orchha",
        "Delhi",
        11,
        ((6, 10), (5, 9), (7, 7), (8, 4)),
        (
            _p("couple", "heritage", 10, "Circuit combines monuments and wildlife."),
            _p("friends", "nature", 7, "Groups can emphasize safari and outdoors."),
            _p("senior-couple", "heritage", 6, "Heritage travelers need gentle pacing."),
            _p("young-family", "nature", 5, "Safari-led family trips are plausible."),
        ),
    ),
    IndiaDestination(
        "karnataka-heritage",
        "Hampi, Badami and Aihole",
        "Bangalore",
        1,
        ((5, 10), (4, 9), (6, 7), (7, 5)),
        (
            _p("couple", "heritage", 10, "Heritage couples are a core shape."),
            _p("friends", "heritage", 8, "Road-trip groups cover the circuit."),
            _p("solo", "budget", 7, "Hampi is popular with solo budget travelers."),
            _p("senior-couple", "accessible", 5, "Heat, terrain and walking matter."),
        ),
    ),
    IndiaDestination(
        "tamil-nadu",
        "Madurai, Rameswaram and Thanjavur",
        "Chennai",
        1,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)),
        (
            _p("three-generation", "pilgrimage", 10, "Temple circuits commonly involve families."),
            _p(
                "senior-couple",
                "pilgrimage",
                10,
                "Many visitors are middle-aged or elderly pilgrims.",
            ),
            _p("young-family", "pilgrimage", 7, "Family worship needs child-aware pacing."),
            _p("couple", "heritage", 5, "Architecture leisure is a secondary shape."),
        ),
    ),
    IndiaDestination(
        "odisha",
        "Bhubaneswar, Puri and Konark",
        "Kolkata",
        12,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)),
        (
            _p("three-generation", "pilgrimage", 10, "Puri drives family pilgrimage."),
            _p("senior-couple", "pilgrimage", 9, "Older pilgrims need temple-access realism."),
            _p("young-family", "relaxation", 7, "Families combine beach and temples."),
            _p("couple", "heritage", 6, "Konark supports a heritage trip."),
        ),
    ),
    IndiaDestination(
        "assam",
        "Guwahati and Kaziranga",
        "Kolkata",
        2,
        ((5, 10), (4, 9), (6, 7), (7, 5)),
        (
            _p("young-family", "nature", 10, "Wildlife holidays are family-friendly."),
            _p("couple", "nature", 8, "Couples choose short safari breaks."),
            _p("friends", "nature", 7, "Groups add active nature experiences."),
            _p("senior-couple", "accessible", 5, "Safari comfort and transfers matter."),
        ),
    ),
    IndiaDestination(
        "arunachal",
        "Tawang and western Arunachal Pradesh",
        "Guwahati",
        10,
        ((8, 10), (9, 9), (7, 8), (10, 6)),
        (
            _p("friends", "nature", 10, "Long mountain drives suit an experienced group."),
            _p("couple", "nature", 9, "Couples need realistic transfer and permit planning."),
            _p("young-family", "nature", 5, "Altitude and road days require child-aware scrutiny."),
            _p("senior-couple", "accessible", 3, "This edge case should expose infeasible pacing."),
        ),
    ),
    IndiaDestination(
        "hyderabad",
        "Hyderabad",
        "Bangalore",
        11,
        ((3, 10), (4, 9), (2, 7)),
        (
            _p("friends", "food", 10, "Food is central to a compact city break."),
            _p("young-family", "heritage", 8, "Families combine monuments and museums."),
            _p("couple", "premium", 7, "Couples can use a comfort-led city weekend."),
            _p("senior-couple", "accessible", 5, "Heat and walking need practical choices."),
        ),
    ),
    IndiaDestination(
        "mysuru-coorg",
        "Mysuru and Coorg",
        "Bangalore",
        10,
        ((5, 10), (4, 9), (6, 7)),
        (
            _p(
                "young-family",
                "nature",
                10,
                "A common road circuit needs short family travel days.",
            ),
            _p("couple", "relaxation", 9, "Couples combine heritage with a resort stay."),
            _p("three-generation", "accessible", 6, "Mixed ages change stops and transfer length."),
            _p("friends", "food", 5, "A road-trip group adds local food and outdoors."),
        ),
    ),
    IndiaDestination(
        "kolkata-sundarbans",
        "Kolkata and the Sundarbans",
        "Delhi",
        12,
        ((5, 10), (4, 9), (6, 7)),
        (
            _p("young-family", "heritage", 9, "Families combine city culture and wildlife."),
            _p("couple", "food", 9, "Food and culture lead the city portion."),
            _p("friends", "nature", 7, "Groups can emphasize the delta excursion."),
            _p("senior-couple", "accessible", 5, "Boat boarding and transfers need scrutiny."),
        ),
    ),
    IndiaDestination(
        "mumbai",
        "Mumbai",
        "Ahmedabad",
        1,
        ((3, 10), (4, 9), (2, 7), (5, 5)),
        (
            _p("couple", "food", 10, "A compact food and culture break is plausible."),
            _p("friends", "celebration", 9, "Friends add nightlife and dense city coverage."),
            _p("young-family", "heritage", 7, "Families need age-aware city pacing."),
            _p("solo-woman", "food", 5, "Solo safety and evening transport matter."),
        ),
    ),
    IndiaDestination(
        "wildlife-central-india",
        "Kanha and Bandhavgarh",
        "Delhi",
        2,
        ((6, 10), (5, 9), (7, 7)),
        (
            _p("young-family", "nature", 10, "Safari timing and child suitability shape the trip."),
            _p("couple", "premium", 8, "A lodge-led wildlife holiday is a distinct shape."),
            _p("friends", "nature", 8, "Groups can prioritize multiple safari zones."),
            _p("senior-couple", "accessible", 5, "Vehicle comfort and early starts matter."),
        ),
    ),
    IndiaDestination(
        "maharashtra",
        "Mumbai, Lonavala and Mahabaleshwar",
        "Pune",
        1,
        ((5, 10), (4, 9), (6, 7), (3, 6), (7, 4)),
        (
            _p("young-family", "relaxation", 10, "Nearby hill breaks are family-heavy."),
            _p("friends", "food", 8, "Friends combine city food and hill time."),
            _p("couple", "premium", 8, "Couples choose resort-led breaks."),
            _p("three-generation", "accessible", 5, "Mixed ages stress road choices."),
        ),
    ),
    IndiaDestination(
        "pondicherry",
        "Pondicherry and Mahabalipuram",
        "Chennai",
        3,
        ((4, 10), (3, 9), (5, 7), (6, 3)),
        (
            _p("couple", "food", 10, "Common short couples and food break."),
            _p("friends", "food", 8, "Friend groups favor cafes and coast."),
            _p("young-family", "heritage", 6, "Families combine beaches and monuments."),
            _p("solo-woman", "relaxation", 5, "Solo slow travel is plausible."),
        ),
    ),
    IndiaDestination(
        "lakshadweep",
        "Lakshadweep",
        "Kochi",
        2,
        ((6, 10), (5, 9), (7, 8), (8, 4)),
        (
            _p("couple", "premium", 10, "Island access favors planned couples holidays."),
            _p("friends", "nature", 7, "Groups prioritize water activities."),
            _p("young-family", "relaxation", 6, "Families need transfer coverage."),
            _p("senior-couple", "accessible", 3, "Access constraints make a useful edge case."),
        ),
    ),
)

DESTINATION_PRIORITIES = {
    "varanasi": 10,
    "golden-triangle": 10,
    "goa": 9,
    "kerala": 9,
    "rajasthan": 9,
    "kashmir": 9,
    "himachal": 8,
    "tirupati": 8,
    "tamil-nadu": 8,
    "char-dham": 7,
    "ladakh": 7,
    "bihar-buddhist": 7,
    "uttarakhand": 7,
    "amritsar": 7,
    "sikkim": 6,
    "meghalaya": 6,
    "assam": 6,
    "andaman": 6,
    "lakshadweep": 6,
    "arunachal": 5,
}

DESTINATION_EVIDENCE = {
    "varanasi": (
        "high",
        "Official UP district data records 101,647,159 domestic tourist visits to "
        "Varanasi in 2023; duration and audience remain catalog inferences.",
    ),
    "golden-triangle": (
        "high inclusion; medium shape",
        "Official UP district data records 11,138,316 domestic and 970,901 foreign "
        "tourist visits to Agra in 2023; circuit shape is an inference.",
    ),
    "tirupati": (
        "high state demand; medium allocation",
        "Official state data records 237,051,508 domestic tourist visits to Andhra "
        "Pradesh in 2019; it does not attribute all visits to Tirupati.",
    ),
    "bihar-buddhist": (
        "high state demand; medium allocation",
        "Official state data records 33,990,038 domestic tourist visits to Bihar in "
        "2019; allocation to this circuit is a catalog inference.",
    ),
    "assam": (
        "high state demand; medium shape",
        "Official state data records 5,447,805 domestic tourist visits to Assam in "
        "2019; audience and duration are catalog inferences.",
    ),
    "char-dham": (
        "high constraint confidence",
        "Uttarakhand's official portal requires traveler and vehicle registration and "
        "destination verification for Char Dham and Hemkund Sahib journeys.",
    ),
    "ladakh": (
        "high constraint confidence",
        "Leh's official tourist portal requires at least 48 hours of acclimatisation "
        "before travel to higher-altitude areas.",
    ),
    "lakshadweep": (
        "high constraint confidence",
        "The UT Administration states that entry is restricted and requires a permit.",
    ),
}


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
    evidence_confidence, evidence_note = DESTINATION_EVIDENCE.get(
        destination.key,
        (destination.evidence_confidence, destination.evidence_note),
    )
    slug = f"india-{destination.key}-{emphasis.key}-{party.key}-{days}d"
    start = date(year, destination.month, 1) + timedelta(days=stable(slug) % 18)
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
            f"Evidence posture ({evidence_confidence}): {evidence_note}",
        ),
        budget_evidence_required=emphasis.key == "budget",
    )
    return profile.weight * duration_weight, request


def candidates(catalog: Catalog, *, limit: int = 500, year: int = 2027) -> tuple[TripRequest, ...]:
    """Balance destinations, then choose their most plausible uncovered scenarios."""
    return weighted_candidates(
        catalog,
        DESTINATIONS,
        _compose,
        limit=limit,
        year=year,
        priority_by_key=DESTINATION_PRIORITIES,
    )
