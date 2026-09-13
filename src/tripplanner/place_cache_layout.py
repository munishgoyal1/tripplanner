"""Where one cached Google place lives in the ``places_cache`` Cosmos container.

Every reader and writer of that container -- the app's durable place cache, the
optional secondary cache, the production cache sync, the corpus place cache and
the debug-store restore -- derives an item's identity from here, so the layout
cannot drift between them.

Why places are bucketed
-----------------------
Places are global, not per-user, so they used to share one logical partition,
``_shared``. Provisioned throughput is spread across *physical* partitions and a
logical partition is pinned to exactly one of them, so a container whose every
read and write names the same partition value cannot use more than one physical
partition's share however many RU/s are provisioned -- and a trip build issues
its place reads eight at a time (``places_cache._MAX_WORKERS``). With
``CACHE_STABLE_FOREVER=1`` those rows also never expire, so the one partition
only grows toward Cosmos's 20 GB logical-partition limit.

The partition value is now a bucket derived from the item id, which is itself a
hash of the cache key. A place is still a point read -- its partition is computed,
never looked up -- and load spreads evenly over ``BUCKETS`` partitions, far more
than the physical partitions this account could reach.

The container's partition *path* stays ``/user_id``, as on every container in
``infra/modules/cosmos-data.bicep``: only the value changes, so no container has
to be recreated. ``storage_cosmos._strip_system_fields`` drops ``user_id`` from
returned bodies, which is harmless here because no place reader uses it.

Rows written before the change are still under ``LEGACY_PARTITION``. Readers fall
back to it on a miss and re-home what they find; ``scripts/migrate_places_cache_partitions.py``
moves the rest. See ``docs/operations/performance-cost.md``.
"""

from __future__ import annotations

import hashlib

CONTAINER = "places_cache"

#: The single partition every place used to share. Read only as a fallback.
LEGACY_PARTITION = "_shared"

PARTITION_PREFIX = "place-"

#: Two hex characters of a SHA-1 id: 256 evenly loaded logical partitions.
_BUCKET_HEX_CHARS = 2
BUCKETS = 16**_BUCKET_HEX_CHARS


def doc_id(key: str) -> str:
    """Cosmos-safe item id for a cache key (keys contain spaces, '/', '|')."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def partition(item_id: str) -> str:
    """The partition value a place item with ``item_id`` is stored under."""
    return f"{PARTITION_PREFIX}{item_id[:_BUCKET_HEX_CHARS].lower()}"


def is_place_partition(value: str) -> bool:
    """Whether ``value`` is one of the bucketed place partitions."""
    return str(value or "").startswith(PARTITION_PREFIX)


__all__ = [
    "BUCKETS",
    "CONTAINER",
    "LEGACY_PARTITION",
    "PARTITION_PREFIX",
    "doc_id",
    "is_place_partition",
    "partition",
]
