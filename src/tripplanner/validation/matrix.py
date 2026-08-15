"""The request matrix the corpus is generated from.

Volume is cheap from templates; what only the real planner can give us is the
shapes it actually produces. So these requests are chosen for *variety* -- each
one puts the planner somewhere structurally different -- rather than to cover a
destination list.

Each request must be complete enough to plan in a single turn. A probe on
2026-08-15 spent real money on "Plan a 3 day trip to Coorg for 2 adults", which
bought a clarifying question and no itinerary, because it never said where the
traveller was starting from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TripRequest:
    slug: str
    #: What structural shape this request is here to produce.
    shape: str
    message: str


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
