"""Provider fallback execution with TTL cache and source evidence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from tripplanner.providers.cache import ProviderCacheEntry, ProviderTTLCache
from tripplanner.providers.models import QuoteStatus

T = TypeVar("T")


@dataclass(frozen=True)
class ProviderChainResult(Generic[T]):
    value: T
    provider: str
    quote_status: QuoteStatus
    cache_hit: bool = False
    checked_at: object | None = None
    expires_at: object | None = None
    errors: list[str] = field(default_factory=list)


def run_provider_chain(
    *,
    providers: Sequence[object],
    cache: ProviderTTLCache[T],
    cache_key: str,
    ttl_seconds: int,
    refresh: bool,
    empty_value: T,
    call: Callable[[object], T],
) -> ProviderChainResult[T]:
    """Run providers in order, using cache first and falling through on errors.

    Providers are expected to expose a `name` attribute. Empty list results are
    treated as unavailable and allow the next provider to try.
    """

    if not refresh:
        cached = cache.get(cache_key)
        if cached:
            return ProviderChainResult(
                value=cached.value,
                provider=cached.provider,
                quote_status=QuoteStatus.CACHED,
                cache_hit=True,
                checked_at=cached.checked_at,
                expires_at=cached.expires_at,
            )

    errors: list[str] = []
    for provider in providers:
        provider_name = str(getattr(provider, "name", provider.__class__.__name__))
        try:
            value = call(provider)
        except Exception as exc:  # provider boundaries must degrade
            errors.append(f"{provider_name}: {exc}")
            continue
        if isinstance(value, list) and not value:
            errors.append(f"{provider_name}: no availability")
            continue
        cache_entry: ProviderCacheEntry[T] = cache.set(
            cache_key,
            value,
            provider=provider_name,
            ttl_seconds=ttl_seconds,
        )
        return ProviderChainResult(
            value=value,
            provider=provider_name,
            quote_status=QuoteStatus.LIVE,
            checked_at=cache_entry.checked_at,
            expires_at=cache_entry.expires_at,
            errors=errors,
        )

    return ProviderChainResult(
        value=empty_value,
        provider="none",
        quote_status=QuoteStatus.UNAVAILABLE if not errors else QuoteStatus.PROVIDER_ERROR,
        errors=errors,
    )
