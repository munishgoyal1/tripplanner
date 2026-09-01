"""Select the narrowest safe validation targets for a repository change.

Selection is intentionally fail-closed: an unrecognised production path widens
to the complete applicable suite instead of silently skipping coverage.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "scripts" / "dev" / "test-selection.json"
EXPECTED_BEHAVIORS = ROOT / "docs" / "EXPECTED_BEHAVIORS.md"
BEHAVIOR_HEADING = re.compile(r"^### (EB-[A-Z]+-[0-9]+)\b", re.MULTILINE)
TEST_LINK = re.compile(r"\[`([^`]+)`\]\(\.\./((?:tests|frontend)/[^)#]+)(?:#[^)]+)?\)")
TEST_NAME = re.compile(r"\s+-\s+`(test_[^`]+)`")


@dataclass
class Selection:
    backend: set[str] = field(default_factory=set)
    frontend: set[str] = field(default_factory=set)
    backend_all: bool = False
    frontend_all: bool = False
    frontend_typecheck: bool = False
    frontend_build: bool = False
    mobile: bool = False
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        backend = ["tests"] if self.backend_all else sorted(self.backend)
        frontend = ["frontend"] if self.frontend_all else sorted(self.frontend)
        return {
            "backend": backend,
            "frontend": frontend,
            "backend_all": self.backend_all,
            "frontend_all": self.frontend_all,
            "frontend_typecheck": self.frontend_typecheck,
            "frontend_build": self.frontend_build,
            "mobile": self.mobile,
            "reasons": self.reasons,
        }


def _normalise(path: str) -> str:
    value = path.replace("\\", "/").removeprefix("./")
    try:
        return Path(value).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return value


def _existing(paths: Iterable[str]) -> set[str]:
    return {path for path in paths if (ROOT / path.split("::", 1)[0]).is_file()}


def _pytest_target(path: str, test_name: str) -> str:
    source = ROOT / path
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    nodes: list[str] = []
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == test_name:
            nodes.append(f"{path}::{test_name}")
        if not isinstance(item, ast.ClassDef):
            continue
        for member in item.body:
            if (
                isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and member.name == test_name
            ):
                nodes.append(f"{path}::{item.name}::{test_name}")
    if len(nodes) != 1:
        detail = "missing" if not nodes else "ambiguous"
        raise ValueError(f"Behavior proof {path}::{test_name} is {detail}")
    return nodes[0]


def _changed_paths(base: str, head: str | None) -> list[str]:
    revision = f"{base}..{head}" if head else base
    result = subprocess.run(
        ["git", "diff", "--name-only", revision],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [line for line in result.stdout.splitlines() if line.strip()]
    if not head:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.extend(line for line in untracked.stdout.splitlines() if line.strip())
    return list(dict.fromkeys(_normalise(path) for path in paths))


def behavior_tests(behavior_id: str, document: Path = EXPECTED_BEHAVIORS) -> tuple[str, ...]:
    text = document.read_text(encoding="utf-8")
    headings = list(BEHAVIOR_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        if heading.group(1) != behavior_id:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        targets: list[str] = []
        for line in section.splitlines():
            link = TEST_LINK.search(line)
            if not link:
                continue
            _label, path = link.groups()
            test_name = TEST_NAME.search(line)
            target = (
                _pytest_target(path, test_name.group(1))
                if path.startswith("tests/") and test_name
                else path
            )
            targets.append(target)
        return tuple(dict.fromkeys(targets))
    raise ValueError(f"Unknown expected-behavior ID: {behavior_id}")


def _apply_behavior(selection: Selection, behavior_id: str) -> None:
    targets = behavior_tests(behavior_id)
    missing = [target for target in targets if not (ROOT / target.split("::", 1)[0]).is_file()]
    if missing:
        raise ValueError(f"{behavior_id} links to missing test files: {', '.join(missing)}")
    for target in targets:
        if target.startswith("tests/"):
            selection.backend.add(target)
        else:
            selection.frontend.add(target)
    selection.frontend_typecheck = selection.frontend_typecheck or bool(selection.frontend)
    selection.reasons.append(f"{behavior_id}: executable proofs from EXPECTED_BEHAVIORS.md")


def _infer_direct_test(path: str) -> str | None:
    if not path.startswith("src/tripplanner/") or not path.endswith(".py"):
        return None
    basename = Path(path).stem
    candidate = f"tests/test_{basename}.py"
    return candidate if (ROOT / candidate).is_file() else None


def _infer_frontend_test(path: str) -> str | None:
    if not path.startswith("frontend/") or Path(path).suffix not in {".ts", ".tsx"}:
        return None
    source = ROOT / path
    stem = source.with_suffix("")
    for suffix in (".test.ts", ".test.tsx"):
        candidate = Path(f"{stem}{suffix}")
        if candidate.is_file():
            return candidate.relative_to(ROOT).as_posix()
    return None


def select_tests(
    paths: Iterable[str],
    *,
    behavior_ids: Iterable[str] = (),
    policy_path: Path = DEFAULT_POLICY,
) -> Selection:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    selection = Selection()
    normalised = tuple(dict.fromkeys(_normalise(path) for path in paths))

    for behavior_id in behavior_ids:
        _apply_behavior(selection, behavior_id)

    for path in normalised:
        matched = False
        if (
            path.startswith("tests/test_")
            and path.endswith(".py")
            and (ROOT / path).is_file()
        ):
            selection.backend.add(path)
            selection.reasons.append(f"{path}: changed backend test")
            matched = True
        direct = _infer_direct_test(path)
        if direct:
            selection.backend.add(direct)
            selection.reasons.append(f"{path}: matching module test {direct}")
            matched = True
        frontend = _infer_frontend_test(path)
        if frontend:
            selection.frontend.add(frontend)
            selection.frontend_typecheck = True
            selection.reasons.append(f"{path}: colocated frontend test {frontend}")
            matched = True

        for rule in policy["rules"]:
            if not any(fnmatch.fnmatch(path, pattern) for pattern in rule["patterns"]):
                continue
            matched = True
            selection.backend.update(_existing(rule.get("backend", ())))
            selection.frontend.update(_existing(rule.get("frontend", ())))
            selection.backend_all |= rule.get("backend_all", False)
            selection.frontend_all |= rule.get("frontend_all", False)
            selection.frontend_typecheck |= rule.get("frontend_typecheck", False)
            selection.frontend_build |= rule.get("frontend_build", False)
            selection.mobile |= rule.get("mobile", False)
            selection.reasons.append(f"{path}: {rule['reason']}")

        if matched or path.startswith(tuple(policy["no_test_prefixes"])):
            continue
        if path.startswith(("frontend/", "packages/tripplanner-client/")):
            selection.frontend_all = True
            selection.frontend_typecheck = True
            selection.frontend_build = True
            selection.reasons.append(f"{path}: unmapped client change; complete frontend fallback")
        elif path.startswith(("src/", "scripts/", "infra/", "mobile/", "tests/")):
            selection.backend_all = True
            selection.mobile |= path.startswith("mobile/")
            selection.reasons.append(
                f"{path}: unmapped executable change; complete backend fallback"
            )

    if selection.backend_all:
        selection.backend.clear()
    if selection.frontend_all:
        selection.frontend.clear()
    return selection


def validation_commands(selection: Selection) -> tuple[str, ...]:
    commands: list[str] = []
    if selection.backend_all:
        commands.append("python -m pytest -q")
    elif selection.backend:
        commands.append("python -m pytest -q " + " ".join(sorted(selection.backend)))
    if selection.frontend_all:
        commands.append("npm --prefix frontend run test:all")
    elif selection.frontend:
        targets = " ".join(path.removeprefix("frontend/") for path in sorted(selection.frontend))
        commands.append(f"npm --prefix frontend exec vitest run -- {targets}")
    if selection.frontend_typecheck:
        commands.append("npm --prefix frontend run typecheck")
    if selection.frontend_build:
        commands.append("npm --prefix frontend run build")
    if selection.mobile:
        commands.extend(("npm --prefix mobile run typecheck", "npm --prefix mobile run lint"))
    return tuple(commands)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Changed repository path")
    parser.add_argument(
        "--base", help="Git base revision; includes staged and working-tree changes"
    )
    parser.add_argument("--head", help="Optional Git head revision used with --base")
    parser.add_argument("--behavior", action="append", default=[], help="Expected-behavior ID")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser


def main() -> int:
    args = _parser().parse_args()
    paths = list(args.path)
    if args.base:
        paths.extend(_changed_paths(args.base, args.head))
    if not paths and not args.behavior:
        raise SystemExit("Provide --path, --base, or --behavior")
    selection = select_tests(paths, behavior_ids=args.behavior)
    payload = selection.as_dict() | {"commands": validation_commands(selection)}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Selected validation:")
        for command in payload["commands"]:
            print(f"  {command}")
        print("Why:")
        for reason in selection.reasons:
            print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
