"""Execute offline evaluators once per versioned input and retain finding history."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tripplanner.evals import suite
from tripplanner.evals.contracts import CorpusRecord
from tripplanner.evals.findings import Finding
from tripplanner.harness.lifecycle import fixed_findings
from tripplanner.harness.results import (
    SCHEMA_VERSION,
    ResultStore,
    atomic_json,
    fingerprint,
    implementation_fingerprint,
)


def code_identity(repo_root: Path) -> tuple[str, bool]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def run(
    records: list[CorpusRecord],
    root: Path,
    repo_root: Path,
    ratings: dict[str, Any],
    evaluators: tuple[str, ...],
    *,
    force: bool = False,
    configuration: dict[str, Any] | None = None,
) -> tuple[list[Finding], dict[str, Any], set[str]]:
    if not evaluators or any(name not in suite.EVALUATORS for name in evaluators):
        raise ValueError("Select at least one known evaluator")
    version = implementation_fingerprint()
    commit, dirty = code_identity(repo_root)
    store = ResultStore(root)
    fixed = fixed_findings(root)
    summary: dict[str, Any] = {
        "implementation": version,
        "evaluators": list(evaluators),
        "executed": 0,
        "reused": 0,
        "errors": 0,
        "insufficient_evidence": 0,
        "results": [],
        "occurrences": [],
        "fixed": fixed,
    }
    findings: list[Finding] = []
    actionable: set[str] = set()
    for record in records:
        store.snapshot("artifacts", {"case_id": record.case_identity, **record.evaluation_input()})
        evidence_id = store.snapshot("evidence", record.places)
        for evaluator in evaluators:
            inputs = {"artifact": record.artifact_id, "input": record.evaluation_input()}
            if evaluator == "human":
                inputs["rating"] = suite.rating_for(record, ratings)
            else:
                inputs["places"] = record.places
            input_id = store.snapshot("inputs", inputs)
            key = fingerprint(
                {
                    "input": inputs,
                    "evaluator": evaluator,
                    "implementation": version,
                    "configuration": (configuration or {}).get(evaluator, {}),
                }
            )
            body = None if force else store.cached(key)
            reused = body is not None
            if body is None:
                try:
                    status, found, reason = suite.evaluate(evaluator, record, ratings)
                except Exception as error:
                    status, found, reason = "error", [], f"{type(error).__name__}: {error}"
                body = {
                    "version": SCHEMA_VERSION,
                    "id": fingerprint([key, uuid4().hex]),
                    "cache_key": key,
                    "case_id": record.case_identity,
                    "artifact_id": record.artifact_id,
                    "evaluator": evaluator,
                    "evidence_id": evidence_id,
                    "input_id": input_id,
                    "implementation": version,
                    "status": status,
                    "reason": reason,
                    "configuration": fingerprint((configuration or {}).get(evaluator, {})),
                    "code_commit": commit,
                    "code_dirty": dirty,
                    "generation": record.generation,
                    "evaluated_at": datetime.now(UTC).isoformat(),
                    "findings": [
                        {
                            k: v
                            for k, v in asdict(item).items()
                            if k not in {"record_id", "provenance"}
                        }
                        for item in found
                    ],
                }
                store.remember(body)
            summary["reused" if reused else "executed"] += 1
            summary["errors"] += body["status"] == "error"
            summary["insufficient_evidence"] += body["status"] == "insufficient_evidence"
            summary["results"].append({**body, "record_id": record.id, "reused": reused})
            for item in body["findings"]:
                finding = Finding(**item, record_id=record.id, provenance=record.provenance)
                findings.append(finding)
                fixes = fixed.get(finding.key, [])
                occurrence_key = fingerprint(
                    [
                        record.artifact_id,
                        finding.key,
                        sorted(fix["after"] for fix in fixes),
                    ]
                )
                seen = root / "observations" / f"{occurrence_key}.json"
                try:
                    observation = json.loads(seen.read_text(encoding="utf-8"))
                    known = bool(store.read(observation["result_id"]))
                except (OSError, ValueError, KeyError, TypeError):
                    known = False
                status = "known" if known else "new"
                if fixes:
                    historical = any(
                        fix["before_artifact"] == record.artifact_id
                        and fix["before_artifact"] != fix["after_artifact"]
                        for fix in fixes
                    )
                    status = "historical" if historical else ("known" if known else "recurring")
                if status in {"new", "recurring"}:
                    actionable.add(finding.key)
                summary["occurrences"].append(
                    {
                        "key": finding.key,
                        "artifact_id": record.artifact_id,
                        "result_id": body["id"],
                        "status": status,
                    }
                )
                if not known:
                    atomic_json(seen, {"artifact_id": record.artifact_id, "result_id": body["id"]})
    return findings, summary, actionable
