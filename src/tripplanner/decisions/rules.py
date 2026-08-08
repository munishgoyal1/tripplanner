"""The rule that separates a chosen option from the ones it beat.

Every comparison is reduced to *effective minutes*: the door-to-door time, plus
the part of the day the option destroys around itself, plus the traveller's own
money-for-time rate applied to the fare, plus a documented penalty for a mode
they have said they dislike. Scoring in one unit is what lets the explanation
sentence be generated from the same numbers the user sees.

Unpriced options are never given a free ride. When a comparison is only partly
priced, a fareless option has to win clearly on time before it is preferred over
an option whose total is actually known.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tripplanner.decisions.models import Option, TransportMode

USABLE_DAY_MIN = 600

# Money-for-time rate, in currency units per hour, by the trip's budget level.
# A shoestring traveller trades four hours to save fifty; a luxury traveller
# does not. These are the only place that trade-off is expressed.
_VALUE_OF_TIME_PER_HOUR = {
    "shoestring": 6.0,
    "budget": 10.0,
    "moderate": 18.0,
    "mid-range": 18.0,
    "comfort": 30.0,
    "premium": 45.0,
    "luxury": 60.0,
}
_DEFAULT_VALUE_OF_TIME = 18.0

_DISLIKED_MODE_PENALTY_MIN = 90.0
_PREFERRED_MODE_BONUS_MIN = 45.0

# An unpriced option must beat the best priced option by this much to be chosen.
_UNPRICED_MARGIN = 0.10
_CLOSE_CALL_MARGIN = 0.05

_MODE_NAMES = {
    TransportMode.FLIGHT: "the flight",
    TransportMode.TRAIN: "the train",
    TransportMode.ROAD: "driving",
    TransportMode.COACH: "the coach",
    TransportMode.FERRY: "the ferry",
    TransportMode.METRO: "the metro",
    TransportMode.WALK: "walking",
}

_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "INR": "₹", "JPY": "¥"}


@dataclass(frozen=True)
class TransportPrefs:
    budget_level: str = "moderate"
    travellers: int = 1
    disliked_modes: frozenset[TransportMode] = frozenset()
    preferred_modes: frozenset[TransportMode] = frozenset()


@dataclass
class RankResult:
    chosen_option_id: str
    rule_code: str
    rule_text: str
    rejected_because: dict[str, str] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)


def money(amount: float, currency: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get((currency or "").upper())
    rounded = f"{abs(amount):,.0f}"
    if symbol:
        return f"{symbol}{rounded}"
    return f"{rounded} {currency}".strip()


def duration(minutes: float) -> str:
    total = int(round(abs(minutes)))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def party_total(option: Option, travellers: int) -> float | None:
    """Fare for the whole party, so per-traveller and per-party quotes compare."""
    if option.price is None:
        return None
    if option.price.basis == "per_party":
        return option.price.amount
    return option.price.amount * max(1, travellers)


def _time_score(option: Option, prefs: TransportPrefs) -> float:
    score = float(option.door_to_door_min or option.duration_min or 0)
    score += max(0.0, option.day_cost) * USABLE_DAY_MIN
    if option.mode in prefs.disliked_modes:
        score += _DISLIKED_MODE_PENALTY_MIN
    if option.mode in prefs.preferred_modes:
        score -= _PREFERRED_MODE_BONUS_MIN
    return score


def _price_minutes(option: Option, prefs: TransportPrefs) -> float:
    total = party_total(option, prefs.travellers)
    if total is None:
        return 0.0
    rate = _VALUE_OF_TIME_PER_HOUR.get((prefs.budget_level or "").lower(), _DEFAULT_VALUE_OF_TIME)
    return total * 60.0 / rate


def rank(options: list[Option], prefs: TransportPrefs | None = None) -> RankResult | None:
    """Choose one option and produce the sentences that defend the choice."""
    usable = [option for option in options if option.id]
    if not usable:
        return None
    prefs = prefs or TransportPrefs()

    time_scores = {option.id: _time_score(option, prefs) for option in usable}
    priced = [option for option in usable if option.price is not None]
    unpriced = [option for option in usable if option.price is None]

    if priced and not unpriced:
        scores = {o.id: time_scores[o.id] + _price_minutes(o, prefs) for o in usable}
        winner = min(usable, key=lambda o: scores[o.id])
        rule_code = "door_to_door_time"
    elif not priced:
        scores = dict(time_scores)
        winner = min(usable, key=lambda o: scores[o.id])
        rule_code = "door_to_door_time_unpriced"
    else:
        scores = dict(time_scores)
        best_priced = min(priced, key=lambda o: time_scores[o.id])
        best_unpriced = min(unpriced, key=lambda o: time_scores[o.id])
        clear_win = time_scores[best_unpriced.id] < time_scores[best_priced.id] * (
            1 - _UNPRICED_MARGIN
        )
        winner = best_unpriced if clear_win else best_priced
        rule_code = "door_to_door_time_unpriced" if clear_win else "known_total_preferred"

    # "Close call" is only worth saying when the comparison was complete. When a
    # fare is missing, that is the more important thing to tell the user.
    ordered = sorted(usable, key=lambda o: scores[o.id])
    if rule_code == "door_to_door_time" and len(ordered) > 1:
        best, second = scores[ordered[0].id], scores[ordered[1].id]
        if best and abs(second - best) <= best * _CLOSE_CALL_MARGIN:
            rule_code = "close_call"

    return RankResult(
        chosen_option_id=winner.id,
        rule_code=rule_code,
        rule_text=_rule_text(rule_code, winner, prefs),
        rejected_because={
            option.id: _rejection(option, winner, prefs)
            for option in usable
            if option.id != winner.id
        },
        scores=scores,
    )


def _rule_text(rule_code: str, winner: Option, prefs: TransportPrefs) -> str:
    if rule_code == "close_call":
        return "Close call — picked on whole-journey time, with little between them"
    if rule_code == "known_total_preferred":
        return "Whole-journey time, and a fare we can actually see"
    if rule_code == "door_to_door_time_unpriced":
        return "Whole-journey time — no fare source covers this hop"
    if winner.mode in prefs.preferred_modes:
        return "Whole-journey time, weighted to how you said you like to travel"
    return "Whole-journey time, not the time in the vehicle"


def _rejection(option: Option, winner: Option, prefs: TransportPrefs) -> str:
    parts: list[str] = []

    loser_total = party_total(option, prefs.travellers)
    winner_total = party_total(winner, prefs.travellers)
    if loser_total is not None and winner_total is not None:
        gap = loser_total - winner_total
        currency = (option.price.currency if option.price else "") or ""
        if abs(gap) >= 1:
            parts.append(
                f"costs {money(gap, currency)} more"
                if gap > 0
                else f"saves {money(gap, currency)}"
            )
    elif loser_total is None:
        parts.append("has no fare we can verify")

    loser_time = option.door_to_door_min or option.duration_min
    winner_time = winner.door_to_door_min or winner.duration_min
    if loser_time is not None and winner_time is not None:
        gap = loser_time - winner_time
        if abs(gap) >= 15:
            parts.append(
                f"takes {duration(gap)} longer door to door"
                if gap > 0
                else f"is {duration(gap)} quicker door to door"
            )

    if option.day_cost > winner.day_cost + 0.15:
        parts.append("turns the day into a transfer day")
    elif option.mode in prefs.disliked_modes:
        parts.append("is a way you have said you would rather not travel")

    if not parts:
        return f"Close to {_MODE_NAMES.get(winner.mode, 'the chosen option')} on every measure."
    sentence = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return sentence[0].upper() + sentence[1:] + "."
