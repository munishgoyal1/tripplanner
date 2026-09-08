"""Shared records and deterministic selection for weighted travel-market catalogs."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tripplanner.validation.catalog import Catalog
from tripplanner.validation.matrix import TripRequest


@dataclass(frozen=True)
class VisitorProfile:
    party: str
    emphasis: str
    weight: int
    rationale: str


@dataclass(frozen=True)
class MarketDestination:
    key: str
    phrase: str
    origin: str
    month: int
    durations: tuple[tuple[int, int], ...]
    profiles: tuple[VisitorProfile, ...]
    priority: int = 1
    evidence_note: str = "Catalog prior; no destination-specific source attached."
    evidence_confidence: str = "low"


ComposeRequest = Callable[
    [MarketDestination, VisitorProfile, int, int, int], tuple[int, TripRequest]
]


def stable(value: str) -> int:
    """Return a deterministic integer suitable for ordering catalog entries."""
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:8], 16)


def weighted_candidates(
    catalog: Catalog,
    destinations: tuple[MarketDestination, ...],
    compose: ComposeRequest,
    *,
    limit: int,
    year: int,
    priority_by_key: Mapping[str, int] | None = None,
) -> tuple[TripRequest, ...]:
    """Balance destinations, then choose their highest-weight exact-new scenarios."""
    grouped: dict[str, list[TripRequest]] = {}
    for destination in destinations:
        weighted = [
            compose(destination, profile, days, duration_weight, year)
            for profile in destination.profiles
            for days, duration_weight in destination.durations
        ]
        weighted.sort(key=lambda item: (-item[0], stable(item[1].slug)))
        grouped[destination.key] = [
            request
            for _, request in weighted
            if request.slug not in catalog.slugs and request.signature.key not in catalog.keys
        ]

    priorities = {
        destination.key: (
            priority_by_key.get(destination.key, destination.priority)
            if priority_by_key
            else destination.priority
        )
        for destination in destinations
    }
    order = sorted(grouped, key=lambda key: (-priorities[key], stable(key)))
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
