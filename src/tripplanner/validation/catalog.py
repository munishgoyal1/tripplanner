"""What the corpus already covers, so the next request can be something else.

Every generated trip costs real money, so the builder must never pay twice for
the same shape. The catalog reads the manifest once and then answers, in
constant time, whether a candidate would repeat a request the corpus already
holds -- by slug, by exact signature, or by re-using an emphasis on a
destination that already has one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class Signature:
    """The axes that make one request structurally different from another."""

    destination: str
    emphasis: str
    party: str
    days: int

    @property
    def key(self) -> str:
        return "|".join(
            (_norm(self.destination), _norm(self.emphasis), _norm(self.party), str(self.days))
        )


class Catalog:
    """A lookup over everything the corpus has already produced."""

    def __init__(self, produced: Iterable[dict[str, Any]] = ()) -> None:
        self.slugs: set[str] = set()
        self.keys: set[str] = set()
        self.destinations: Counter[str] = Counter()
        self._emphases: dict[str, set[str]] = {}
        for entry in produced:
            self.add_entry(entry)

    def add_entry(self, entry: dict[str, Any]) -> None:
        slug = str(entry.get("slug") or "")
        if slug:
            self.slugs.add(slug)
        key = str(entry.get("signature") or "")
        if key:
            self.keys.add(key)
        destination = _norm(entry.get("destination"))
        if not destination:
            return
        # A legacy entry carries only its hand-written shape, which still tells
        # us this destination has been used for something.
        emphasis = _norm(entry.get("emphasis") or entry.get("shape"))
        self.destinations[destination] += 1
        self._emphases.setdefault(destination, set()).add(emphasis)

    def add(self, signature: Signature, slug: str) -> None:
        self.add_entry(
            {
                "slug": slug,
                "signature": signature.key,
                "destination": signature.destination,
                "emphasis": signature.emphasis,
            }
        )

    def covers(self, signature: Signature, slug: str) -> bool:
        """Whether this request would repeat something the corpus already has."""
        if slug in self.slugs or signature.key in self.keys:
            return True
        destination = _norm(signature.destination)
        return _norm(signature.emphasis) in self._emphases.get(destination, set())

    def times_used(self, destination: str) -> int:
        return self.destinations[_norm(destination)]

    def summary(self) -> dict[str, Any]:
        return {
            "trips": len(self.slugs),
            "destinations": len(self.destinations),
            "most_used": self.destinations.most_common(3),
        }
