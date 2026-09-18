"""Versioned local evaluator receipts; no domain scoring or network operations."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
from importlib.metadata import distributions
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1
_KEY = re.compile(r"[0-9a-f]{64}")


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def implementation_fingerprint() -> str:
    """Conservative dependency closure until narrower evaluator dependencies are proven."""
    from tripplanner.config import get_settings

    source = Path(__file__).resolve().parents[1]
    files = {
        path.relative_to(source).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source.rglob("*.py"))
    }
    packages = sorted((item.metadata.get("Name", ""), item.version) for item in distributions())
    return fingerprint(
        {
            "schema": SCHEMA_VERSION,
            "source": files,
            "packages": packages,
            "python": sys.version,
            "platform": platform.platform(),
            # Persist only the digest, never settings values or credentials.
            "settings": get_settings().model_dump(mode="json"),
        }
    )


class ResultStore:
    def __init__(self, root: Path):
        self.root = root

    def path(self, key: str) -> Path:
        if not _KEY.fullmatch(key):
            raise ValueError("Result identity must be a SHA-256 digest")
        return self.root / "results" / f"{key}.json"

    def snapshot(self, category: str, value: Any) -> str:
        key = fingerprint(value)
        path = self.root / category / f"{key}.json"
        try:
            valid = fingerprint(json.loads(path.read_text(encoding="utf-8"))) == key
        except (OSError, ValueError):
            valid = False
        if not valid:
            atomic_json(path, value)
        return key

    def read(self, key: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path(key).read_text(encoding="utf-8"))
            body = payload["result"]
            if payload["checksum"] != fingerprint(body):
                return None
            if body["id"] != key or body["version"] != SCHEMA_VERSION:
                return None
            if body["status"] not in {"pass", "fail", "insufficient_evidence"}:
                return None
            if not isinstance(body["findings"], list):
                return None
            if not all(
                isinstance(body[k], str)
                for k in (
                    "case_id",
                    "artifact_id",
                    "evaluator",
                    "implementation",
                    "cache_key",
                )
            ):
                return None
            if body["status"] == "pass" and body["findings"]:
                return None
            for category, field in (
                ("artifacts", "artifact_id"),
                ("evidence", "evidence_id"),
                ("inputs", "input_id"),
            ):
                identity = body[field]
                if not _KEY.fullmatch(identity):
                    return None
                snapshot = json.loads(
                    (self.root / category / f"{identity}.json").read_text(encoding="utf-8")
                )
                if fingerprint(snapshot) != identity:
                    return None
            for finding in body["findings"]:
                if not isinstance(finding, dict) or not all(
                    isinstance(finding.get(k), str) for k in ("rule", "symptom", "message")
                ):
                    return None
                if set(finding) != {"rule", "symptom", "message", "day"}:
                    return None
                if finding["day"] is not None and type(finding["day"]) is not int:
                    return None
            return body
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def write(self, body: dict[str, Any]) -> None:
        atomic_json(self.path(body["id"]), {"checksum": fingerprint(body), "result": body})

    def cached(self, key: str) -> dict[str, Any] | None:
        try:
            pointer = json.loads((self.root / "cache" / f"{key}.json").read_text(encoding="utf-8"))
            body = self.read(pointer["result_id"])
            return body if body and body["cache_key"] == key else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def remember(self, body: dict[str, Any]) -> None:
        self.write(body)
        if body["status"] in {"pass", "fail", "insufficient_evidence"}:
            atomic_json(
                self.root / "cache" / f"{body['cache_key']}.json", {"result_id": body["id"]}
            )
