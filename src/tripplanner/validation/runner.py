"""Load the corpus, run every check, and report only what is new."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tripplanner.validation import corpus as corpus_module
from tripplanner.validation.checks import check_record
from tripplanner.validation.corpus import CorpusRecord
from tripplanner.validation.findings import Finding, Group, group, load_baseline, new_groups

DEFAULT_CORPUS_DIR = "corpus"
BASELINE_FILE = "audit-baseline.json"


@dataclass
class AuditResult:
    records: list[CorpusRecord] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    new: list[Group] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def corpus_size(self) -> int:
        return len(self.records)

    @property
    def provenance_mix(self) -> dict[str, int]:
        return corpus_module.counts_by_provenance(self.records)


def corpus_root(repo_root: Path) -> Path:
    return repo_root / DEFAULT_CORPUS_DIR


def baseline_path(repo_root: Path) -> Path:
    return corpus_root(repo_root) / BASELINE_FILE


def collect(
    repo_root: Path,
    *,
    debug_store: bool = True,
    revisions: bool = True,
    databases: list[str] | None = None,
    fixtures: bool = True,
) -> tuple[list[CorpusRecord], list[str], list[str]]:
    """Gather every trip the harness can see, saying what it read and skipped."""
    from tripplanner.validation.emulator import EmulatorUnreachableError, list_sandbox_databases

    records: list[CorpusRecord] = []
    sources: list[str] = []
    skipped: list[str] = []

    if debug_store:
        found = corpus_module.from_debug_store(revisions=revisions)
        sources.append(f"debug-store ({len(found)})")
        records.extend(found)

    if databases is None:
        try:
            databases = list_sandbox_databases()
        except EmulatorUnreachableError as error:
            databases = []
            skipped.append(f"emulator unreachable: {error}")
    for database in databases:
        try:
            found = corpus_module.from_emulator(database)
        except EmulatorUnreachableError as error:
            skipped.append(f"{database}: {error}")
            continue
        except ValueError as error:
            skipped.append(str(error))
            continue
        sources.append(f"{database} ({len(found)})")
        records.extend(found)

    if fixtures:
        directory = repo_root / "scripts" / "dev" / "sandbox-seed"
        found = corpus_module.from_fixtures(directory)
        if found:
            sources.append(f"fixtures ({len(found)})")
        records.extend(found)

    return corpus_module.deduplicate(records), sources, skipped


def audit(
    repo_root: Path,
    *,
    records: list[CorpusRecord] | None = None,
    baseline: dict[str, Any] | None = None,
    render: bool = True,
    mutate: bool = True,
    **collect_kwargs: Any,
) -> AuditResult:
    from tripplanner.validation.mutations import check_metamorphic
    from tripplanner.validation.render import check_render

    sources: list[str] = []
    skipped: list[str] = []
    if records is None:
        records, sources, skipped = collect(repo_root, **collect_kwargs)
    findings: list[Finding] = []
    for record in records:
        findings.extend(check_record(record))
        if render:
            findings.extend(check_render(record))
        if mutate:
            findings.extend(check_metamorphic(record))
    grouped = group(findings)
    if baseline is None:
        baseline = load_baseline(baseline_path(repo_root))
    return AuditResult(
        records=records,
        findings=findings,
        groups=grouped,
        new=new_groups(grouped, baseline),
        sources=sources,
        skipped=skipped,
    )
