<#
.SYNOPSIS
  Run the complete pytest and vitest suites once and classify them against the
  checked-in known-failure baseline.

.DESCRIPTION
  The lane gates (sandbox.ps1, full-2way-sync.ps1) no longer run these suites --
  see config/environments/local.env. This script is where that cost is paid
  instead: deliberately, periodically, on master, in one pass whose output a
  single focused session can work through.

  It never throws on a failing suite. Both halves always run, because "pytest
  broke so we never learned anything about vitest" is exactly the outcome that
  made the old gate useless.

  Exit codes:
    0  no NEW failures (known debt alone is not red, or it would be red forever)
    1  at least one NEW failure
    2  a suite could not run at all

.EXAMPLE
  pwsh scripts/dev/suite-health.ps1
.EXAMPLE
  pwsh scripts/dev/suite-health.ps1 -UpdateBaseline
#>

[CmdletBinding()]
param(
    # Branch to measure. Anything other than the primary checkout's own master
    # is measured in a temporary worktree that is removed afterwards.
    [string]$Ref = "master",
    # Retire fixed entries and record new ones. The only write to the baseline.
    [switch]$UpdateBaseline,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    # Narrow the backend run. For smoke-testing this script itself, not for a
    # real health run -- a partial run would retire baseline entries it never
    # executed, which is why -UpdateBaseline refuses to combine with it.
    [string]$PytestTarget = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/python-runtime.ps1"
. "$PSScriptRoot/lib/node-tools.ps1"

if ($PytestTarget -and $UpdateBaseline) {
    throw "-PytestTarget is a smoke-test switch; it must never rewrite the baseline."
}

Start-RunLog -Name "suite-health" | Out-Null

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$repoRoot = Resolve-PrimaryCheckoutRoot -RepoRoot $scriptRepoRoot
$baseline = Join-Path $scriptRepoRoot "scripts/dev/test-health-baseline.json"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRoot = Join-Path $repoRoot "logs/suite-health/$stamp"
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

function Invoke-Suite {
    <#
    .SYNOPSIS
      Run one suite, capture its output verbatim, and return its exit code.
    .DESCRIPTION
      $ErrorActionPreference is forced to Continue for the duration: piping a
      native command through Tee-Object turns any stderr write into an error
      record under "Stop", so a single warning would abort the whole health run
      before the second suite ever started.
    #>
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Out-Host, not a bare pipeline: anything left on the pipeline becomes
        # part of this function's return value, and the caller wants the exit
        # code alone.
        & $Command 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

# Resolve the tree to measure.
$worktree = $repoRoot
$temporary = ""
$currentBranch = (& git -C $repoRoot branch --show-current).Trim()
if ($Ref -eq "master" -and $currentBranch -eq "master") {
    # A tree mid-merge is a blend of two commits that never existed. Measuring it
    # would file failures against a baseline keyed to real commits, so refuse.
    $unmerged = & git -C $repoRoot diff --name-only --diff-filter=U
    if ($LASTEXITCODE -eq 0 -and $unmerged) {
        throw ("The primary checkout has an unresolved merge (" +
               ($unmerged -join ", ") + "). Finish or abort it before measuring suite health.")
    }
    Write-Host "== syncing master with origin/master ==" -ForegroundColor Cyan
    & git -C $repoRoot fetch -q origin master
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/master." }
    & git -C $repoRoot merge --ff-only origin/master
    if ($LASTEXITCODE -ne 0) { throw "Could not fast-forward master; resolve that first." }
} else {
    $safe = $Ref -replace '[^A-Za-z0-9_.-]', '-'
    $temporary = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-health-$PID-$safe"
    & git -C $repoRoot fetch -q origin
    & git -C $repoRoot worktree add --quiet --detach $temporary $Ref
    if ($LASTEXITCODE -ne 0) { throw "Could not create a worktree for $Ref." }
    $worktree = $temporary
}

$commit = (& git -C $worktree rev-parse --short HEAD).Trim()
Write-Host "Measuring $Ref at $commit" -ForegroundColor Cyan
Write-Host "Report: $outputRoot" -ForegroundColor DarkGray

$arguments = @("--baseline", $baseline, "--out", $outputRoot, "--ref", $Ref, "--commit", $commit)

try {
    # Every gate on, whatever the policy says: this script IS the full run.
    $previousFullSuites = $env:TRIPPLANNER_FULL_SUITES
    $previousPythonPath = $env:PYTHONPATH
    $previousColumns = $env:COLUMNS
    $previousDebugStore = $env:TRIPPLANNER_DEBUG_STORE
    $env:TRIPPLANNER_FULL_SUITES = "1"
    $env:PYTHONPATH = Join-Path $worktree "src"
    $env:TRIPPLANNER_DEBUG_STORE = "0"
    # Start-RunLog uses Start-Transcript, which records console-RENDERED text at
    # the host window width. At a normal width pytest hard-wraps node ids
    # mid-word and the parse silently yields a truncated but plausible id, which
    # would never match its baseline entry again. suite_health.py refuses such
    # output; this is what stops it being produced.
    $env:COLUMNS = "400"

    if (-not $FrontendOnly) {
        Write-Host "== pytest ==" -ForegroundColor Cyan
        $python = (Resolve-TripplannerPython -RepoRoot $worktree).Python
        $junit = Join-Path $outputRoot "pytest-junit.xml"
        $pytestLog = Join-Path $outputRoot "pytest.log"
        $target = if ($PytestTarget) { $PytestTarget } else { "tests" }
        Push-Location $worktree
        try {
            # -n 2, not -n auto: see docs/development/testing.md. -rfE gives the
            # verbatim node ids; --junitxml gives the totals they are checked
            # against. Neither alone is enough.
            $code = Invoke-Suite -LogPath $pytestLog -Command {
                & $python -m pytest $target -q -n 2 -rfE --color=no --junitxml=$junit
            }
            Write-Host "pytest exit code: $code" -ForegroundColor DarkGray
        } finally {
            Pop-Location
        }
        $arguments += @("--pytest-junit", $junit, "--pytest-log", $pytestLog)
    }

    if (-not $BackendOnly) {
        Write-Host "== vitest ==" -ForegroundColor Cyan
        $frontend = Join-Path $worktree "frontend"
        Use-CompatibleNode
        Push-Location $frontend
        try {
            if (-not (Test-Path (Join-Path $frontend "node_modules") -PathType Container)) {
                & npm install --no-audit --no-fund
            }
            $vitestJson = Join-Path $outputRoot "vitest.json"
            $vitestLog = Join-Path $outputRoot "vitest.log"
            $code = Invoke-Suite -LogPath $vitestLog -Command {
                & npx vitest run --reporter=default --reporter=json --outputFile.json=$vitestJson
            }
            Write-Host "vitest exit code: $code" -ForegroundColor DarkGray
        } finally {
            Pop-Location
        }
        $arguments += @("--vitest-json", $vitestJson)
    }

    if ($UpdateBaseline) { $arguments += "--update-baseline" }

    Write-Host "== classifying against the baseline ==" -ForegroundColor Cyan
    $python = (Resolve-TripplannerPython -RepoRoot $worktree).Python
    & $python (Join-Path $PSScriptRoot "suite_health.py") @arguments
    $classifyExit = $LASTEXITCODE

    # A stable pointer at the newest report, mirroring logs/audit/latest.json.
    Copy-Item (Join-Path $outputRoot "report.json") (Join-Path $repoRoot "logs/suite-health/latest.json") -Force

    switch ($classifyExit) {
        0 { Write-Host "No NEW failures." -ForegroundColor Green }
        1 { Write-Host "NEW failures found. See $outputRoot/report.md" -ForegroundColor Red }
        default { Write-Host "A suite could not run. See $outputRoot/report.md" -ForegroundColor Red }
    }
    exit $classifyExit
} finally {
    $env:TRIPPLANNER_FULL_SUITES = $previousFullSuites
    $env:PYTHONPATH = $previousPythonPath
    $env:COLUMNS = $previousColumns
    $env:TRIPPLANNER_DEBUG_STORE = $previousDebugStore
    if ($temporary) {
        & git -C $repoRoot worktree remove --force $temporary 2>$null
    }
    Stop-RunLog
}
