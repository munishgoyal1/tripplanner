"""Budgeted whole-itinerary judging; separate from the offline audit runner."""

from __future__ import annotations

import json
import math
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import uuid4

from tripplanner.cost_model import inr_per_usd, usd_to_inr
from tripplanner.evals import judge
from tripplanner.evals.contracts import CorpusRecord
from tripplanner.harness import judge_transport
from tripplanner.harness.judge_transport import JudgeProfile
from tripplanner.harness.results import SCHEMA_VERSION, ResultStore, atomic_json, fingerprint


@contextmanager
def exclusive(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "judge.lock"
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError(
            "Judge state is locked; verify no run is active before removing judge.lock"
        ) from error
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def cost_inr(profile: JudgeProfile, input_tokens: int, output_tokens: int) -> float:
    cost_usd = (
        input_tokens * profile.input_usd_per_million
        + output_tokens * profile.output_usd_per_million
    ) / 1_000_000
    return math.ceil(usd_to_inr(cost_usd) * 100_000_000) / 100_000_000


def load_ledger(path: Path, cap_inr: float) -> dict:
    if not path.exists():
        return {"version": 1, "cap_inr": cap_inr, "calls": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("calls"), list)
    ):
        raise ValueError("Invalid judge spend ledger")
    if any(not isinstance(item, dict) for item in data["calls"]):
        raise ValueError("Invalid judge spend entries")
    amounts = [data.get("cap_inr"), *(item.get("charged_inr") for item in data["calls"])]
    if any(type(x) not in {int, float} or not math.isfinite(x) or x < 0 for x in amounts):
        raise ValueError("Invalid judge ledger amounts")
    data["cap_inr"] = min(data["cap_inr"], cap_inr)
    return data


def implementation() -> str:
    paths = (Path(__file__), Path(judge.__file__), Path(judge_transport.__file__))
    return fingerprint(
        {
            "source": {path.name: path.read_text(encoding="utf-8") for path in paths},
            "packages": {name: package_version(name) for name in ("openai", "pydantic")},
            "schema": SCHEMA_VERSION,
        }
    )


def run(
    records: list[CorpusRecord],
    root: Path,
    profile: JudgeProfile,
    *,
    allow_spend: bool = False,
    budget_inr: float = 0,
    force: bool = False,
    human: dict | None = None,
) -> dict:
    if not math.isfinite(budget_inr) or budget_inr < 0 or (allow_spend and budget_inr <= 0):
        raise ValueError("Live judging requires a positive finite run budget in INR")
    human = {} if human is None else human
    judge.calibration([], human)
    identity = profile.identity()
    scoring_identity = {
        key: identity[key]
        for key in (
            "provider",
            "model",
            "model_revision",
            "max_completion_tokens",
            "api_version",
            "endpoint",
        )
        if key in identity
    }
    version = implementation()
    summary = {
        "rubric_version": judge.RUBRIC_VERSION,
        "profile": identity,
        "advisory": True,
        "executed": 0,
        "reused": 0,
        "pending": 0,
        "errors": 0,
        "charged_inr": 0.0,
        "estimated_pending_inr": 0.0,
        "results": [],
    }
    store = ResultStore(root)
    with exclusive(root):
        ledger_path = root / "judge-spend.json"
        ledger = load_ledger(ledger_path, profile.cumulative_cap_inr)
        for record in {record.artifact_id: record for record in records}.values():
            evidence = judge.evidence_for(record)
            prompt = judge.messages(evidence)
            envelope = {"messages": prompt, "schema": judge.Judgement.model_json_schema()}
            input_bytes = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
            key = fingerprint(
                {
                    "artifact": record.artifact_id,
                    "envelope": envelope,
                    "profile": scoring_identity,
                    "implementation": version,
                }
            )
            body = None if force else store.cached(key)
            if body is not None:
                try:
                    judged = judge.validate(body["judgement"], evidence)
                    body["judgement"] = judged
                except (KeyError, ValueError, TypeError):
                    body = None
            if body is not None:
                summary["reused"] += 1
                summary["results"].append({**body, "reused": True})
                continue
            row = {
                "artifact_id": record.artifact_id,
                "case_id": record.case_identity,
                "cache_key": key,
                "status": "pending",
                "reused": False,
            }
            if input_bytes > profile.max_input_bytes:
                summary["errors"] += 1
                summary["results"].append(
                    {**row, "status": "error", "reason": "Input exceeds byte limit"}
                )
                continue
            # UTF-8 byte count is a conservative token bound, plus protocol overhead.
            reserve = cost_inr(profile, input_bytes + 4096, profile.max_completion_tokens)
            spent = sum(item["charged_inr"] for item in ledger["calls"])
            if (
                not allow_spend
                or summary["charged_inr"] + reserve > budget_inr
                or spent + reserve > ledger["cap_inr"]
            ):
                summary["pending"] += 1
                summary["estimated_pending_inr"] += reserve
                summary["results"].append(
                    {
                        **row,
                        "reason": "Opt-in or budget headroom required",
                        "reservation_inr": reserve,
                    }
                )
                continue
            judge_transport.validate_credentials(profile)
            artifact_id = store.snapshot(
                "artifacts", {"case_id": record.case_identity, **record.evaluation_input()}
            )
            evidence_id = store.snapshot("evidence", evidence)
            input_id = store.snapshot("inputs", envelope)
            result_id = fingerprint([key, uuid4().hex])
            charge = {
                "result_id": result_id,
                "charged_inr": reserve,
                "reserved_inr": reserve,
                "status": "reserved",
                "fx_inr_per_usd": inr_per_usd(),
                "profile": identity,
            }
            ledger["calls"].append(charge)
            atomic_json(ledger_path, ledger)
            summary["executed"] += 1
            body = {
                **row,
                "version": SCHEMA_VERSION,
                "id": result_id,
                "evaluator": "itinerary_judge",
                "artifact_id": artifact_id,
                "evidence_id": evidence_id,
                "input_id": input_id,
                "implementation": version,
                "configuration": fingerprint(identity),
                "findings": [],
                "profile": identity,
                "rubric": judge.rubric(),
                "evaluated_at": datetime.now(UTC).isoformat(),
            }
            stage = "request"
            try:
                response = judge_transport.complete(profile, prompt)
                body["response"] = response
                stage = "usage"
                usage = response.get("usage") or {}
                counts = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
                if all(type(count) is int and count > 0 for count in counts):
                    measured = cost_inr(profile, *counts)
                    charge.update(charged_inr=measured, status="measured")
                    if measured > reserve:
                        raise ValueError(
                            "Usage exceeded the conservative reservation; halt and review rates"
                        )
                else:
                    raise ValueError("Missing usage; reservation retained")
                stage = "finish_or_refusal"
                if response.get("refusal") or response.get("finish_reason") != "stop":
                    raise ValueError("Judge refused or did not finish normally")
                stage = "assessment"
                validated = judge.validate(json.loads(response["content"]), evidence)
                body["judgement"] = {
                    key: validated[key] for key in ("rubric_version", "assessments")
                }
                body["status"] = (
                    "insufficient_evidence"
                    if validated["status"] != "complete"
                    else "fail"
                    if any(
                        item["score"] is not None and item["score"] <= 2
                        for item in validated["assessments"]
                    )
                    else "pass"
                )
                body["cost"] = dict(charge)
                store.remember(body)
                body["judgement"] = validated
            except Exception as error:
                # Provider exceptions can contain request data; persist only their class.
                body.update(status="error", reason=f"Judge {stage} failed ({type(error).__name__})")
                summary["errors"] += 1
                store.write(body)
            finally:
                atomic_json(ledger_path, ledger)
                summary["charged_inr"] += charge["charged_inr"]
            body["cost"] = dict(charge)
            summary["results"].append(body)
            if charge["charged_inr"] > reserve:
                break
        summary["cumulative_charged_inr"] = sum(item["charged_inr"] for item in ledger["calls"])
        summary["cumulative_cap_inr"] = ledger["cap_inr"]
    summary["calibration"] = judge.calibration(summary["results"], human or {})
    return summary
