"""Trip-specific evaluation inputs and provenance, independent of acquisition."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

REAL = "real"
REVISION = "revision"
SYNTHETIC = "synthetic"
TEMPLATE = "template"
GOLDEN = "golden"
REFERENCE = "reference"
MUTATED = "mutated"

PROVENANCES = (REAL, REVISION, SYNTHETIC, TEMPLATE, GOLDEN, REFERENCE, MUTATED)

GENERATED_FINAL = "generated-final"
OWNER_CURRENT = "owner-current"
REVISION_COHORT = "revision"
PARTIAL = "partial"
CLONE = "clone"
COHORTS = (GENERATED_FINAL, OWNER_CURRENT, REVISION_COHORT, PARTIAL, CLONE)

_NON_SEMANTIC_KEYS = frozenset(
    {
        "_attachments",
        "_etag",
        "_rid",
        "_self",
        "_ts",
        "account_id",
        "created_at",
        "id",
        "revision",
        "trip_id",
        "updated_at",
        "user_id",
    }
)


@dataclass(frozen=True)
class ProvenanceLink:
    """One persisted occurrence of a semantic logical trip."""

    id: str
    provenance: str
    source: str
    user_id: str = ""
    trip_id: str = ""


@dataclass(frozen=True)
class CorpusRecord:
    """One trip plan plus enough context to render and attribute it."""

    id: str
    provenance: str
    source: str
    plan: dict[str, Any]
    #: Cached ``name|city`` place entries, so a record can be checked offline.
    places: dict[str, Any] = field(default_factory=dict)
    provenance_links: tuple[ProvenanceLink, ...] = ()
    case_id: str = ""
    request: str = ""
    preferences: dict[str, Any] = field(default_factory=dict)
    final_reply: str = ""
    steps: tuple[dict[str, Any], ...] = ()
    generation: dict[str, Any] = field(default_factory=dict)

    @property
    def case_identity(self) -> str:
        return self.case_id or self.id

    def evaluation_input(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "request": self.request,
            "preferences": self.preferences,
            "final_reply": self.final_reply,
            "steps": self.steps,
            "generation": self.generation,
        }

    @property
    def artifact_id(self) -> str:
        payload = {"case_id": self.case_identity, **self.evaluation_input()}
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @property
    def destination(self) -> str:
        return str(self.plan.get("destination") or "")

    @property
    def logical_trip_id(self) -> str:
        return semantic_fingerprint(self.plan)

    @property
    def links(self) -> tuple[ProvenanceLink, ...]:
        if self.provenance_links:
            return self.provenance_links
        return (
            ProvenanceLink(
                id=self.id,
                provenance=self.provenance,
                source=self.source,
                user_id=str(self.plan.get("user_id") or ""),
                trip_id=str(self.plan.get("trip_id") or self.plan.get("id") or ""),
            ),
        )

    @property
    def cohorts(self) -> tuple[str, ...]:
        links = self.links
        has_final = any(link.provenance != REVISION for link in links)
        cohorts: list[str] = []
        if not has_final:
            cohorts.append(REVISION_COHORT)
        if is_partial(self.plan):
            cohorts.append(PARTIAL)
        elif has_final:
            generated = self.provenance == SYNTHETIC or any(
                link.user_id.startswith("corpus-") for link in links
            )
            cohorts.append(GENERATED_FINAL if generated else OWNER_CURRENT)
        if len(links) > 1:
            cohorts.append(CLONE)
        return tuple(cohorts)

    @property
    def executive(self) -> bool:
        return (
            REVISION_COHORT not in self.cohorts
            and PARTIAL not in self.cohorts
            and bool({GENERATED_FINAL, OWNER_CURRENT}.intersection(self.cohorts))
        )


def _is_plan(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("destination") or value.get("trip_id"))


def _semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_value(item)
            for key, item in sorted(value.items())
            if key not in _NON_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    return value


def semantic_fingerprint(plan: dict[str, Any]) -> str:
    """Stable plan identity without account, lane, or persistence metadata."""
    encoded = json.dumps(
        _semantic_value(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def is_partial(plan: dict[str, Any]) -> bool:
    itinerary = plan.get("day_wise_itinerary")
    if not isinstance(itinerary, list) or not itinerary:
        return True
    days = [day for day in itinerary if isinstance(day, dict)]
    return not days or any(not isinstance(day.get("stops"), list) for day in days)
