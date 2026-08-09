from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "record-lab-implementation.ps1"
SANDBOX_SCRIPT = ROOT / "scripts" / "dev" / "sandbox.ps1"


def write_store(path: Path) -> dict[str, object]:
    store = {
        "travel-documents": {
            "labId": "travel-documents",
            "labTitle": "Travel documents",
            "selection": "vault",
            "selectionLabel": "B · Account vault",
            "comment": "Keep originals out of storage.",
            "disposition": "ready",
            "handoffs": [{
                "version": 1,
                "selection": "vault",
                "selectionLabel": "B · Account vault",
                "comment": "Keep originals out of storage.",
                "disposition": "ready",
                "recordedAt": "2026-08-06T12:48:15.693Z",
            }],
            "implementations": [],
            "updatedAt": "2026-08-06T12:48:15.693Z",
        },
        "unrelated": {"labId": "unrelated", "selection": "a"},
    }
    path.write_text(json.dumps(store), encoding="utf-8")
    return store


def run_script(
    store_path: Path,
    evidence: str = "Commit abc123; 14 Labs tests passed.",
    state: str = "implemented-review",
) -> subprocess.CompletedProcess[str]:
    arguments = [
            "pwsh",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-LabId",
            "travel-documents",
            "-Evidence",
            evidence,
            "-State",
            state,
            "-StorePath",
            str(store_path),
        ]
    return subprocess.run(
        arguments,
        capture_output=True,
        check=False,
        text=True,
    )


def test_records_implementation_against_latest_handoff(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    original = write_store(store_path)

    result = run_script(store_path)

    assert result.returncode == 0, result.stderr
    assert "implementation v1 -> state version v2" in result.stdout
    stored = json.loads(store_path.read_text(encoding="utf-8-sig"))
    lab = stored["travel-documents"]
    assert lab["disposition"] == "implemented-review"
    assert lab["handoffs"][:-1] == original["travel-documents"]["handoffs"]
    assert lab["handoffs"][-1] == {
        "version": 2,
        "selection": "vault",
        "selectionLabel": "B · Account vault",
        "comment": "Keep originals out of storage.",
        "disposition": "implemented-review",
        "summary": "Commit abc123; 14 Labs tests passed.",
        "recordedAt": lab["updatedAt"],
    }
    assert lab["implementations"] == [{
        "version": 1,
        "handoffVersion": 2,
        "selection": "vault",
        "selectionLabel": "B · Account vault",
        "comment": "Keep originals out of storage.",
        "summary": "Commit abc123; 14 Labs tests passed.",
        "recordedAt": lab["updatedAt"],
    }]
    assert stored["unrelated"] == original["unrelated"]
    assert (tmp_path / "selections.previous.json").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_records_each_successful_implementation_iteration(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    first = run_script(store_path)

    second = run_script(store_path, "A second successful iteration")

    assert first.returncode == 0
    assert second.returncode == 0, second.stderr
    updated = json.loads(store_path.read_text(encoding="utf-8-sig"))["travel-documents"]
    assert [entry["version"] for entry in updated["handoffs"]] == [1, 2, 3]
    assert [entry["summary"] for entry in updated["handoffs"][1:]] == [
        "Commit abc123; 14 Labs tests passed.",
        "A second successful iteration",
    ]
    assert [entry["version"] for entry in updated["implementations"]] == [1, 2]
    assert updated["implementations"][1]["handoffVersion"] == 3


def test_completion_preserves_latest_implemented_handoff(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    implemented = run_script(store_path)
    assert implemented.returncode == 0, implemented.stderr

    stored = json.loads(store_path.read_text(encoding="utf-8-sig"))
    lab = stored["travel-documents"]
    lab["handoffs"].append({
        "version": 3,
        "selection": "carry",
        "selectionLabel": "A · Carry originals",
        "comment": "Reconsider this option.",
        "disposition": "ready",
        "recordedAt": "2026-08-06T14:00:00.000Z",
    })
    store_path.write_text(json.dumps(stored), encoding="utf-8")

    completed = run_script(store_path, "Promoted after verification.", "completed")

    assert completed.returncode == 0, completed.stderr
    updated = json.loads(store_path.read_text(encoding="utf-8-sig"))["travel-documents"]
    assert updated["handoffs"][-1]["version"] == 4
    assert updated["handoffs"][-1]["selection"] == "vault"
    assert updated["handoffs"][-1]["comment"] == "Keep originals out of storage."
    assert updated["handoffs"][-1]["disposition"] == "completed"


@pytest.mark.parametrize("state", ["ready", "parked", "completed", "discarded"])
def test_records_agent_state_change_as_a_new_version(tmp_path: Path, state: str) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)

    result = run_script(store_path, state=state)

    assert result.returncode == 0, result.stderr
    assert f"state '{state}' as version v2" in result.stdout
    updated = json.loads(store_path.read_text(encoding="utf-8-sig"))["travel-documents"]
    assert updated["disposition"] == state
    assert updated["handoffs"][-1]["version"] == 2
    assert updated["handoffs"][-1]["disposition"] == state
    assert updated["handoffs"][-1]["selection"] == "vault"
    assert updated["handoffs"][-1]["comment"] == "Keep originals out of storage."
    assert updated["handoffs"][-1]["summary"] == "Commit abc123; 14 Labs tests passed."


def test_preserves_singular_legacy_implementation(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    stored["travel-documents"]["implementation"] = {
        "handoffVersion": 1,
        "selection": "vault",
        "selectionLabel": "B · Account vault",
        "comment": "Earlier implementation",
        "summary": "Commit old123.",
        "recordedAt": "2026-08-06T13:00:00.000Z",
    }
    store_path.write_text(json.dumps(stored), encoding="utf-8")
    result = run_script(store_path, "Commit new456.")

    assert result.returncode == 0, result.stderr
    updated = json.loads(store_path.read_text(encoding="utf-8-sig"))["travel-documents"]
    assert [entry["version"] for entry in updated["implementations"]] == [1, 2]
    assert updated["implementations"][0]["summary"] == "Commit old123."
    assert updated["implementations"][1]["summary"] == "Commit new456."
    assert updated["implementations"][1]["handoffVersion"] == 2


def test_sandbox_records_linked_iterations_and_both_promotion_paths() -> None:
    source = SANDBOX_SCRIPT.read_text(encoding="utf-8")

    assert '[string]$LabId = ""' in source
    assert '[string]$IterationSummary = ""' in source
    assert source.count('Write-SandboxLabVersion -Entry $entry -State "implemented-review"') == 1
    assert '$labsReady = Wait-SandboxEndpoint -Url $labsUrl' in source
    assert 'Invoke-Git -WorkingDirectory $Entry.worktree -Arguments @("status", "--porcelain")' in source
    assert 'labBaselineCommit' in source
    assert 'lastLabIterationCommit' in source
    assert 'merge-base --is-ancestor $previousCommit $commit' in source
    assert 'diff-tree --no-commit-id --name-only -r $revision' in source
    assert '$_ -ne "docs/ux-experiments/LAB_SELECTIONS.json"' in source
    assert 'if ($parents.Count -eq 1 -and $labRecordOnly)' in source
    assert 'Assert-SandboxLabReadyForPromotion -Entry $entry' in source
    assert source.count('Write-SandboxLabVersion -Entry $entry -State "completed"') == 2


def test_promotion_allows_lab_record_commit_but_rejects_later_product_work(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "sandbox"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)

    def commit(path: str, content: str, message: str) -> str:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", path], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()

    base = commit("README.md", "base\n", "base")
    reviewed = commit("frontend/src/App.tsx", "reviewed\n", "reviewed product change")
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/master", base],
        check=True,
    )
    commit(
        "docs/ux-experiments/LAB_SELECTIONS.json",
        '{"lab":"implemented-review"}\n',
        "record Lab review",
    )

    harness = tmp_path / "assert-promotion.ps1"
    harness.write_text(
        f'''$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    "{SANDBOX_SCRIPT.as_posix()}", [ref]$tokens, [ref]$errors)
$definition = $ast.Find({{ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq "Assert-SandboxLabReadyForPromotion"
}}, $true)
Invoke-Expression $definition.Extent.Text
function Invoke-Git {{
    param([string]$WorkingDirectory, [string[]]$Arguments)
    $output = & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {{ throw "git failed" }}
    return $output
}}
$entry = [pscustomobject]@{{
    slug = "test"
    labId = "lab"
    worktree = "{repo.as_posix()}"
    lastLabIterationCommit = "{reviewed}"
}}
Assert-SandboxLabReadyForPromotion -Entry $entry -Base master -AllowContainedIteration
''',
        encoding="utf-8",
    )
    allowed = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(harness)],
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0, allowed.stderr

    commit("frontend/src/App.tsx", "unreviewed\n", "unreviewed product change")
    rejected = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(harness)],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "HEAD changed after its last recorded Lab iteration" in rejected.stderr