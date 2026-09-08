"""Planning decisions as first-class trip data.

Everything in this package is pure: no network, no model call, no storage. A
decision's ranking, its explanation sentences and its size limits are functions
of data, so the words the user reads can never drift from the numbers they
describe.
"""

from __future__ import annotations

from tripplanner.decisions.apply import ApplyResult, apply_override, restore
from tripplanner.decisions.models import (
    Decision,
    FareBasis,
    Option,
    OverrideRecord,
    Price,
    PricedState,
    Source,
    TransportMode,
    UnpricedReason,
    decision_from_dict,
    decision_to_dict,
)
from tripplanner.decisions.rules import RankResult, TransportPrefs, rank
from tripplanner.decisions.store import (
    MAX_DECISIONS_PER_TRIP,
    MAX_OPTIONS_PER_DECISION,
    list_decisions,
    prune_decisions,
    upsert_decision,
)

__all__ = [
    "MAX_DECISIONS_PER_TRIP",
    "MAX_OPTIONS_PER_DECISION",
    "ApplyResult",
    "Decision",
    "FareBasis",
    "Option",
    "OverrideRecord",
    "Price",
    "PricedState",
    "RankResult",
    "Source",
    "TransportMode",
    "TransportPrefs",
    "UnpricedReason",
    "apply_override",
    "decision_from_dict",
    "decision_to_dict",
    "list_decisions",
    "prune_decisions",
    "rank",
    "restore",
    "upsert_decision",
]
