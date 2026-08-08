"""Capture one real planning run so the public entry can replay it.

The public entry must not start an agent for every stranger who loads the page:
that would cost money, hit rate limits, and risk failing in front of someone who
has not yet decided to trust the product. So it replays a run instead. This
script is what makes that run real. It drives the same graph, the same tools and
the same receipt projection the live product uses, then writes what actually
happened. Nothing here invents a number, a source or a sentence.

Server-free by design: it talks to the graph in-process, so it never touches the
local stack.

    python scripts/capture_public_run.py --out captured-run.json \\
        --prompt "Plan 5 days in Lisbon and Porto for 2 travellers in October"
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from tripplanner import storage_cosmos
from tripplanner.decisions.apply import apply_override
from tripplanner.decisions.provenance import build_provenance
from tripplanner.decisions.receipts import ReceiptLog
from tripplanner.graph import app_graph
from tripplanner.tools import trip_planner
from tripplanner.user_context import set_user_id
from tripplanner.web import share, trip_view

_RECURSION_LIMIT = 60


def _clock(started: float) -> str:
    seconds = max(int(time.monotonic() - started), 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


async def _run_turn(
    history: list[Any], message: str, started: float, receipts: list[dict[str, Any]]
) -> str:
    """Stream one turn, collecting receipts exactly as the API would."""
    history.append(HumanMessage(content=message))
    log = ReceiptLog()
    reply: list[str] = []
    async for event in app_graph.astream_events(
        {"messages": history, "current_agent": "", "proposal_only": False},
        config={"recursion_limit": _RECURSION_LIMIT},
        version="v2",
    ):
        kind = event.get("event")
        data = event.get("data", {}) or {}
        if kind == "on_chat_model_stream":
            chunk = data.get("chunk")
            text = getattr(chunk, "content", "") if chunk is not None else ""
            if text:
                reply.append(text)
                print(text, end="", flush=True)
        elif kind == "on_tool_end":
            output = data.get("output")
            text = output if isinstance(output, str) else getattr(output, "content", "")
            receipt = log.add(event.get("name", ""), text)
            if receipt is None:
                continue
            row = {"seq": len(receipts) + 1, "at": _clock(started), **receipt.as_dict()}
            receipts.append(row)
            print(f"\n  [{row['at']}] {row['text']}", flush=True)
    answer = "".join(reply)
    history.append(AIMessage(content=answer))
    return answer


def _schedule(itinerary: dict[str, Any]) -> dict[tuple[int, str], str]:
    return {
        (day.get("day", 0), str(stop.get("name", ""))): str(stop.get("time", ""))
        for day in itinerary.get("days", [])
        for stop in day.get("stops", [])
    }


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What actually moved in the plan, read off the two itineraries.

    The page shows a traveller what overruling would cost them, so the list has
    to come from the re-settled plan rather than from a description of it.
    """
    old, new = _schedule(before), _schedule(after)
    lines: list[str] = []
    for key, time_of_day in old.items():
        day, name = key
        if key not in new:
            lines.append(f"Day {day}: {name} drops out")
        elif new[key] != time_of_day:
            lines.append(f"Day {day}: {name} moves {time_of_day} → {new[key]}")
    for key in new:
        if key not in old:
            lines.append(f"Day {key[0]}: {key[1]} added at {new[key]}")
    return lines


def _overrules(plan: dict[str, Any], itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    """Overrule every comparison once, on a copy, and keep what really happened."""
    captured: list[dict[str, Any]] = []
    for decision in plan.get("decisions") or []:
        chosen = str(decision.get("chosen_option_id") or "")
        for option in decision.get("options") or []:
            option_id = str(option.get("id") or "")
            if not option_id or option_id == chosen:
                continue
            draft = copy.deepcopy(plan)
            result = apply_override(draft, str(decision.get("id") or ""), option_id)
            if not result.ok:
                continue
            captured.append(
                {
                    "decision_id": result.decision_id,
                    "option_id": option_id,
                    "label": option.get("label", ""),
                    "message": result.message,
                    "total_cost": result.total_cost,
                    "delta": result.delta,
                    "currency": result.currency,
                    "warnings": result.warnings,
                    "changes": _changes(itinerary, trip_view.build_itinerary(draft)),
                }
            )
    return captured


def _capture(prompts: list[str], previous: dict[str, Any] | None) -> dict[str, Any]:
    started = time.monotonic()
    receipts: list[dict[str, Any]] = []
    history: list[Any] = []
    if previous is None:
        replies = [
            asyncio.run(_run_turn(history, prompt, started, receipts)) for prompt in prompts
        ]
    else:
        # Re-projecting an earlier run: the trip is already on disk, and asking
        # the agent again would produce a different trip, not a better capture.
        prompts = previous.get("prompts") or prompts
        replies = previous.get("replies") or []
        receipts = previous.get("receipts") or []

    plan = trip_planner.load_active_trip_dict()
    if not plan:
        raise SystemExit("The run finished without saving a trip. Nothing to capture.")

    view = trip_view.build_view(plan, None)
    itinerary = trip_view.build_itinerary(plan)
    return {
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "prompts": prompts,
        "replies": replies,
        "trip": {
            "id": plan.get("trip_id", ""),
            "destination": plan.get("destination", ""),
            "departure_date": plan.get("departure_date", ""),
            "return_date": plan.get("return_date", ""),
            "travellers": plan.get("travelers") or plan.get("travellers"),
            "total_cost": plan.get("total_cost"),
            "currency": itinerary.get("currency", ""),
        },
        "overview": view.get("overview", {}),
        "receipts": receipts,
        "days": itinerary.get("days", []),
        "stats": itinerary.get("stats", {}),
        # Sanitised the same way a shared trip is, because this is published too.
        "decisions": share.sanitize_decisions(plan.get("decisions")),
        "overrules": _overrules(plan, itinerary),
        "provenance": build_provenance(plan),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        help="A turn to send. Repeat to capture a multi-turn run.",
    )
    parser.add_argument("--out", required=True, help="Where to write the captured run.")
    parser.add_argument(
        "--reproject",
        action="store_true",
        help="Skip the agent and re-derive the file from the trip already captured.",
    )
    parser.add_argument(
        "--user",
        default="capture",
        help="Trip owner for the run. Keep it off a real account.",
    )
    parser.add_argument(
        "--store",
        choices=("local", "configured"),
        default="local",
        help="Where the captured trip is written. Local by default: a capture is"
        " throwaway data and has no business in a real database.",
    )
    args = parser.parse_args(argv)

    if args.store == "local":
        storage_cosmos.is_enabled = lambda: False  # type: ignore[assignment]
    set_user_id(args.user)

    out = Path(args.out)
    previous = None
    if args.reproject:
        previous = json.loads(out.read_text(encoding="utf-8"))
    elif not args.prompt:
        parser.error("give at least one --prompt, or --reproject an earlier capture")
    captured = _capture(args.prompt, previous)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n\nCaptured {len(captured['receipts'])} receipts, "
        f"{len(captured['days'])} days, {len(captured['decisions'])} decisions → {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
