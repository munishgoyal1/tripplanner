"""What the corpus is allowed to cost, remembered between runs.

Generating trips is the only part of this harness that spends money, so the
ledger is deliberately dull: it records what was spent, refuses to start a run
that would breach the cumulative cap, and clamps a run to whatever headroom is
left. A build that finds the corpus already big enough spends nothing at all --
the owner asked for a durable corpus, not a recurring bill.

Amounts are held in INR because that is the currency the cap was set in. Model
usage and known provider catalog estimates are held in USD, so every run records
the rate it converted at and stays auditable if the rate moves.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_VERSION = 1
DEFAULT_RUN_BUDGET_INR = 1000.0
CUMULATIVE_CAP_INR = 15000.0
#: Only an assumption, so each run stores the rate it actually used.
DEFAULT_USD_INR = 88.0


class BudgetExhaustedError(RuntimeError):
    """The cumulative cap leaves nothing to spend."""


@dataclass(frozen=True)
class Authorization:
    budget_inr: float
    spent_inr: float
    cap_inr: float
    usd_inr: float

    @property
    def remaining_inr(self) -> float:
        return max(0.0, self.cap_inr - self.spent_inr)

    @property
    def budget_usd(self) -> float:
        return self.budget_inr / self.usd_inr


def usd_inr() -> float:
    try:
        rate = float(os.getenv("CORPUS_USD_INR", DEFAULT_USD_INR))
    except (TypeError, ValueError):
        return DEFAULT_USD_INR
    return rate if rate > 0 else DEFAULT_USD_INR


def ledger_path(corpus_root: Path) -> Path:
    return corpus_root / "spend-ledger.json"


def load(corpus_root: Path) -> dict[str, Any]:
    path = ledger_path(corpus_root)
    if not path.exists():
        return {"version": LEDGER_VERSION, "cap_inr": CUMULATIVE_CAP_INR, "runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # An unreadable ledger must never read as "nothing spent yet".
        raise BudgetExhaustedError(f"cannot read the spend ledger at {path}") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise BudgetExhaustedError(f"the spend ledger at {path} is not a ledger")
    payload.setdefault("cap_inr", CUMULATIVE_CAP_INR)
    return payload


def spent_inr(corpus_root: Path) -> float:
    return round(
        sum(float(run.get("spent_inr") or 0.0) for run in load(corpus_root)["runs"]), 2
    )


def authorize(corpus_root: Path, requested_inr: float | None = None) -> Authorization:
    """How much this run may spend, or refuse it outright."""
    ledger = load(corpus_root)
    cap = float(ledger.get("cap_inr") or CUMULATIVE_CAP_INR)
    already = spent_inr(corpus_root)
    remaining = max(0.0, cap - already)
    if remaining <= 0:
        raise BudgetExhaustedError(
            f"the corpus has already cost INR {already:.0f} of its INR {cap:.0f} cap"
        )
    wanted = DEFAULT_RUN_BUDGET_INR if requested_inr is None else float(requested_inr)
    if wanted <= 0:
        raise BudgetExhaustedError("a run budget must be greater than zero")
    return Authorization(
        budget_inr=min(wanted, remaining), spent_inr=already, cap_inr=cap, usd_inr=usd_inr()
    )


def record(
    corpus_root: Path,
    *,
    spent_inr_amount: float,
    model_spent_inr: float | None = None,
    google_spent_inr: float | None = None,
    trips: int,
    model: str,
    stopped_because: str,
    usd_inr_rate: float | None = None,
) -> dict[str, Any]:
    """Append one run to the ledger and return it."""
    ledger = load(corpus_root)
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "trips": int(trips),
        "spent_inr": round(float(spent_inr_amount), 2),
        "model_spent_inr": round(float(model_spent_inr), 2)
        if model_spent_inr is not None
        else None,
        "google_spent_inr": round(float(google_spent_inr), 2)
        if google_spent_inr is not None
        else None,
        "usd_inr": usd_inr_rate or usd_inr(),
        "stopped_because": stopped_because,
    }
    ledger["runs"].append(entry)
    ledger["version"] = LEDGER_VERSION
    path = ledger_path(corpus_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return entry
