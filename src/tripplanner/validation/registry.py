"""Every rule the harness can report, in one place and in the owner's words.

Rules were scattered across the guard, the completion gate, the render checks
and the metamorphic relations, so adding one meant knowing four conventions and
reading no single list. Collecting them costs nothing and makes the next rule
cheap: a sentence, a severity, and an evaluator.

The registry is assembled from the modules that own the rules rather than
retyped here, so it cannot drift from what actually runs.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Blocks a turn from reporting the trip as planned.
GATE = "gate"
#: Told to the agent, and to us, but stops nothing.
REPORT = "report"
#: Counted while it earns its place. New rules start here.
OBSERVE = "observe"

GAP_RULE = "gap"


@dataclass(frozen=True)
class Rule:
    code: str
    title: str
    statement: str
    severity: str
    evaluated_in: str
    requires_places: bool = False


def _gate_codes() -> frozenset[str]:
    from tripplanner.tools.trip_validation import _COHERENCE_CODES

    return frozenset(_COHERENCE_CODES)


def registry() -> tuple[Rule, ...]:
    """The full rule set, ordered as a person would read it."""
    from tripplanner.tools.trip_guard import INVARIANTS
    from tripplanner.validation.mutations import METAMORPHIC_RULES
    from tripplanner.validation.render import RENDER_RULES

    gates = _gate_codes()
    place_rules = frozenset({"I3", "I4", "I9", "I11"})
    rules: list[Rule] = [
        Rule(
            code=code,
            title=title,
            statement=statement,
            severity=GATE if code in gates else REPORT,
            evaluated_in="tripplanner.tools.trip_guard",
            requires_places=code in place_rules,
        )
        for code, title, statement in INVARIANTS
    ]
    rules.append(
        Rule(
            code=GAP_RULE,
            title="Completion gap",
            statement="A trip presented as planned must not still be missing its parts.",
            severity=GATE,
            evaluated_in="tripplanner.tools.trip_validation",
        )
    )
    rules.extend(
        Rule(
            code=code,
            title="Render",
            statement=statement,
            severity=REPORT,
            evaluated_in="tripplanner.validation.render",
            requires_places=True,
        )
        for code, statement in RENDER_RULES
    )
    rules.extend(
        Rule(
            code=code,
            title="Metamorphic",
            statement=statement,
            severity=REPORT,
            evaluated_in="tripplanner.validation.mutations",
        )
        for code, statement in METAMORPHIC_RULES
    )
    return tuple(rules)


def codes() -> frozenset[str]:
    return frozenset(rule.code for rule in registry())


def rule_for(code: str) -> Rule | None:
    return next((rule for rule in registry() if rule.code == code), None)
