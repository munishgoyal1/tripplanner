"""Classify a full-suite run against the checked-in known-failure baseline.

``scripts/dev/suite-health.ps1`` runs the suites and hands the raw artifacts
here. This module owns everything that has to be *correct* -- parsing, the
baseline diff, the report -- so it can be tested exhaustively from recorded
fixtures without ever running a 20-minute suite.

The four buckets are the whole point:

* ``new``     -- failed now, absent from the baseline. The only red signal.
* ``known``   -- failed now and in the baseline. Reported with its age.
* ``fixed``   -- in the baseline, passed now. Retire it with --update-baseline.
* ``missing`` -- in the baseline and absent from the run entirely: renamed,
  deleted, or skipped. Never folded into ``fixed``. Deleting a failing test is
  the cheapest way to make a system like this lie, and this bucket is what
  catches it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

BASELINE_VERSION = 1

# `FAILED tests/test_trip_rebalance.py::test_it_reduces_travel - AssertionError: ...`
_SUMMARY_LINE = re.compile(r"^(?P<kind>FAILED|ERROR)\s+(?P<node>\S+?)(?:\s+-\s+(?P<message>.*))?$")
# A node id is <path>.py::<test>, optionally ::Class:: and optionally [params].
_NODE_SHAPE = re.compile(r"^[^\s:]+\.py::[^\s]+$")
# Lines that legitimately follow the short summary block.
_BLOCK_END = re.compile(r"^(=+|-+|\s*$|\d+ (passed|failed|error))")


class TruncatedOutputError(RuntimeError):
    """Raised when the captured pytest output cannot be parsed verbatim.

    Start-Transcript records console-rendered text at the host window width, so
    a narrow console hard-wraps node ids mid-word and the parse would silently
    produce a truncated -- but still plausible -- id. Refusing loudly is the only
    safe behaviour: a wrong node id means a real failure is filed as NEW forever
    and never matches its baseline entry.
    """


@dataclass(frozen=True)
class Failure:
    """One failing test, identified the way its suite identifies it."""

    id: str
    message: str = ""


@dataclass
class SuiteResult:
    """What one suite did, independent of the baseline."""

    name: str
    ran: bool
    failures: tuple[Failure, ...] = ()
    totals: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    # Test files the suite collected but never executed -- a worker that failed
    # to start, say. The run happened, but it is incomplete.
    unrun: tuple[str, ...] = ()


@dataclass
class Classification:
    """One suite's run, diffed against its baseline."""

    suite: str
    new: tuple[Failure, ...]
    known: tuple[Failure, ...]
    fixed: tuple[str, ...]
    missing: tuple[str, ...]
    totals: dict[str, Any]
    ran: bool
    error: str = ""
    unrun: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# pytest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JunitFailure:
    """One failing ``<testcase>`` as junit recorded it.

    pytest's default ``xunit2`` family writes no ``file`` attribute, only a
    dotted ``classname`` (``tests.test_a`` or ``tests.test_a.TestThing``), so
    ``source`` is usually empty. ``name`` keeps any ``[param]`` suffix: two
    failing parametrizations of one test are two failures, not one.
    """

    source: str
    classname: str
    name: str


def parse_pytest_junit(path: Path) -> tuple[set[JunitFailure], dict[str, Any]]:
    """Return the failing test cases plus run totals.

    junit is pytest core -- no plugin -- and is the arithmetic authority here.
    It is deliberately *not* used to rebuild node ids: 13 test files in this repo
    use ``class Test*``, so the classname-to-nodeid mapping is lossy. The
    reverse direction -- node id to expected classname -- is exact, and that is
    how :func:`reconcile_pytest` matches the two records.
    """
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    failed: set[JunitFailure] = set()
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "duration_seconds": 0.0}
    for suite in suites:
        totals["tests"] += int(suite.get("tests", 0))
        totals["failures"] += int(suite.get("failures", 0))
        totals["errors"] += int(suite.get("errors", 0))
        totals["skipped"] += int(suite.get("skipped", 0))
        totals["duration_seconds"] += float(suite.get("time", 0.0))
        for case in suite.iter("testcase"):
            if case.find("failure") is None and case.find("error") is None:
                continue
            failed.add(
                JunitFailure(
                    source=(case.get("file") or "").replace("\\", "/"),
                    classname=case.get("classname") or "",
                    name=case.get("name") or "",
                )
            )

    totals["failed"] = totals["failures"] + totals["errors"]
    totals["passed"] = totals["tests"] - totals["failed"] - totals["skipped"]
    totals["duration_seconds"] = round(totals["duration_seconds"], 2)
    return failed, totals


def parse_pytest_summary(text: str) -> tuple[Failure, ...]:
    """Read verbatim node ids out of a ``-rfE`` short test summary.

    Raises :class:`TruncatedOutputError` when a line looks wrapped rather than
    complete.
    """
    lines = text.splitlines()
    failures: list[Failure] = []
    seen: set[str] = set()

    for index, raw in enumerate(lines):
        line = raw.rstrip()
        match = _SUMMARY_LINE.match(line)
        if not match:
            continue
        node = match.group("node")

        if not _NODE_SHAPE.match(node):
            raise TruncatedOutputError(
                f"line {index + 1}: {node!r} is not a complete pytest node id. "
                "The captured output is probably console-wrapped; re-run with "
                "COLUMNS=400 and capture pytest's stdout directly."
            )

        # A wrapped node id leaves an orphan continuation on the next line: no
        # leading whitespace, and matching nothing the summary block emits.
        if index + 1 < len(lines):
            following = lines[index + 1]
            if (
                following
                and not following[0].isspace()
                and not _SUMMARY_LINE.match(following.rstrip())
                and not _BLOCK_END.match(following)
            ):
                raise TruncatedOutputError(
                    f"line {index + 2}: {following.rstrip()!r} looks like the wrapped "
                    "remainder of the node id above. Re-run with COLUMNS=400 and "
                    "capture pytest's stdout directly."
                )

        if node in seen:
            continue
        seen.add(node)
        failures.append(Failure(id=node, message=(match.group("message") or "").strip()))

    return tuple(failures)


def _junit_matches(node_id: str, case: JunitFailure) -> bool:
    """Whether a verbatim ``-rfE`` node id names this junit test case."""
    source, _, remainder = node_id.partition("::")
    *classes, name = remainder.split("::")
    if case.name != name:
        return False
    if case.source:
        return case.source == source
    module = source.removesuffix(".py").replace("/", ".")
    return case.classname == ".".join([module, *classes])


def reconcile_pytest(
    summary_failures: tuple[Failure, ...], junit_failures: set[JunitFailure]
) -> tuple[Failure, ...]:
    """Cross-check the two pytest sources and return the reconciled failures.

    junit says how many failed and where; ``-rfE`` says exactly which node. If
    they disagree the run is not trustworthy enough to rewrite a baseline from,
    so this raises rather than guessing.
    """
    if len(summary_failures) != len(junit_failures):
        raise TruncatedOutputError(
            f"pytest reported {len(junit_failures)} failing tests in junit but the "
            f"short summary yielded {len(summary_failures)}. Refusing to classify a "
            "run whose two records disagree."
        )

    for failure in summary_failures:
        if not any(_junit_matches(failure.id, case) for case in junit_failures):
            raise TruncatedOutputError(
                f"{failure.id!r} does not match any failure junit recorded. The node "
                "id is probably truncated; re-run with COLUMNS=400."
            )
    return summary_failures


# ---------------------------------------------------------------------------
# vitest
# ---------------------------------------------------------------------------


def _repo_relative(raw_name: str, repo_root: Path) -> str:
    try:
        return Path(raw_name).resolve().relative_to(repo_root.resolve()).as_posix()
    except (ValueError, OSError):
        return raw_name.replace("\\", "/")


def parse_vitest_file_list(path: Path, repo_root: Path) -> set[str]:
    """Read ``vitest list --filesOnly --json`` output: every file vitest would run."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {_repo_relative(entry["file"], repo_root) for entry in payload if entry.get("file")}


def parse_vitest_json(
    path: Path, repo_root: Path
) -> tuple[tuple[Failure, ...], dict[str, Any], set[str]]:
    """Read vitest's built-in json reporter output.

    Failures are keyed ``<repo-relative file>::<full test name>`` so the id is
    stable across machines; the reporter records absolute paths. Also returns
    the files that actually executed: a file whose worker never started is
    simply absent from this report, with no failure and no skip to show for it.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    failures: list[Failure] = []
    observed: set[str] = set()
    ran_files: set[str] = set()
    passed = failed = skipped = 0

    for file_result in payload.get("testResults", []) or []:
        relative = _repo_relative(file_result.get("name") or "", repo_root)
        ran_files.add(relative)
        for assertion in file_result.get("assertionResults", []) or []:
            full = assertion.get("fullName") or assertion.get("title") or "<unnamed>"
            status = assertion.get("status")
            if status not in {"skipped", "pending", "todo"}:
                observed.add(f"{relative}::{full}")
            if status == "passed":
                passed += 1
                continue
            if status in {"skipped", "pending", "todo"}:
                skipped += 1
                continue
            failed += 1
            messages = assertion.get("failureMessages") or []
            first = messages[0].strip().splitlines()[0] if messages else ""
            failures.append(Failure(id=f"{relative}::{full}", message=first))

    totals = {
        "tests": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "observed_ids": observed,
    }
    if isinstance(payload.get("startTime"), (int, float)) and payload.get("duration"):
        totals["duration_seconds"] = round(float(payload["duration"]) / 1000.0, 2)
    return tuple(failures), totals, ran_files


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": BASELINE_VERSION, "pytest": {}, "vitest": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_entries(baseline: dict[str, Any], suite: str) -> dict[str, dict[str, Any]]:
    section = baseline.get(suite) or {}
    return {entry["id"]: entry for entry in section.get("failures", []) if entry.get("id")}


def classify(result: SuiteResult, baseline: dict[str, Any]) -> Classification:
    """Diff one suite's failures against its baseline entries."""
    known_entries = baseline_entries(baseline, result.name)

    if not result.ran:
        # A suite that could not run tells us nothing about its baseline; calling
        # every entry "fixed" would be the worst possible lie.
        return Classification(
            suite=result.name,
            new=(),
            known=(),
            fixed=(),
            missing=(),
            totals=result.totals,
            ran=False,
            error=result.error,
        )

    failed_now = {failure.id: failure for failure in result.failures}
    new = tuple(f for f in result.failures if f.id not in known_entries)
    known = tuple(f for f in result.failures if f.id in known_entries)

    observed = observed_ids(result)
    fixed: list[str] = []
    missing: list[str] = []
    for entry_id in known_entries:
        if entry_id in failed_now:
            continue
        if observed is None or entry_id in observed:
            fixed.append(entry_id)
        else:
            missing.append(entry_id)

    return Classification(
        suite=result.name,
        new=new,
        known=known,
        fixed=tuple(sorted(fixed)),
        missing=tuple(sorted(missing)),
        totals=result.totals,
        ran=True,
        unrun=result.unrun,
    )


def observed_ids(result: SuiteResult) -> set[str] | None:
    """Ids the run is known to have executed, or ``None`` when unknown.

    ``None`` means the caller could not enumerate executed tests, in which case a
    baseline entry that did not fail is reported as fixed rather than missing.
    """
    return result.totals.get("observed_ids")


def merge_baseline(
    baseline: dict[str, Any], classifications: list[Classification], *, today: str
) -> dict[str, Any]:
    """Rewrite the baseline, preserving the human-owned fields.

    ``first_seen``, ``owner``, ``note`` and ``category`` survive; that is what
    makes the debt measurable over time rather than a rolling snapshot.
    """
    merged: dict[str, Any] = {**baseline, "version": BASELINE_VERSION, "generated": today}
    for key in ("ref", "commit"):
        if baseline.get(key):
            merged[key] = baseline[key]

    for classification in classifications:
        if not classification.ran or classification.unrun:
            # Keep the previous section untouched rather than erasing debt with a
            # run that never happened -- or only partly happened: entries in the
            # files that never executed would otherwise be silently dropped.
            merged[classification.suite] = baseline.get(classification.suite, {})
            continue

        previous = baseline_entries(baseline, classification.suite)
        entries = []
        for failure in sorted(
            classification.new + classification.known, key=lambda item: item.id
        ):
            prior = previous.get(failure.id, {})
            entries.append(
                {
                    "id": failure.id,
                    "first_seen": prior.get("first_seen", today),
                    "message": failure.message or prior.get("message", ""),
                    "category": prior.get("category", "unreviewed"),
                    "owner": prior.get("owner", "unassigned"),
                    "note": prior.get("note", ""),
                }
            )
        entries.extend(dict(previous[node]) for node in classification.missing)
        section = dict(baseline.get(classification.suite) or {})
        section["failures"] = entries
        section["totals"] = {
            key: value for key, value in classification.totals.items() if key != "observed_ids"
        }
        merged[classification.suite] = section

    return merged


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def age_in_days(first_seen: str, today: str) -> int:
    try:
        return (date.fromisoformat(today) - date.fromisoformat(first_seen)).days
    except ValueError:
        return 0


def render_markdown(
    classifications: list[Classification], baseline: dict[str, Any], *, today: str, context: dict
) -> str:
    lines = ["# Suite health", ""]
    lines.append(f"- Run: {today}")
    for key in ("ref", "commit"):
        if context.get(key):
            lines.append(f"- {key.capitalize()}: {context[key]}")

    total_new = sum(len(c.new) for c in classifications)
    verdict = "NO NEW FAILURES" if total_new == 0 else f"{total_new} NEW FAILURE(S)"
    total_unrun = sum(len(c.unrun) for c in classifications)
    if total_unrun:
        verdict += f" — INCOMPLETE: {total_unrun} TEST FILE(S) DID NOT RUN"
    lines += ["", f"**{verdict}**", ""]

    for classification in classifications:
        lines.append(f"## {classification.suite}")
        if not classification.ran:
            lines += ["", f"Did not run: {classification.error or 'unknown error'}", ""]
            continue

        totals = classification.totals
        lines.append(
            "- totals: "
            + ", ".join(
                f"{key} {value}"
                for key, value in totals.items()
                if key != "observed_ids" and value != ""
            )
        )
        entries = baseline_entries(baseline, classification.suite)

        if classification.unrun:
            lines += [
                "",
                f"### DID NOT RUN ({len(classification.unrun)})",
                "Collected but never executed, so none of their tests passed, failed, "
                "or skipped. The totals above do not include them, and the baseline "
                "is not updated from this run.",
            ]
            lines += [f"- `{path}`" for path in classification.unrun]

        lines += ["", f"### NEW ({len(classification.new)})"]
        if not classification.new:
            lines.append("None. Nothing regressed against the baseline.")
        for failure in classification.new:
            lines.append(f"- `{failure.id}`")
            if failure.message:
                lines.append(f"  - {failure.message}")

        lines += ["", f"### KNOWN ({len(classification.known)})"]
        if not classification.known:
            lines.append("None.")
        for failure in sorted(classification.known, key=lambda item: item.id):
            entry = entries.get(failure.id, {})
            age = age_in_days(entry.get("first_seen", today), today)
            category = entry.get("category", "unreviewed")
            owner = entry.get("owner", "unassigned")
            lines.append(f"- `{failure.id}` — {category}, {age}d old, owner {owner}")

        lines += ["", f"### FIXED ({len(classification.fixed)})"]
        if not classification.fixed:
            lines.append("None.")
        for entry_id in classification.fixed:
            lines.append(f"- `{entry_id}` — passing now; retire it with -UpdateBaseline")

        lines += ["", f"### MISSING ({len(classification.missing)})"]
        if not classification.missing:
            lines.append("None.")
        else:
            lines.append(
                "These baseline entries did not run at all. Renamed, deleted, or "
                "skipped — confirm which before retiring any of them."
            )
        for entry_id in classification.missing:
            lines.append(f"- `{entry_id}`")
        lines.append("")

    return "\n".join(lines) + "\n"


def to_json(classifications: list[Classification], *, today: str, context: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {"generated": today, **context, "suites": {}}
    for classification in classifications:
        payload["suites"][classification.suite] = {
            "ran": classification.ran,
            "error": classification.error,
            "totals": {
                key: value
                for key, value in classification.totals.items()
                if key != "observed_ids"
            },
            "new": [{"id": f.id, "message": f.message} for f in classification.new],
            "known": [f.id for f in sorted(classification.known, key=lambda i: i.id)],
            "fixed": list(classification.fixed),
            "missing": list(classification.missing),
            "unrun": list(classification.unrun),
        }
    payload["new_failure_count"] = sum(len(c.new) for c in classifications)
    payload["unrun_file_count"] = sum(len(c.unrun) for c in classifications)
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_results(args: argparse.Namespace, repo_root: Path) -> list[SuiteResult]:
    results: list[SuiteResult] = []

    if args.pytest_junit or args.pytest_log:
        try:
            junit_failures, totals = parse_pytest_junit(Path(args.pytest_junit))
            summary = parse_pytest_summary(Path(args.pytest_log).read_text(encoding="utf-8"))
            failures = reconcile_pytest(summary, junit_failures)
            exit_code = getattr(args, "pytest_exit_code", None)
            if exit_code not in (None, 0, 1) or (exit_code == 1 and not failures):
                raise ValueError(f"pytest exited {exit_code}; the run did not complete normally")
            if not totals["tests"]:
                raise ValueError("pytest executed no tests")
            cases = [
                JunitFailure((case.get("file") or "").replace("\\", "/"),
                             case.get("classname") or "", case.get("name") or "")
                for case in ElementTree.parse(args.pytest_junit).getroot().iter("testcase")
                if case.find("skipped") is None
            ]
            known = baseline_entries(load_baseline(Path(args.baseline)), "pytest")
            totals["observed_ids"] = {
                node for node in known if any(_junit_matches(node, case) for case in cases)
            } | {failure.id for failure in failures}
            results.append(SuiteResult("pytest", True, failures, totals))
        except (TruncatedOutputError, OSError, ElementTree.ParseError, ValueError) as error:
            results.append(SuiteResult("pytest", False, error=str(error)))

    if args.vitest_json:
        try:
            failures, totals, ran_files = parse_vitest_json(Path(args.vitest_json), repo_root)
            exit_code = getattr(args, "vitest_exit_code", None)
            if exit_code not in (None, 0) and not failures:
                raise ValueError(f"vitest exited {exit_code} without assertion failures; check vitest.log")
            if not totals["tests"]:
                raise ValueError("vitest executed no tests")
            unrun: tuple[str, ...] = ()
            totals["files_ran"] = len(ran_files)
            if args.vitest_files:
                expected = parse_vitest_file_list(Path(args.vitest_files), repo_root)
                totals["files_expected"] = len(expected)
                unrun = tuple(sorted(expected - ran_files))
            else:
                totals["files_expected"] = "unknown (no file list; completeness not verified)"
            results.append(SuiteResult("vitest", True, failures, totals, unrun=unrun))
        except (OSError, ValueError, KeyError, TypeError) as error:
            results.append(SuiteResult("vitest", False, error=str(error)))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-junit")
    parser.add_argument("--pytest-log")
    parser.add_argument("--pytest-exit-code", type=int)
    parser.add_argument("--vitest-json")
    parser.add_argument("--vitest-exit-code", type=int)
    parser.add_argument(
        "--vitest-files",
        help="`vitest list --filesOnly --json` output, to detect files that never ran",
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--out", required=True, help="directory for report.md and report.json")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--ref", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path(__file__).resolve().parents[2]
    baseline_path = Path(args.baseline)
    baseline = load_baseline(baseline_path)

    results = build_results(args, repo_root)
    classifications = [classify(result, baseline) for result in results]

    context = {"ref": args.ref, "commit": args.commit}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(
        render_markdown(classifications, baseline, today=args.today, context=context),
        encoding="utf-8",
    )
    payload = to_json(classifications, today=args.today, context=context)
    (out / "report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.update_baseline:
        merged = merge_baseline(baseline, classifications, today=args.today)
        merged["ref"] = args.ref or merged.get("ref", "")
        merged["commit"] = args.commit or merged.get("commit", "")
        baseline_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    print((out / "report.md").read_text(encoding="utf-8"))

    if not classifications or any(not c.ran or c.unrun for c in classifications):
        return 2
    return 1 if payload["new_failure_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
