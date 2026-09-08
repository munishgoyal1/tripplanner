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
    def raw_corpus_size(self) -> int:
        return sum(len(record.links) for record in self.records)

    @property
    def provenance_mix(self) -> dict[str, int]:
        return corpus_module.counts_by_provenance(self.records)

    @property
    def cohort_mix(self) -> dict[str, int]:
        return corpus_module.counts_by_cohort(self.records)


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
    generated_finals: bool = True,
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

    if generated_finals:
        from tripplanner.validation import place_cache

        root = corpus_root(repo_root)
        found = corpus_module.from_generated_finals(
            root / "trips",
            places=place_cache.load(place_cache.cache_path(root)),
        )
        if found:
            sources.append(f"generated finals ({len(found)})")
        records.extend(found)

    saved = corpus_module.from_lane_snapshots(corpus_root(repo_root))
    if saved:
        sources.append(f"saved lanes ({len(saved)})")
    records.extend(saved)

    return corpus_module.deduplicate(records), sources, skipped


def audit(
    repo_root: Path,
    *,
    records: list[CorpusRecord] | None = None,
    baseline: dict[str, Any] | None = None,
    render: bool = True,
    mutate: bool = True,
    quality_ratings: dict[str, Any] | None = None,
    **collect_kwargs: Any,
) -> AuditResult:
    from tripplanner.validation.mutations import check_metamorphic
    from tripplanner.validation.quality import gate_findings
    from tripplanner.validation.quality import load as load_quality_ratings
    from tripplanner.validation.render import check_render

    sources: list[str] = []
    skipped: list[str] = []
    if records is None:
        records, sources, skipped = collect(repo_root, **collect_kwargs)
    if quality_ratings is None:
        quality_ratings = load_quality_ratings(corpus_root(repo_root))
    findings: list[Finding] = []
    for record in records:
        findings.extend(check_record(record))
        findings.extend(gate_findings(record, quality_ratings))
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
