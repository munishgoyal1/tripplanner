#!/usr/bin/env pwsh
# Shared "last run" logging. Every entry-point script overwrites one transcript in
# <primary-root>/logs/last-run so any lane, worker, or sandbox can read the latest
# run of any script. Dot-source: . "$PSScriptRoot/lib/run-log.ps1".

function Get-PrimaryRepoRoot {
    # Worktrees keep their own logs/ and no .env.*; runs share the primary checkout's copies.
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $common = & git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($common)) {
            return Split-Path -Parent (@($common)[0])
        }
    }
    # scripts/dev/lib -> scripts/dev -> scripts -> repo root
    return Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Get-RunLogDirectory {
    $dir = Join-Path (Get-PrimaryRepoRoot) "logs/last-run"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Add-RunLogIndex {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Outcome
    )
    try {
        $line = "{0}`t{1}`t{2}`t{3}" -f `
            ((Get-Date).ToUniversalTime().ToString("u")), $Name, $Outcome, (Get-Location).Path
        Add-Content -Path (Join-Path (Get-RunLogDirectory) "runs.log") -Value $line
    } catch {
        # Logging must never break a run.
    }
}

function Start-RunLog {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($global:TripplannerRunLog) {
        return $null   # a nested script keeps writing to the outer transcript
    }
    $path = Join-Path (Get-RunLogDirectory) "$Name.log"
    try {
        Start-Transcript -Path $path -Force -ErrorAction Stop | Out-Null
    } catch {
        Write-Warning "Could not start the run log at ${path}: $($_.Exception.Message)"
        return $null
    }
    $global:TripplannerRunLog = [pscustomobject]@{ Name = $Name; Path = $path }
    $here = (Get-Location).Path
    $branch = & git -C $here branch --show-current 2>$null
    $head = & git -C $here rev-parse --short HEAD 2>$null
    Write-Host "[log]     $path"
    Write-Host "[run]     $Name | $here | $branch@$head | $env:USERNAME"
    Add-RunLogIndex -Name $Name -Outcome "started"
    return $path
}

function Stop-RunLog {
    param([string]$Outcome = "completed")

    $log = $global:TripplannerRunLog
    if (-not $log) { return }
    Add-RunLogIndex -Name $log.Name -Outcome $Outcome
    try { Stop-Transcript | Out-Null } catch { }
    $global:TripplannerRunLog = $null
}
