"""Weighted trip scenarios for travelers leaving India for international destinations."""

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

PARTIES = {
    party.key: party
    for party in (
        Party("solo", "1 adult travelling solo on an Indian passport"),
        Party("couple", "2 adults travelling as a couple on Indian passports"),
        Party("friends", "4 adult friends travelling on Indian passports"),
        Party("young-family", "2 adults and 2 children aged 6 and 10 on Indian passports"),
        Party("senior-couple", "2 adults aged 64 and 70 on Indian passports"),
        Party(
            "three-generation",
            "4 adults and 1 child aged 8 on Indian passports, including grandparents",
        ),
    )
}

EMPHASES = {
    emphasis.key: emphasis
    for emphasis in (
        Emphasis(
            "first-trip",
            "first international trip",
            "Prioritize simple entry preparation, direct routing and low-friction transfers.",
        ),
        Emphasis(
            "family",
            "family attractions and easy pacing",
            "Use child-friendly attractions, practical meals and one main area per day.",
        ),
        Emphasis(
            "honeymoon",
            "honeymoon and private downtime",
            "Prioritize romantic stays, privacy, downtime and one special experience.",
        ),
        Emphasis(
            "food",
            "regional food and culture",
            "Make regional food and local culture central to the itinerary.",
        ),
        Emphasis(
            "nature",
            "nature and outdoors",
            "Focus on scenery and realistic, season-aware outdoor experiences.",
        ),
        Emphasis(
            "heritage",
            "history and culture",
            "Focus on history, architecture, museums and local culture.",
        ),
        Emphasis(
            "pilgrimage",
            "pilgrimage and ritual access",
            "Prioritize ritual dates, permits, health needs and accessible group movement.",
        ),
        Emphasis(
            "vfr",
            "visiting family plus selective leisure",
            "Keep flexible family time and add only geographically practical sightseeing.",
        ),
        Emphasis(
            "budget",
            "value-focused whole-trip planning",
            "Control the whole-trip cost and support major estimates with current evidence.",
        ),
        Emphasis(
            "premium",
            "premium comfort and low-friction transfers",
            "Prioritize excellent stays, comfort and efficient transfers.",
        ),
    )
}


def _p(party: str, emphasis: str, weight: int, rationale: str) -> VisitorProfile:
    return VisitorProfile(party, emphasis, weight, rationale)


def _d(
    key: str,
    phrase: str,
    origin: str,
    month: int,
    durations: tuple[tuple[int, int], ...],
    profiles: tuple[VisitorProfile, ...],
    priority: int,
    evidence_note: str,
    confidence: str,
) -> MarketDestination:
    return MarketDestination(
        key,
        phrase,
        origin,
        month,
        durations,
        profiles,
        priority,
        evidence_note,
        confidence,
    )


DESTINATIONS: tuple[MarketDestination, ...] = (
    _d(
        "uae",
        "Dubai with an optional Abu Dhabi day",
        "Mumbai",
        1,
        ((5, 10), (4, 9), (6, 8)),
        (
            _p("young-family", "family", 10, "A core short-haul family and attractions trip."),
            _p("couple", "first-trip", 9, "A simple first international break is plausible."),
            _p("friends", "premium", 7, "Friends combine city highlights and lively evenings."),
            _p("three-generation", "family", 6, "Mixed ages stress transport and heat planning."),
        ),
        10,
        "Dubai DET reports 19.59M international overnight visitors in 2025; "
        "the India share was not extracted.",
        "high inclusion; medium weight",
    ),
    _d(
        "thailand",
        "Bangkok and Phuket or Krabi",
        "Delhi",
        1,
        ((6, 10), (7, 9), (5, 8), (8, 6)),
        (
            _p("friends", "food", 10, "Friends need a city, food and beach balance."),
            _p("couple", "honeymoon", 9, "Couples commonly combine city and beach downtime."),
            _p("young-family", "family", 7, "Families need transfer and attraction pacing."),
            _p("solo", "budget", 5, "Solo value travel is a useful planning shape."),
        ),
        9,
        "Mainstream short-haul catalog prior; official entry rules require live verification.",
        "medium",
    ),
    _d(
        "singapore",
        "Singapore",
        "Chennai",
        6,
        ((5, 10), (4, 9), (6, 8)),
        (
            _p("young-family", "family", 10, "Family attractions are a primary itinerary shape."),
            _p("couple", "first-trip", 9, "Compact routing suits a first international trip."),
            _p("three-generation", "family", 7, "Accessible transport supports mixed ages."),
            _p("friends", "food", 6, "Food and neighborhoods create a distinct group trip."),
        ),
        7,
        "Singapore ICA explicitly covers Indian visa and conditional transit requirements.",
        "high",
    ),
    _d(
        "bali",
        "Bali",
        "Bangalore",
        6,
        ((7, 10), (6, 9), (8, 8), (5, 6)),
        (
            _p("couple", "honeymoon", 10, "Privacy, stays and transfers define the honeymoon."),
            _p("friends", "nature", 8, "Friends combine coast, culture and outdoors."),
            _p("young-family", "family", 6, "Families need restrained transfers and pool time."),
            _p("solo", "budget", 4, "A lower-weight solo scenario tests practical transport."),
        ),
        7,
        "Strong leisure archetype catalog prior; official statistics extraction was blocked.",
        "medium-low",
    ),
    _d(
        "vietnam",
        "Hanoi, Ha Long Bay and central Vietnam",
        "Kolkata",
        2,
        ((7, 10), (8, 9), (6, 8), (9, 6)),
        (
            _p("couple", "food", 10, "Food and multi-city culture suit couples."),
            _p("friends", "budget", 9, "Value-focused friends need route-cost realism."),
            _p("young-family", "heritage", 6, "Families require fewer hotel changes."),
            _p("solo", "food", 5, "Solo food travel is a useful distinct shape."),
        ),
        7,
        "Growth and value catalog prior pending comparable India-specific official data.",
        "medium-low",
    ),
    _d(
        "maldives",
        "the Maldives",
        "Bangalore",
        2,
        ((5, 10), (4, 9), (6, 8)),
        (
            _p("couple", "honeymoon", 10, "Resort, meal plan and transfer choices dominate."),
            _p("young-family", "premium", 7, "Families need child policy and transfer realism."),
            _p("three-generation", "premium", 4, "Accessibility makes a useful resort edge case."),
        ),
        6,
        "Distinct resort-transfer archetype; official tourism statistics blocked extraction.",
        "medium-low",
    ),
    _d(
        "malaysia",
        "Kuala Lumpur, Genting and Penang",
        "Chennai",
        7,
        ((6, 10), (5, 9), (7, 8)),
        (
            _p("young-family", "family", 10, "Family attractions and a short circuit are central."),
            _p("three-generation", "family", 8, "Mixed-age transport choices matter."),
            _p("friends", "food", 7, "Food and city neighborhoods suit friends."),
            _p("couple", "first-trip", 6, "A compact regional trip suits newer travelers."),
        ),
        5,
        "Family and city-circuit catalog prior; verify current immigration rules.",
        "medium",
    ),
    _d(
        "sri-lanka",
        "Colombo, Kandy and the south coast",
        "Chennai",
        2,
        ((7, 10), (6, 9), (8, 8), (5, 6)),
        (
            _p(
                "young-family", "heritage", 10, "A regional family circuit needs restrained drives."
            ),
            _p("couple", "nature", 9, "Couples combine culture, hills and coast."),
            _p(
                "three-generation",
                "heritage",
                6,
                "Road time and accessibility shape mixed-age trips.",
            ),
            _p("friends", "budget", 5, "A value circuit is a useful group scenario."),
        ),
        5,
        "SLTDA reports 2.36M total arrivals in 2025, up 15.1%; India share is not asserted here.",
        "high inclusion; medium weight",
    ),
    _d(
        "saudi-pilgrimage",
        "Makkah and Madinah for Umrah",
        "Hyderabad",
        2,
        ((9, 10), (7, 9), (12, 8), (16, 5)),
        (
            _p(
                "three-generation",
                "pilgrimage",
                10,
                "Permits, rituals and elder access control the plan.",
            ),
            _p("senior-couple", "pilgrimage", 10, "Health, proximity and rest are essential."),
            _p("young-family", "pilgrimage", 6, "Children change movement and ritual pacing."),
        ),
        5,
        "Nusuk is the official Saudi pilgrimage and permit platform.",
        "high",
    ),
    _d(
        "nepal",
        "Kathmandu and Pokhara",
        "Delhi",
        10,
        ((6, 10), (5, 9), (7, 8), (4, 6)),
        (
            _p(
                "three-generation",
                "pilgrimage",
                9,
                "Regional pilgrimage and family travel overlap.",
            ),
            _p("friends", "nature", 9, "Friends can emphasize mountain activities."),
            _p("couple", "nature", 8, "Couples combine heritage and scenery."),
            _p("senior-couple", "pilgrimage", 6, "Altitude and access need gentle pacing."),
        ),
        4,
        "High-relevance regional catalog prior; official source extraction was incomplete.",
        "medium-low",
    ),
    _d(
        "bhutan",
        "Thimphu, Punakha and Paro",
        "Kolkata",
        10,
        ((7, 10), (8, 9), (6, 8)),
        (
            _p("couple", "heritage", 10, "A paced culture-and-scenery circuit is core."),
            _p("young-family", "nature", 7, "Families need child-aware walks and transfers."),
            _p("friends", "nature", 6, "Interest groups can add practical outdoor activity."),
            _p("senior-couple", "premium", 5, "Comfort and gradients drive feasibility."),
        ),
        3,
        "Distinct regulated-tourism and gateway shape; official page extraction was incomplete.",
        "medium-low",
    ),
    _d(
        "mauritius",
        "Mauritius",
        "Mumbai",
        7,
        ((7, 10), (6, 9), (8, 8)),
        (
            _p(
                "couple",
                "honeymoon",
                10,
                "A resort-led honeymoon alternative needs island touring balance.",
            ),
            _p("young-family", "premium", 8, "Family resorts and drives create a distinct shape."),
            _p("three-generation", "premium", 5, "Accessibility and rooming require scrutiny."),
        ),
        3,
        "Resort-island catalog prior pending stronger India-specific evidence.",
        "medium-low",
    ),
    _d(
        "turkey",
        "Istanbul and Cappadocia",
        "Delhi",
        5,
        ((8, 10), (7, 9), (9, 8)),
        (
            _p("couple", "heritage", 10, "A two-region history trip is a core shape."),
            _p("friends", "food", 8, "Friends combine food, city life and landscapes."),
            _p("young-family", "heritage", 6, "Families need flight and activity pacing."),
            _p("senior-couple", "premium", 5, "Comfort and walking affect the route."),
        ),
        4,
        "Mid-haul multi-city catalog prior; verify visa and advisory status live.",
        "medium-low",
    ),
    _d(
        "schengen-classic",
        "Paris, Switzerland and northern Italy",
        "Mumbai",
        5,
        ((11, 10), (14, 9), (9, 7)),
        (
            _p("young-family", "heritage", 10, "A first family circuit needs fewer hotel changes."),
            _p("couple", "premium", 9, "Rail, stays and landmark pacing define the trip."),
            _p("three-generation", "premium", 6, "Accessibility and transfers shape feasibility."),
            _p("friends", "budget", 5, "A value group circuit tests cost realism."),
        ),
        7,
        "European Commission confirms common Schengen short-stay rules across 29 countries.",
        "high",
    ),
    _d(
        "uk",
        "London with a regional United Kingdom extension",
        "Delhi",
        6,
        ((10, 10), (7, 9), (14, 7)),
        (
            _p(
                "three-generation",
                "vfr",
                10,
                "Family time must anchor rather than overfill the plan.",
            ),
            _p("young-family", "vfr", 9, "A host-city family trip needs flexible days."),
            _p("couple", "heritage", 7, "A leisure trip can add one practical region."),
            _p("senior-couple", "vfr", 6, "Comfort and host time are primary."),
        ),
        4,
        "Official UK visa decision flow exists; processing details require live verification.",
        "high process; medium weight",
    ),
    _d(
        "usa",
        "New York with one practical United States extension",
        "Delhi",
        6,
        ((14, 10), (10, 9), (18, 7)),
        (
            _p("three-generation", "vfr", 10, "VFR time and long-haul recovery control the trip."),
            _p("young-family", "vfr", 9, "Families need restrained domestic travel."),
            _p("couple", "premium", 6, "A leisure pair can add one coherent region."),
            _p("senior-couple", "vfr", 6, "Jet lag and mobility need explicit buffers."),
        ),
        4,
        "Long-haul VFR catalog prior; U.S. State Department source blocked extraction.",
        "medium",
    ),
    _d(
        "australia",
        "Sydney and Melbourne",
        "Bangalore",
        1,
        ((12, 10), (14, 9), (10, 8)),
        (
            _p("young-family", "vfr", 10, "VFR and city leisure need flexible family time."),
            _p("couple", "nature", 8, "A two-city trip can add restrained nature days."),
            _p("three-generation", "vfr", 7, "Long-haul recovery and accessibility matter."),
            _p("friends", "premium", 5, "A comfort-led friends circuit is lower priority."),
        ),
        3,
        "Australian Home Affairs documents visitor and sponsored-family visa streams.",
        "high",
    ),
    _d(
        "japan",
        "Tokyo, Kyoto and Osaka",
        "Delhi",
        4,
        ((8, 10), (10, 9), (7, 8)),
        (
            _p("couple", "heritage", 10, "Rail and seasonal culture define the circuit."),
            _p("young-family", "family", 8, "Families need age-aware rail and attraction days."),
            _p("friends", "food", 8, "Food and interest-led neighborhoods suit friends."),
            _p("senior-couple", "premium", 5, "Walking and station transfers need scrutiny."),
        ),
        4,
        "Japan MOFA publishes current short-stay visa procedures and processing guidance.",
        "high",
    ),
    _d(
        "south-korea",
        "Seoul and Busan",
        "Delhi",
        4,
        ((7, 10), (6, 9), (9, 7)),
        (
            _p("friends", "food", 10, "Food and contemporary culture lead this trip."),
            _p("couple", "heritage", 8, "Couples can balance city culture and coast."),
            _p("young-family", "family", 5, "Family attractions form a lower-weight variant."),
            _p("solo", "budget", 4, "Solo interest travel adds behavioral breadth."),
        ),
        2,
        "Interest-led premium Asia catalog prior; entry route requires live verification.",
        "medium",
    ),
    _d(
        "hong-kong-macau",
        "Hong Kong and Macau",
        "Mumbai",
        11,
        ((5, 10), (4, 9), (6, 8)),
        (
            _p(
                "young-family", "family", 10, "Theme attractions and compact transit suit families."
            ),
            _p("couple", "food", 8, "Food and neighborhoods create a short couple trip."),
            _p("friends", "premium", 6, "Friends combine urban highlights and evenings."),
            _p("three-generation", "family", 5, "Border and walking logistics need scrutiny."),
        ),
        2,
        "Compact urban catalog prior; Hong Kong and Macau entry rules require separate checks.",
        "medium",
    ),
    _d(
        "georgia",
        "Tbilisi and the Georgian Caucasus",
        "Delhi",
        5,
        ((7, 10), (6, 9), (8, 7)),
        (
            _p("couple", "nature", 10, "An emerging scenery-and-culture trip is plausible."),
            _p("friends", "budget", 8, "Value-focused friends need route realism."),
            _p("young-family", "heritage", 5, "A lower-weight family circuit adds coverage."),
        ),
        1,
        "Emerging-destination catalog prior without verified market-share evidence.",
        "low",
    ),
    _d(
        "azerbaijan",
        "Baku and the surrounding Azerbaijan region",
        "Delhi",
        4,
        ((6, 10), (5, 9), (7, 7)),
        (
            _p("couple", "heritage", 10, "A compact emerging city-and-region trip."),
            _p("friends", "budget", 8, "Friends add value and evening considerations."),
            _p("young-family", "family", 5, "Family coverage remains deliberately lower weight."),
        ),
        1,
        "Emerging-destination catalog prior without verified market-share evidence.",
        "low",
    ),
    _d(
        "kazakhstan",
        "Almaty and the surrounding mountain region",
        "Delhi",
        9,
        ((6, 10), (5, 9), (7, 7)),
        (
            _p("friends", "nature", 10, "A short-haul mountain group trip is distinct."),
            _p("couple", "nature", 8, "Couples combine city and outdoors."),
            _p("young-family", "family", 5, "Weather and transfers need family scrutiny."),
        ),
        1,
        "Emerging Central Asia catalog prior; verify connectivity and entry rules live.",
        "low",
    ),
    _d(
        "seychelles",
        "the Seychelles",
        "Mumbai",
        7,
        ((7, 10), (6, 9), (8, 7)),
        (
            _p("couple", "honeymoon", 10, "A multi-island premium honeymoon is distinct."),
            _p("young-family", "premium", 6, "Family island transfers create a useful variant."),
        ),
        1,
        "Niche island catalog prior without extracted India-specific official statistics.",
        "low",
    ),
    _d(
        "egypt",
        "Cairo, Luxor and Aswan",
        "Mumbai",
        11,
        ((8, 10), (9, 9), (7, 7)),
        (
            _p("couple", "heritage", 10, "A history-led multi-city circuit is core."),
            _p("young-family", "heritage", 7, "Families need restrained heat and transfer days."),
            _p("friends", "budget", 6, "A value group circuit tests evidence quality."),
            _p("senior-couple", "premium", 5, "Heat, walking and cruise access matter."),
        ),
        1,
        "Niche heritage catalog prior; advisories and entry rules require live verification.",
        "low",
    ),
    _d(
        "cambodia-laos",
        "Cambodia and Laos",
        "Kolkata",
        1,
        ((8, 10), (7, 9), (9, 7)),
        (
            _p("couple", "heritage", 10, "A temple-and-culture combination needs logical routing."),
            _p("friends", "budget", 8, "Value-focused friends add overland and flight trade-offs."),
            _p("solo", "heritage", 5, "Experienced solo travel is a lower-weight scenario."),
        ),
        1,
        "Emerging combination catalog prior without verified market-share evidence.",
        "low",
    ),
)


def _date_phrase(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day} to {end.day} {start.strftime('%B')} {start.year}"
    return f"{start.day} {start.strftime('%B')} to {end.day} {end.strftime('%B')} {end.year}"


def _compose(
    destination: MarketDestination,
    profile: VisitorProfile,
    days: int,
    duration_weight: int,
    year: int,
) -> tuple[int, TripRequest]:
    party = PARTIES[profile.party]
    emphasis = EMPHASES[profile.emphasis]
    slug = f"india-outbound-{destination.key}-{emphasis.key}-{party.key}-{days}d"
    start = date(year, destination.month, 1) + timedelta(days=stable(slug) % 18)
    request = TripRequest(
        slug=slug,
        shape=f"India outbound: {destination.phrase}, {emphasis.shape}, {party.key}, {days} days",
        message=(
            f"Plan a {days} day trip to {destination.phrase} from {destination.origin} for "
            f"{party.phrase}, {_date_phrase(start, start + timedelta(days=days))}. "
            f"{emphasis.clause} Verify current official entry requirements and Indian "
            "government travel advisories before treating the plan as bookable."
        ),
        destination=f"india-outbound:{destination.key}",
        emphasis=emphasis.key,
        party=party.key,
        days=days,
        scenario_expectations=(
            f"Keep the destination scope to {destination.phrase}.",
            f"Plan appropriately for {party.phrase}.",
            emphasis.clause,
            f"Keep the requested {days}-day duration.",
            "Do not promise visa eligibility, approval, fees or processing time from static data.",
            f"Heuristic audience rationale: {profile.rationale}",
            f"Evidence posture ({destination.evidence_confidence}): {destination.evidence_note}",
        ),
        budget_evidence_required=emphasis.key == "budget",
    )
    return destination.priority * profile.weight * duration_weight, request


def candidates(catalog: Catalog, *, limit: int = 500, year: int = 2027) -> tuple[TripRequest, ...]:
    """Return balanced India-outbound scenarios in destination-priority order."""
    return weighted_candidates(catalog, DESTINATIONS, _compose, limit=limit, year=year)
