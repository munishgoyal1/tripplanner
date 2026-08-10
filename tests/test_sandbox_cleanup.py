from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SANDBOX_SCRIPT = ROOT / "scripts" / "dev" / "sandbox.ps1"


def test_promotion_checks_github_auth_before_sync() -> None:
    source = SANDBOX_SCRIPT.read_text(encoding="utf-8")

    auth_check = source.index("gh auth status --hostname github.com")
    sync_step = source.index('Write-Host "== 1/6 sync with origin/$BaseBranch =="')

    assert auth_check < sync_step
    assert "gh auth login --hostname github.com --web" in source


def test_worktree_cleanup_retries_transient_windows_lock(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    harness = tmp_path / "cleanup-harness.ps1"
    harness.write_text(
        r"""
param([string]$SourcePath, [string]$WorktreePath)
$source = Get-Content -Raw -LiteralPath $SourcePath
$definition = [regex]::Match(
    $source,
    '(?ms)^function Remove-SandboxLeftovers \{.*?^\}'
).Value
if (-not $definition) { throw "Remove-SandboxLeftovers was not found." }
Invoke-Expression $definition

$script:attempts = 0
function Remove-Item {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [switch]$Recurse,
        [switch]$Force
    )
    $script:attempts++
    if ($script:attempts -lt 3) { throw "temporarily locked" }
    Microsoft.PowerShell.Management\Remove-Item `
        -LiteralPath $LiteralPath -Recurse:$Recurse -Force:$Force
}

$removed = Remove-SandboxLeftovers -Path $WorktreePath
@{ removed = $removed; attempts = $script:attempts; exists = Test-Path $WorktreePath } |
    ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(harness),
            "-SourcePath",
            str(SANDBOX_SCRIPT),
            "-WorktreePath",
            str(worktree),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"removed": True, "attempts": 3, "exists": False}


def test_promotion_cleanup_removes_pending_conflict_marker() -> None:
    source = SANDBOX_SCRIPT.read_text(encoding="utf-8")

    assert "Remove-PendingMergesFor" not in source
    assert 'pending-conflict-$((Split-Path -Leaf $entry.worktree)).json' in source
