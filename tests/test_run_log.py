from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUN_LOG_LIB = ROOT / "scripts" / "dev" / "lib" / "run-log.ps1"


def test_nested_script_does_not_end_the_outer_transcript(tmp_path: Path) -> None:
    # deploy-canary.ps1 runs push-image.ps1 in-process. The nested script's
    # Stop-RunLog used to stop the canary transcript, so canary-deploy.log lost
    # the whole deploy and smoke stage that followed the image push.
    harness = tmp_path / "run-log-harness.ps1"
    harness.write_text(
        r"""
param([string]$LibPath, [string]$LogDir)
. $LibPath
function Get-RunLogDirectory { return $LogDir }
function Add-RunLogIndex { param($Name, $Outcome) }

Start-RunLog -Name "outer" | Out-Null
Start-RunLog -Name "nested" | Out-Null
Write-Host "inside-nested"
Stop-RunLog
Write-Host "after-nested"
if (-not $global:TripplannerRunLog) { throw "nested Stop-RunLog ended the outer run" }
Stop-RunLog
Write-Host "after-outer"
if ($global:TripplannerRunLog) { throw "outer Stop-RunLog left the run open" }
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(harness),
            "-LibPath",
            str(RUN_LOG_LIB),
            "-LogDir",
            str(tmp_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    transcript = (tmp_path / "outer.log").read_text(encoding="utf-8")
    assert "inside-nested" in transcript
    assert "after-nested" in transcript
    assert "outer completed after" in transcript
    assert "after-outer" not in transcript
    assert not (tmp_path / "nested.log").exists()
