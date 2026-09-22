"""Dated LiteAPI access evidence for one exact trip context.

Run: python scripts/liteapi_access_probe.py --city Goa --checkin 2026-12-01 \
        --checkout 2026-12-03 --origin DEL --destination GOI --departure-date 2026-12-01

What this records is technical access: whether the configured account and base URL
answer for hotel search and for flight search, with what shape of evidence. Hotel
access and flight production entitlement are separate facts, so they are reported
separately and one never stands in for the other.

What it does not record is vendor permission, commercial terms or live-quote
quality. A sandbox base URL that answers is a sandbox that answers. Denials are
printed as denials; nothing here retries around one or substitutes another source.

Nothing is cached, saved to a trip or written back to a provider. Print the
markdown block with --markdown and paste it under the verification boundary in
docs/research/provider-api-access.md, or write it with --out.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tripplanner.config import get_settings
from tripplanner.providers.models import FlightSearchQuery, HotelSearchQuery
from tripplanner.providers.registry import get_flight_provider, get_hotel_provider


@dataclass
class Probe:
    capability: str
    query: dict[str, Any]
    outcome: str = "not_run"
    detail: str = ""
    offers: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)


def _offer_evidence(offers: list[Any]) -> dict[str, Any]:
    """Summarize what the offers prove, without copying opaque provider handles."""
    if not offers:
        return {}
    currencies = sorted({offer.total.currency for offer in offers if offer.total})
    return {
        "currencies": currencies,
        "mandatory_costs_complete": sum(
            1 for offer in offers if offer.total and offer.total.mandatory_costs_complete
        ),
        "all_in": sum(1 for offer in offers if offer.total and offer.total.all_in),
        "carries_expiry": sum(1 for offer in offers if getattr(offer, "expires_at", None)),
        # A returned link is the only thing that can support a product-page or
        # exact-offer handoff. None means every row stays copy-the-details.
        "carries_url": sum(
            1
            for offer in offers
            if getattr(offer, "provider_url", None) or getattr(offer, "booking_url", None)
        ),
        "statuses": sorted({str(offer.status) for offer in offers}),
    }


def _run(probe: Probe, call) -> Probe:
    try:
        offers = call()
    except Exception as exc:  # noqa: BLE001 - the failure class is the evidence
        probe.outcome = "denied_or_failed"
        probe.detail = f"{type(exc).__name__}: {exc}"[:400]
        return probe
    probe.offers = len(offers)
    probe.outcome = "answered_with_offers" if offers else "answered_empty"
    probe.evidence = _offer_evidence(offers)
    return probe


def probe_hotels(args: argparse.Namespace) -> Probe:
    query = HotelSearchQuery(
        destination=args.city,
        checkin=args.checkin,
        checkout=args.checkout,
        adults_per_room=args.adults,
        rooms=args.rooms,
        children_ages=args.children_ages,
        currency=args.currency,
        guest_nationality=args.nationality,
        max_results=args.max_results,
    )
    probe = Probe("hotel_search", query.model_dump())
    provider = get_hotel_provider()
    if provider is None:
        probe.outcome = "not_configured"
        probe.detail = "No hotel provider is selected or enabled for this profile."
        return probe
    return _run(probe, lambda: provider.search_hotels(query))


def probe_flights(args: argparse.Namespace) -> Probe:
    query = FlightSearchQuery(
        origin=args.origin,
        destination=args.destination,
        departure_date=args.departure_date,
        return_date=args.return_date,
        adults=args.adults,
        cabin_class=args.cabin,
        currency=args.currency,
        max_results=args.max_results,
    )
    probe = Probe("flight_search", query.model_dump())
    provider = get_flight_provider()
    if provider is None:
        probe.outcome = "not_configured"
        probe.detail = "No flight provider is selected or enabled for this profile."
        return probe
    return _run(probe, lambda: provider.search_flights(query))


def markdown(probes: list[Probe], base_url: str, checked_at: str) -> str:
    lines = [
        f"#### LiteAPI access probe — {checked_at}",
        "",
        f"Base URL: `{base_url}`. Technical access only: this is not vendor permission,",
        "commercial approval or evidence of live-quote quality. Hotel access and flight",
        "production entitlement are separate; each row stands on its own.",
        "",
        "| Capability | Outcome | Offers | Evidence | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for probe in probes:
        evidence = (
            ", ".join(f"{key}: {value}" for key, value in probe.evidence.items())
            if probe.evidence
            else "none returned"
        )
        lines.append(
            f"| {probe.capability} | {probe.outcome} | {probe.offers} | {evidence} "
            f"| {probe.detail or '—'} |"
        )
    lines += [
        "",
        "Queries probed: "
        + "; ".join(f"{probe.capability}: {json.dumps(probe.query)}" for probe in probes),
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", choices=("hotels", "flights", "both"), default="both")
    parser.add_argument("--city", default="Goa", help="Hotel search destination")
    parser.add_argument("--checkin", default="")
    parser.add_argument("--checkout", default="")
    parser.add_argument("--origin", default="DEL")
    parser.add_argument("--destination", default="GOI")
    parser.add_argument("--departure-date", default="")
    parser.add_argument("--return-date", default="")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--rooms", type=int, default=1)
    parser.add_argument("--children-ages", type=int, nargs="*", default=[])
    parser.add_argument("--nationality", default="IN")
    parser.add_argument("--currency", default="INR")
    parser.add_argument("--cabin", default="ECONOMY")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--markdown", action="store_true", help="Print the pasteable block")
    parser.add_argument("--out", default="", help="Write the markdown block to this file")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.liteapi_api_key:
        print(
            "LITEAPI_API_KEY is not set in this environment. This probe records real account\n"
            "access, so it stops here rather than reporting a result it cannot stand behind."
        )
        return 2
    if args.capability in ("hotels", "both") and not (args.checkin and args.checkout):
        parser.error("--checkin and --checkout are required for a hotel probe")
    if args.capability in ("flights", "both") and not args.departure_date:
        parser.error("--departure-date is required for a flight probe")

    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    probes: list[Probe] = []
    if args.capability in ("hotels", "both"):
        probes.append(probe_hotels(args))
    if args.capability in ("flights", "both"):
        probes.append(probe_flights(args))

    for probe in probes:
        print(f"\n=== {probe.capability} ===")
        print(f"  outcome : {probe.outcome}")
        print(f"  offers  : {probe.offers}")
        if probe.evidence:
            print(f"  evidence: {json.dumps(probe.evidence)}")
        if probe.detail:
            print(f"  detail  : {probe.detail}")

    block = markdown(probes, settings.liteapi_base_url, checked_at)
    if args.markdown:
        print("\n" + block)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(block + "\n")
        print(f"\nWrote {args.out}. Paste it under the verification boundary in the research doc.")
    # A probe that reached the provider has done its job even when the answer is
    # a denial: the denial is the evidence. Only a missing provider is a setup error.
    return 1 if any(probe.outcome == "not_configured" for probe in probes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
