from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SYNC_COMMON = ROOT / "scripts" / "dev" / "lib" / "sync-common.ps1"


def test_frontend_dependency_link_is_cross_platform_and_removable(tmp_path: Path) -> None:
    target = tmp_path / "node_modules"
    target.mkdir()
    link = tmp_path / "merged" / "node_modules"
    link.parent.mkdir()
    harness = tmp_path / "link-harness.ps1"
    harness.write_text(
        r"""
param([string]$SourcePath, [string]$LinkPath, [string]$TargetPath)
$source = Get-Content -Raw -LiteralPath $SourcePath
$definition = [regex]::Match(
    $source,
    '(?ms)^function New-FrontendDependencyLink \{.*?^\}'
).Value
if (-not $definition) { throw "New-FrontendDependencyLink was not found." }
Invoke-Expression $definition
function Write-SyncLog { param([string]$Level, [string]$Message) }
$created = New-FrontendDependencyLink -Path $LinkPath -Target $TargetPath
$isLink = if ($IsWindows) {
    (Get-Item -LiteralPath $LinkPath).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)
} else {
    (Get-Item -LiteralPath $LinkPath -Force).LinkType -eq "SymbolicLink"
}
Remove-Item -LiteralPath $LinkPath -Force
@{
    created = $created
    isLink = $isLink
    linkExists = Test-Path $LinkPath
    targetExists = Test-Path $TargetPath
} | ConvertTo-Json -Compress
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
            str(SYNC_COMMON),
            "-LinkPath",
            str(link),
            "-TargetPath",
            str(target),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "created": True,
        "isLink": True,
        "linkExists": False,
        "targetExists": True,
    }


def test_missing_frontend_dependencies_block_integration_publication() -> None:
    source = SYNC_COMMON.read_text(encoding="utf-8")

    assert '$itemType = if ($IsWindows) { "Junction" } else { "SymbolicLink" }' in source
    assert (
        '$blocking.Add("frontend vitest unavailable: node_modules could not be linked")'
        in source
    )
    assert "Skipping frontend tests: node_modules was unavailable to link." not in source
