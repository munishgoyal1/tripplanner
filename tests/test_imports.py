"""Environment smoke test.

Catches a broken/partial virtualenv (missing or corrupted dependencies)
*before* it shows up as "the backend won't start". A healthy install must be
able to import the FastAPI app and the LangGraph wiring, and the critical
third-party packages must report a real version (a `None` version means a
package with no RECORD file — i.e. a corrupted install).
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import version

import pytest

# Top-level app modules whose import exercises the whole dependency chain.
APP_MODULES = [
    "tripplanner.api",
    "tripplanner.graph",
    "tripplanner.agents.trip_agent",
]

# Critical third-party deps that must be present with a resolvable version.
CRITICAL_PACKAGES = [
    "langgraph",
    "langchain",
    "langchain-core",
    "langchain-openai",
    "openai",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "httpx",
    "websockets",
    "azure-cosmos",
]


@pytest.mark.parametrize("module", APP_MODULES)
def test_app_module_imports(module: str) -> None:
    import_module(module)


@pytest.mark.parametrize("package", CRITICAL_PACKAGES)
def test_critical_package_has_version(package: str) -> None:
    resolved = version(package)
    assert resolved, f"{package} reports no version — likely a corrupted install"
