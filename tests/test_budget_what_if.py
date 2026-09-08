from datetime import UTC, datetime, timedelta

from tripplanner.decisions.budget_what_if import build_budget_what_if
from tripplanner.decisions.models import (
    Decision,
    DecisionKind,
    DecisionScope,
    FareBasis,
    FlightFacts,
    Option,
    Price,
    Rule,
    TransportMode,
)
from tripplanner.decisions.store import upsert_decision


def option(option_id: str, label: str, amount: float, stops: int) -> Option:
    return Option(
        id=option_id,
        mode=TransportMode.FLIGHT,
        label=label,
        price=Price(amount=amount, currency="USD", basis=FareBasis.PER_PARTY),
        rejected_because="One connection instead of a direct flight" if stops else None,
        flight=FlightFacts(origin="DEL", destination="LHR", stops=stops),
    )


def plan_with_flight_decision() -> dict:
    now = datetime.now(UTC)
    plan = {
        "currency": "USD",
        "selected_flights": [
            {
                "airline": "Air India",
                "price": 900,
                "currency": "USD",
                "source": {"provider": "duffel"},
                "price_composition": {"mandatory_costs_complete": True},
            }
        ],
        "price_checks": [
            {
                "kind": "flights",
                "provider": "duffel",
                "checked_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
            }
        ],
    }
    upsert_decision(
        plan,
        Decision(
            id="dec_flight_del_lhr",
            kind=DecisionKind.FLIGHT,
            created_at=now,
            scope=DecisionScope(from_place="DEL", to_place="LHR"),
            subject="Flight from Delhi to London",
            rule=Rule(code="flight_stops_then_total", text="Fewest stops first."),
            chosen_option_id="direct",
            options=[
                option("direct", "Air India", 900, 0),
                option("connecting", "Emirates", 650, 1),
                option("dearer", "British Airways", 1100, 0),
            ],
        ),
    )
    return plan


def test_on_demand_what_if_returns_only_cheaper_exact_alternatives() -> None:
    result = build_budget_what_if(plan_with_flight_decision())

    assert result["generated_on_demand"] is True
    assert result["estimated"] is False
    assert result["evidence_coverage_pct"] == 100
    assert result["proposals"] == [
        {
            "id": "what_if:dec_flight_del_lhr:connecting",
            "decision_id": "dec_flight_del_lhr",
            "option_id": "connecting",
            "kind": "flight",
            "subject": "Flight from Delhi to London",
            "label": "Emirates",
            "savings": 250,
            "currency": "USD",
            "tradeoff": "One connection instead of a direct flight",
            "personalized": False,
        }
    ]


def test_incomplete_evidence_labels_the_what_if_as_estimated() -> None:
    plan = plan_with_flight_decision()
    plan["selected_hotels"] = [{"name": "Unknown stay"}]

    result = build_budget_what_if(plan)

    assert result["estimated"] is True
    assert result["evidence_coverage_pct"] == 50
    assert "worth it" not in str(result).lower()
