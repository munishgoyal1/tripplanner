#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Generate corpus trips with the real planner, inside a budget.

.DESCRIPTION
  Thin dispatcher over scripts/dev/build_corpus.py using the repository virtual
  environment when one is present.

  This spends real money: it sends planning requests to a running sandbox API,
  which calls the model and the place providers. Spend is capped per run and
  cumulatively, and recorded in corpus/spend-ledger.json. A finished run also
  saves the place grounding it warmed into corpus/places.json.

    Pass --country india to cover trips within India. Pass --market india to cover
    Indian travelers, alternating domestic and outbound scenarios even in a small
    run. Choose only one of --country or --market per run. Both use reviewable
    destination-specific durations and visitor profiles.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Publish-GeneratedCorpus {
    $paths = @(
        "corpus/manifest.json",
        "corpus/spend-ledger.json",
        "corpus/places.json",
        "corpus/trips"
    )
    $changed = @(& git -C $repoRoot status --porcelain -- @paths)
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect generated corpus files." }
    if ($changed.Count -eq 0) {
        Write-Host "Corpus artifacts are already committed."
        return
    }

    $branch = (& git -C $repoRoot branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $branch) {
        throw "Cannot publish generated corpus from a detached HEAD."
    }
    & git -C $repoRoot add -- @paths
    if ($LASTEXITCODE -ne 0) { throw "Could not stage generated corpus files." }
    & git -C $repoRoot commit -m "Preserve generated corpus" -- @paths
    if ($LASTEXITCODE -ne 0) { throw "Could not commit generated corpus files." }
    & git -C $repoRoot push origin "HEAD:$branch"
    if ($LASTEXITCODE -ne 0) { throw "Could not push generated corpus commit to origin/$branch." }
    Write-Host "Published generated corpus to origin/$branch." -ForegroundColor Green
}

# A sandbox worktree has no virtual environment of its own; the shared one lives
# in the primary checkout, which the git common directory points at.
$primaryRoot = $repoRoot
$commonDir = & git -C $repoRoot rev-parse --git-common-dir 2>$null
if ($LASTEXITCODE -eq 0 -and $commonDir) {
    $resolved = if ([System.IO.Path]::IsPathRooted($commonDir)) { $commonDir }
                else { Join-Path $repoRoot $commonDir }
    $primaryRoot = Split-Path -Parent (Resolve-Path $resolved).Path
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

$cli = Join-Path $PSScriptRoot "build_corpus.py"
# -u so a run that streams through this dispatcher for hours is never buffered.
& $python -u $cli @Rest
$buildExit = $LASTEXITCODE
$dryRun = @($Rest | Where-Object { $_ -eq "--dry-run" }).Count -gt 0
if (-not $dryRun) {
    Publish-GeneratedCorpus
}
exit $buildExit
