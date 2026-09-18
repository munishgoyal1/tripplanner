"""Explicit artifact selection and evidence-backed finding lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tripplanner.evals.contracts import REVISION_COHORT, CorpusRecord
from tripplanner.harness.results import ResultStore, atomic_json, fingerprint

STATES = ("active", "historical", "superseded", "regression")
SELECTIONS = ("active", "historical", "regression", "all")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "artifacts": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported evaluation lifecycle manifest")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Lifecycle artifacts must be an object")
    for key, item in artifacts.items():
        if not isinstance(item, dict) or item.get("state") not in STATES:
            raise ValueError(f"Invalid lifecycle state for {key}")
    return payload


def set_state(path: Path, artifact: str, state: str, reason: str, successor: str = "") -> None:
    if len(artifact) != 64 or any(char not in "0123456789abcdef" for char in artifact):
        raise ValueError("Artifact must be a SHA-256 identity from an audit report")
    if state not in STATES or not reason.strip():
        raise ValueError("A valid lifecycle state and a reason are required")
    if state == "superseded" and (
        len(successor) != 64
        or successor == artifact
        or any(char not in "0123456789abcdef" for char in successor)
    ):
        raise ValueError("A different successor artifact is required for superseded state")
    payload = load_manifest(path)
    payload["artifacts"][artifact] = {"state": state, "reason": reason, "superseded_by": successor}
    atomic_json(path, payload)


def state_for(record: CorpusRecord, manifest: dict[str, Any]) -> str:
    explicit = manifest.get("artifacts", {}).get(record.artifact_id, {})
    return explicit.get("state") or (
        "historical" if REVISION_COHORT in record.cohorts else "active"
    )


def select(
    records: list[CorpusRecord],
    manifest: dict[str, Any],
    mode: str,
) -> tuple[list[CorpusRecord], list[dict[str, str]]]:
    if mode not in SELECTIONS:
        raise ValueError(f"Unknown selection {mode}")
    selected, excluded = [], []
    for record in records:
        state = state_for(record, manifest)
        matches = mode == "all" or state == mode or (mode == "historical" and state == "superseded")
        if matches:
            selected.append(record)
        else:
            excluded.append(
                {"record_id": record.id, "artifact_id": record.artifact_id, "state": state}
            )
    return selected, excluded


def verify_fix(
    root: Path,
    finding_key: str,
    before_id: str,
    after_id: str,
    kind: str,
    fix_commit: str,
    issue: str = "",
) -> dict[str, Any]:
    store = ResultStore(root)
    before, after = store.read(before_id), store.read(after_id)
    if not before or not after or before_id == after_id:
        raise ValueError("Distinct valid failed and passing result receipts are required")
    if before["evaluator"] == "itinerary_judge" or after["evaluator"] == "itinerary_judge":
        raise ValueError("Advisory model judgments cannot verify a preventive fix")
    keys = {f"{item['rule']}|{item['symptom']}" for item in before["findings"]}
    if finding_key not in keys or after["status"] != "pass":
        raise ValueError(
            "Before must contain the finding and after must be fully evaluated and pass"
        )
    if before["case_id"] != after["case_id"] or before["evaluator"] != after["evaluator"]:
        raise ValueError("Verification requires the same case and evaluator")
    if before.get("configuration") != after.get("configuration"):
        raise ValueError("Evaluator configuration must stay fixed during verification")
    if not fix_commit or after.get("code_commit") != fix_commit or after.get("code_dirty"):
        raise ValueError("Passing receipt must come from the clean declared fix commit")
    same_artifact = before["artifact_id"] == after["artifact_id"]
    if kind == "replay":
        if before["input_id"] != after["input_id"]:
            raise ValueError("Replay requires unchanged evidence and ratings")
        if not same_artifact or before["implementation"] == after["implementation"]:
            raise ValueError(
                "Replay requires the same artifact and changed evaluator implementation"
            )
    elif kind == "regenerated":
        if same_artifact or after.get("generation", {}).get("generated_by_commit") != fix_commit:
            raise ValueError(
                "Regeneration requires a new artifact produced by the declared fix commit"
            )
    else:
        raise ValueError("Verification kind must be replay or regenerated")
    receipt = {
        "finding_key": finding_key,
        "before": before_id,
        "after": after_id,
        "case_id": after["case_id"],
        "before_artifact": before["artifact_id"],
        "after_artifact": after["artifact_id"],
        "kind": kind,
        "fix_commit": fix_commit,
        "issue": issue,
    }
    atomic_json(root / "fixes" / f"{fingerprint(receipt)}.json", receipt)
    return receipt


def fixed_findings(root: Path) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / "fixes").glob("*.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or path.stem != fingerprint(receipt):
            raise ValueError(f"Invalid fix receipt {path.name}")
        store = ResultStore(root)
        if not store.read(receipt["before"]) or not store.read(receipt["after"]):
            raise ValueError(f"Missing or invalid verification evidence for {path.name}")
        found.setdefault(receipt["finding_key"], []).append(receipt)
    return found
