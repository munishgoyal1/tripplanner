#!/usr/bin/env pwsh
# Shared Python interpreter resolution for scripts/dev dispatchers. Each dispatcher
# used to resolve ".venv" independently, which drifted: some checked only their own
# worktree, some also checked the primary checkout, and a "not found" error named no
# candidates. Dot-source: . "$PSScriptRoot/lib/python-runtime.ps1".

function Resolve-PrimaryCheckoutRoot {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)
    # A sandbox or multiagent worktree has no virtual environment of its own; the
    # shared one lives in the primary checkout, which the git common directory points at.
    $commonDir = & git -C $RepoRoot rev-parse --git-common-dir 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $commonDir) { return $RepoRoot }
    $resolved = if ([System.IO.Path]::IsPathRooted($commonDir)) { $commonDir }
                else { Join-Path $RepoRoot $commonDir }
    return Split-Path -Parent (Resolve-Path $resolved).Path
}

function Resolve-TripplannerPython {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [switch]$Quiet
    )

    $primaryRoot = Resolve-PrimaryCheckoutRoot -RepoRoot $RepoRoot
    $candidates = @(
        (Join-Path $RepoRoot ".venv/bin/python"),
        (Join-Path $RepoRoot ".venv/Scripts/python.exe"),
        (Join-Path $primaryRoot ".venv/bin/python"),
        (Join-Path $primaryRoot ".venv/Scripts/python.exe")
    ) | Select-Object -Unique
    $python = $candidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) {
        $python = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
    }
    if (-not $python) {
        $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    }
    if (-not $python) {
        $checked = ($candidates + @("python3 (PATH)", "python (PATH)")) -join "`n  "
        throw "No Python interpreter found. Checked:`n  $checked`nCreate the repository virtual environment first (docs/development/dev.md)."
    }

    if (-not $Quiet) {
        $version = ((& $python --version) 2>&1 | Select-Object -First 1)
        $sourceRoot = if ($primaryRoot -ne $RepoRoot -and $python -like "$primaryRoot*") {
            "primary checkout ($primaryRoot)"
        } else {
            "this worktree ($RepoRoot)"
        }
        $pythonPath = if ($env:PYTHONPATH) { $env:PYTHONPATH } else { "(unset)" }
        Write-Host "[python]  $python | $version | source: $sourceRoot | PYTHONPATH=$pythonPath" -ForegroundColor DarkGray
    }

    return [pscustomobject]@{
        Python      = $python
        PrimaryRoot = $primaryRoot
        RepoRoot    = $RepoRoot
    }
}
