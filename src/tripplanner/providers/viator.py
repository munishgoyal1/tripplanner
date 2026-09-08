"""Read-only Viator activity discovery and schedule adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from tripplanner import http_client
from tripplanner.providers.models import ActivityOffer, ActivitySearchQuery, Money, QuoteStatus


class ViatorError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration(product: dict[str, Any]) -> dict[str, int] | None:
    value = product.get("duration") or {}
    fixed = value.get("fixedDurationInMinutes")
    if fixed is not None:
        return {"from": int(fixed), "to": int(fixed)}
    start = value.get("variableDurationFromMinutes")
    end = value.get("variableDurationToMinutes")
    if start is None and end is None:
        return None
    return {"from": int(start or end), "to": int(end or start)}


def _availability_ranges(payload: dict[str, Any]) -> list[dict[str, str]]:
    ranges: list[dict[str, str]] = []
    for item in payload.get("bookableItems", []):
        for season in item.get("seasons", []):
            start = str(season.get("startDate") or "")
            end = str(season.get("endDate") or "")
            if start or end:
                ranges.append({"from": start, "to": end})
    return ranges


class ViatorProvider:
    name = "viator"

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        localized: bool = False,
    ) -> dict[str, Any]:
        headers = {
            "exp-api-key": self._api_key,
            "Accept": "application/json;version=2.0",
        }
        if localized:
            headers["Accept-Language"] = "en-US"
        try:
            response = http_client.request(
                method,
                f"{self._base_url}/{path.lstrip('/')}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ViatorError(f"Viator returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ViatorError(f"Viator request failed: {type(exc).__name__}") from exc

    def search_activities(self, query: ActivitySearchQuery) -> list[ActivityOffer]:
        filtering: dict[str, Any] = {"includeAutomaticTranslations": True}
        if query.start_date and query.end_date:
            filtering["dateRange"] = {"from": query.start_date, "to": query.end_date}
        payload = self._request(
            "POST",
            "search/freetext",
            payload={
                "searchTerm": query.destination,
                "productFiltering": filtering,
                "productSorting": {"sort": "TRAVELER_RATING", "order": "DESCENDING"},
                "searchTypes": [
                    {
                        "searchType": "PRODUCTS",
                        "pagination": {"start": 1, "count": query.max_results},
                    }
                ],
                "currency": query.currency,
            },
            localized=True,
        )
        products = payload.get("products", {})
        if isinstance(products, dict):
            products = products.get("results", [])
        if not isinstance(products, list):
            products = []

        quoted_at = datetime.now(UTC)
        offers: list[ActivityOffer] = []
        for product in products[: query.max_results]:
            product_code = str(product.get("productCode") or "")
            pricing = product.get("pricing") or {}
            summary = pricing.get("summary") or {}
            amount = _number(summary.get("fromPrice"))
            if not product_code or amount is None:
                continue
            schedule = self._request("GET", f"availability/schedules/{product_code}")
            ranges = _availability_ranges(schedule)
            reviews = product.get("reviews") or {}
            cancellation = product.get("cancellationPolicy") or {}
            destinations = product.get("destinations") or []
            destination = next(
                (str(item.get("name")) for item in destinations if item.get("name")),
                query.destination,
            )
            offers.append(
                ActivityOffer(
                    provider=self.name,
                    provider_ref={"product_code": product_code},
                    title=str(product.get("title") or product_code),
                    destination=destination,
                    from_price=Money(
                        amount=amount,
                        currency=str(pricing.get("currency") or query.currency),
                    ),
                    available=bool(ranges),
                    availability_ranges=ranges,
                    duration_minutes=_duration(product),
                    rating=_number(reviews.get("combinedAverageRating")),
                    review_count=reviews.get("totalReviews"),
                    cancellation_summary=cancellation.get("description")
                    or cancellation.get("type"),
                    confirmation_type=product.get("confirmationType"),
                    provider_url=product.get("productUrl"),
                    quoted_at=quoted_at,
                    status=QuoteStatus.LIVE if ranges else QuoteStatus.UNAVAILABLE,
                )
            )
        return offers
