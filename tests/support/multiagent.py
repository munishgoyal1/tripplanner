"""Shared module loading and factories for multiagent coordinator tests."""

from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[2]
DEV = ROOT / "scripts" / "dev"


def _load_module(name: str, path: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve annotations through sys.modules, so register first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(DEV))
core = _load_module("multiagent_core", DEV / "multiagent_core.py")
runtime = _load_module("multiagent", DEV / "multiagent.py")


def issue(number: int, *labels: str, body: str = "", title: str = "t") -> object:
    return core.Issue(number=number, title=title, body=body, labels=tuple(labels))


def assignment(issue_number: int, session_id: str) -> object:
    return core.Assignment(
        issue=issue_number,
        attempt=1,
        slot="slot-1",
        branch="multiagent/slot-1",
        base_sha="a" * 40,
        session_id=session_id,
        pid=0,
        state="landed",
    )


def integrated(issue_number: int, *, minutes_ago: int = 0) -> object:
    finished = core.utcnow() - timedelta(minutes=minutes_ago)
    return core.Assignment(
        issue=issue_number,
        state="integrated",
        finished=core.format_time(finished),
    )
