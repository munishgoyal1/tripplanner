#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Run every trip rule over the local corpus and report what is new.

.DESCRIPTION
  Thin dispatcher over scripts/dev/trip_audit.py using the repository virtual
  environment when one is present. Reads stored trips only: no model calls, no
  provider calls, no writes to any trip.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# A sandbox worktree has no virtual environment of its own; the shared one lives
# in the primary checkout, which the git common directory points at.
$primaryRoot = $repoRoot
$commonDir = & git -C $repoRoot rev-parse --git-common-dir 2>$null
if ($LASTEXITCODE -eq 0 -and $commonDir) {
    $resolved = if ([System.IO.Path]::IsPathRooted($commonDir)) { $commonDir }
                else { Join-Path $repoRoot $commonDir }
    $primaryRoot = Split-Path -Parent (Resolve-Path $resolved).Path
}

if ($repoRoot -ne $primaryRoot) {
    $sourceEnv = Join-Path $primaryRoot ".env"
    if (Test-Path $sourceEnv -PathType Leaf) {
        Copy-Item -LiteralPath $sourceEnv -Destination (Join-Path $repoRoot ".env") -Force
        Write-Host "[env]     refreshed .env from the primary checkout" -ForegroundColor DarkGray
    } else {
        Write-Warning "The primary checkout has no .env; sandbox credentials were not refreshed."
    }
}

$candidates = @(
    (Join-Path $repoRoot ".venv/bin/python"),
    (Join-Path $repoRoot ".venv/Scripts/python.exe"),
    (Join-Path $primaryRoot ".venv/bin/python"),
    (Join-Path $primaryRoot ".venv/Scripts/python.exe")
)
$python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    $python = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    throw "No Python interpreter found. Create the repository virtual environment first."
}

$cli = Join-Path $PSScriptRoot "trip_audit.py"
& $python $cli @Rest
exit $LASTEXITCODE
