"""The request matrix the corpus is generated from.

Volume is cheap from templates; what only the real planner can give us is the
shapes it actually produces. So these requests are chosen for *variety* -- each
one puts the planner somewhere structurally different -- rather than to cover a
destination list.

Each request must be complete enough to plan in a single turn. A probe on
2026-08-15 spent real money on "Plan a 3 day trip to Coorg for 2 adults", which
bought a clarifying question and no itinerary, because it never said where the
traveller was starting from.

``REQUESTS`` is the hand-written seed set. Once it is exhausted the builder
composes further requests from the axis pools below, which deliberately use
destinations no seed mentions, so a generated request can never repeat a seed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from tripplanner.validation.catalog import Catalog, Signature


@dataclass(frozen=True)
class TripRequest:
    slug: str
    #: What structural shape this request is here to produce.
    shape: str
    message: str
    #: Set on a generated request; a seed carries its shape and nothing else.
    destination: str = ""
    emphasis: str = ""
    party: str = ""
    days: int = 0
    #: Human-readable contract used to judge scenario and preference fidelity.
    scenario_expectations: tuple[str, ...] = ()
    #: Budget evidence is a gate only when the request explicitly asks for it.
    budget_evidence_required: bool = False

    @property
    def signature(self) -> Signature:
        return Signature(
            destination=self.destination,
            emphasis=self.emphasis or self.shape,
            party=self.party,
            days=self.days,
        )


REQUESTS: tuple[TripRequest, ...] = (
    TripRequest(
        "goa-relaxed",
        "short domestic beach, relaxed pacing",
        "Plan a relaxed 4 day trip to Goa from Bangalore for 2 adults, "
        "10 to 14 March 2027. We want a slow pace, beaches and good food.",
    ),
    TripRequest(
        "goa-see-it-all",
        "same destination, opposite pacing",
        "Plan a packed 4 day Goa trip from Bangalore for 2 adults, 10 to 14 March 2027. "
        "We want to see as much as possible, early starts are fine.",
    ),
    TripRequest(
        "paris-longhaul",
        "international long haul with a connection",
        "Plan a 7 day trip to Paris from Bangalore for 2 adults, 5 to 12 April 2027, "
        "flying economy. Include the flights and a central hotel.",
    ),
    TripRequest(
        "tokyo-rail",
        "destination where rail should beat driving",
        "Plan a 6 day trip to Japan from Delhi for 2 adults, 3 to 9 April 2027, "
        "covering Tokyo and Kyoto. We are happy to use trains between cities.",
    ),
    TripRequest(
        "rajasthan-multicity",
        "regional multi-city circuit by road",
        "Plan an 8 day Rajasthan trip from Mumbai for 2 adults, 2 to 10 February 2027, "
        "covering Jaipur, Jodhpur and Udaipur by road.",
    ),
    TripRequest(
        "kerala-family-kids",
        "family with young children",
        "Plan a 6 day Kerala trip from Chennai for 2 adults and 2 children aged 4 and 7, "
        "12 to 18 December 2026. Keep travel days short and include a houseboat.",
    ),
    TripRequest(
        "shimla-seniors",
        "mobility-constrained travellers",
        "Plan a 5 day Shimla trip from Delhi for 2 adults and my parents aged 72 and 68, "
        "5 to 10 May 2027. My father uses a walking stick, so avoid long walks.",
    ),
    TripRequest(
        "ladakh-altitude",
        "altitude and acclimatisation constraints",
        "Plan a 7 day Leh Ladakh trip from Delhi for 2 adults, 1 to 8 July 2027, "
        "including acclimatisation days.",
    ),
    TripRequest(
        "dubai-visa",
        "visa-required short international",
        "Plan a 4 day Dubai trip from Hyderabad for 2 adults on Indian passports, "
        "20 to 24 November 2026, mid-range budget.",
    ),
    TripRequest(
        "andaman-ferry",
        "island hopping where the leg is a ferry",
        "Plan a 6 day Andaman trip from Kolkata for 2 adults, 8 to 14 January 2027, "
        "covering Port Blair and Havelock.",
    ),
    TripRequest(
        "varanasi-pilgrimage",
        "religious circuit across nearby cities",
        "Plan a 5 day Varanasi and Ayodhya pilgrimage from Pune for 2 adults, "
        "3 to 8 February 2027.",
    ),
    TripRequest(
        "coorg-monsoon",
        "monsoon season, weather-sensitive",
        "Plan a 4 day Coorg trip from Bangalore for 2 adults, 15 to 19 July 2027, "
        "during the monsoon.",
    ),
    TripRequest(
        "singapore-budget",
        "tight budget, international",
        "Plan a 5 day Singapore trip from Chennai for 2 adults, 4 to 9 June 2027, "
        "on a tight budget of INR 90000 total.",
        scenario_expectations=("Stay within the INR 90,000 whole-trip ceiling.",),
        budget_evidence_required=True,
    ),
    TripRequest(
        "swiss-luxury",
        "high budget, scenic rail",
        "Plan an 8 day Switzerland trip from Mumbai for 2 adults, 10 to 18 September 2027, "
        "premium hotels, scenic train journeys.",
    ),
    TripRequest(
        "manali-roadtrip",
        "self-drive road trip with stops en route",
        "Plan a 6 day Manali road trip driving from Delhi for 4 adults, "
        "1 to 7 October 2027, with stops on the way.",
    ),
    TripRequest(
        "bali-honeymoon",
        "couple, single destination, international",
        "Plan a 7 day Bali honeymoon from Bangalore for 2 adults, 12 to 19 November 2027, "
        "romantic hotels and sunsets.",
    ),
    TripRequest(
        "meghalaya-offbeat",
        "offbeat destination, sparse provider data",
        "Plan a 6 day Meghalaya trip from Guwahati for 2 adults, 2 to 8 November 2027, "
        "covering Shillong and Cherrapunji.",
    ),
    TripRequest(
        "weekend-pondicherry",
        "very short trip, two days only",
        "Plan a 2 day Pondicherry weekend from Chennai for 2 adults, "
        "6 to 8 March 2027.",
    ),
    TripRequest(
        "srilanka-multicountry",
        "international multi-city with internal flights",
        "Plan a 9 day Sri Lanka trip from Bangalore for 2 adults, 4 to 13 August 2027, "
        "covering Colombo, Kandy and Galle.",
    ),
    TripRequest(
        "destination-only-udaipur",
        "traveller arranges their own arrival",
        "Plan a 3 day Udaipur itinerary for 2 adults, 14 to 17 February 2027. "
        "I will arrange my own travel to Udaipur, just plan what to do there.",
    ),
    TripRequest(
        "vegetarian-jain-gujarat",
        "strict dietary constraint",
        "Plan a 5 day Gujarat trip from Mumbai for 2 adults, 7 to 12 December 2026, "
        "covering Ahmedabad and Kutch. We eat strictly Jain food.",
    ),
    TripRequest(
        "pet-friendly-lonavala",
        "travelling with a pet",
        "Plan a 3 day Lonavala trip from Mumbai for 2 adults with our dog, "
        "20 to 23 January 2027. Pet friendly stays only.",
    ),
    TripRequest(
        "solo-hampi",
        "solo traveller, heritage",
        "Plan a 4 day solo Hampi trip from Bangalore, 5 to 9 January 2027, "
        "on a modest budget.",
    ),
    TripRequest(
        "newyork-business",
        "long haul with fixed working hours",
        "Plan a 5 day New York trip from Delhi for 1 adult, 9 to 14 October 2027. "
        "I have meetings 9am to 2pm on the middle three days.",
    ),
)


def requests_by_slug() -> dict[str, TripRequest]:
    return {request.slug: request for request in REQUESTS}


@dataclass(frozen=True)
class Destination:
    key: str
    #: Dropped straight into the message, so it must read as a place to plan.
    phrase: str
    origin: str
    month: int


@dataclass(frozen=True)
class Party:
    key: str
    phrase: str


@dataclass(frozen=True)
class Emphasis:
    key: str
    shape: str
    clause: str


#: None of these appear in any seed message, which `tests` assert.
DESTINATIONS: tuple[Destination, ...] = (
    Destination("rishikesh", "Rishikesh", "Delhi", 3),
    Destination("darjeeling", "Darjeeling", "Kolkata", 4),
    Destination("gangtok", "Gangtok and north Sikkim", "Kolkata", 10),
    Destination("srinagar", "Srinagar and Gulmarg", "Delhi", 5),
    Destination("amritsar", "Amritsar", "Delhi", 11),
    Destination("mysore", "Mysore", "Bangalore", 9),
    Destination("ooty", "Ooty", "Coimbatore", 4),
    Destination("chikmagalur", "Chikmagalur", "Bangalore", 12),
    Destination("gokarna", "Gokarna", "Bangalore", 1),
    Destination("kaziranga", "Kaziranga", "Guwahati", 2),
    Destination("spiti", "Spiti Valley", "Delhi", 6),
    Destination("mahabalipuram", "Mahabalipuram", "Chennai", 12),
    Destination("tirupati", "Tirupati", "Hyderabad", 8),
    Destination("bhutan", "Bhutan covering Thimphu and Paro", "Delhi", 10),
    Destination("nepal", "Nepal covering Kathmandu and Pokhara", "Delhi", 3),
    Destination("vietnam", "Vietnam covering Hanoi and Ha Long Bay", "Mumbai", 11),
    Destination("thailand", "Thailand covering Bangkok and Krabi", "Chennai", 1),
    Destination("malaysia", "Malaysia covering Kuala Lumpur and Penang", "Chennai", 7),
    Destination("maldives", "the Maldives", "Bangalore", 2),
    Destination("istanbul", "Istanbul", "Delhi", 5),
    Destination("rome", "Rome and Florence", "Mumbai", 9),
    Destination("seoul", "Seoul", "Delhi", 4),
    Destination("muscat", "Muscat", "Hyderabad", 12),
    Destination("capetown", "Cape Town", "Mumbai", 11),
)

PARTIES: tuple[Party, ...] = (
    Party("couple", "2 adults"),
    Party("solo", "1 adult"),
    Party("young-family", "2 adults and 2 children aged 6 and 9"),
    Party("friends", "4 adults"),
    Party("three-generation", "4 adults and 1 child aged 8, including grandparents"),
)

EMPHASES: tuple[Emphasis, ...] = (
    Emphasis("food", "food-led itinerary", "We care most about local food."),
    Emphasis("budget", "tight budget ceiling", "Keep the trip under INR 80000 in total."),
    Emphasis("premium", "high budget, premium stays", "We want premium hotels throughout."),
    Emphasis("slow", "relaxed pacing with free time", "Keep the pace slow with free afternoons."),
    Emphasis(
        "packed",
        "dense pacing, maximum coverage",
        "We want to see as much as possible, early starts are fine.",
    ),
    Emphasis("outdoors", "outdoor and nature led", "Focus on the outdoors and nature."),
    Emphasis("heritage", "heritage and history led", "Focus on history and heritage sites."),
    Emphasis(
        "accessible",
        "mobility constraint",
        "One traveller cannot manage long walks or stairs.",
    ),
)

DURATIONS: tuple[int, ...] = (3, 5, 7)

#: Enough candidates to outlast any single run's budget without composing thousands.
DEFAULT_CANDIDATE_LIMIT = 500


def _stable(value: str) -> int:
    """A hash that does not move between processes, so a run is reproducible."""
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:8], 16)


def _date_phrase(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day} to {end.day} {start.strftime('%B')} {start.year}"
    return (
        f"{start.day} {start.strftime('%B')} to "
        f"{end.day} {end.strftime('%B')} {end.year}"
    )


def _compose(
    destination: Destination, party: Party, emphasis: Emphasis, days: int, year: int
) -> TripRequest:
    slug = f"{destination.key}-{emphasis.key}-{party.key}-{days}d"
    start = date(year, destination.month, 1) + timedelta(days=_stable(slug) % 18)
    dates = _date_phrase(start, start + timedelta(days=days))
    return TripRequest(
        slug=slug,
        shape=f"{destination.phrase}, {emphasis.shape}, {party.key}",
        message=(
            f"Plan a {days} day {destination.phrase} trip from {destination.origin} "
            f"for {party.phrase}, {dates}. {emphasis.clause}"
        ),
        destination=destination.key,
        emphasis=emphasis.key,
        party=party.key,
        days=days,
        scenario_expectations=(
            f"Use {destination.phrase} as the destination scope.",
            f"Plan for {party.phrase}.",
            emphasis.clause,
            f"Keep the requested {days}-day duration.",
        ),
        budget_evidence_required=emphasis.key == "budget",
    )


def candidates(
    catalog: Catalog, *, limit: int = DEFAULT_CANDIDATE_LIMIT, year: int = 2027
) -> tuple[TripRequest, ...]:
    """Novel requests, spread across destinations the corpus has used least."""
    grouped: dict[str, list[TripRequest]] = {}
    for destination in DESTINATIONS:
        for party in PARTIES:
            for emphasis in EMPHASES:
                for days in DURATIONS:
                    request = _compose(destination, party, emphasis, days, year)
                    if catalog.covers(request.signature, request.slug):
                        continue
                    grouped.setdefault(destination.key, []).append(request)
    for group in grouped.values():
        group.sort(key=lambda request: _stable(request.slug))

    order = sorted(grouped, key=lambda key: (catalog.times_used(key), _stable(key)))
    picked: list[TripRequest] = []
    depth = 0
    while order and (limit <= 0 or len(picked) < limit):
        progressed = False
        for key in order:
            group = grouped[key]
            if depth >= len(group):
                continue
            picked.append(group[depth])
            progressed = True
            if limit > 0 and len(picked) >= limit:
                break
        if not progressed:
            break
        depth += 1
    return tuple(picked)


def pending(catalog: Catalog, *, limit: int = DEFAULT_CANDIDATE_LIMIT) -> tuple[TripRequest, ...]:
    """Everything left to ask for: unused seeds first, then generated requests."""
    seeds = tuple(
        request
        for request in REQUESTS
        if not catalog.covers(request.signature, request.slug)
    )
    if limit > 0 and len(seeds) >= limit:
        return seeds[:limit]
    remaining = 0 if limit <= 0 else limit - len(seeds)
    return seeds + candidates(catalog, limit=remaining)
