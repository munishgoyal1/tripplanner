#!/usr/bin/env pwsh
# Shared helpers for the worktree synchronization scripts.
# Provides run logging (transcript + append-only index) and a non-interactive
# merge-conflict flow that records a resumable pending state instead of blocking
# on an interactive prompt. Dot-source this file: . "$PSScriptRoot/lib/sync-common.ps1".

$MarkerPattern = "^(<<<<<<< |\|\|\|\|\|\|\| |=======$|>>>>>>> )"

function Get-SyncPaths {
    $common = & git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>$null
    if ($LASTEXITCODE -eq 0 -and $common) {
        $primaryRoot = Split-Path -Parent (@($common)[0])
    } else {
        # scripts/dev/lib -> scripts/dev -> scripts -> repo root
        $primaryRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    }
    $logDir = Join-Path $primaryRoot "logs/sync"
    [pscustomobject]@{
        PrimaryRoot = $primaryRoot
        LogDir      = $logDir
        PendingFile = Join-Path $logDir "pending-merge.json"
        RunsIndex   = Join-Path $logDir "runs.log"
    }
}

function Add-SyncRunIndex {
    param(
        [Parameter(Mandatory = $true)][string]$Component,
        [Parameter(Mandatory = $true)][string]$Outcome,
        [string]$LogPath = ""
    )
    try {
        $paths = Get-SyncPaths
        New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
        $line = "{0}`t{1}`t{2}`t{3}" -f ((Get-Date).ToUniversalTime().ToString("u")), $Component, $Outcome, $LogPath
        Add-Content -Path $paths.RunsIndex -Value $line
    } catch {
        # Logging must never break a sync run.
    }
}

function Write-SyncLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("Info", "Warn", "Error")][string]$Level = "Info"
    )
    $line = "[{0}] [{1}] {2}" -f ((Get-Date).ToUniversalTime().ToString("u")), $Level.ToUpper(), $Message
    switch ($Level) {
        "Warn" { Write-Host $line -ForegroundColor Yellow }
        "Error" { Write-Host $line -ForegroundColor Red }
        default { Write-Host $line -ForegroundColor DarkGray }
    }
    $log = $global:TripplannerSyncLog
    if ($log -and -not $log.Transcript -and $log.Path) {
        try { Add-Content -Path $log.Path -Value $line } catch { }
    }
}

function Start-SyncLog {
    param([Parameter(Mandatory = $true)][string]$Component)
    if ($global:TripplannerSyncLog) {
        return $false
    }
    $global:TripplannerSyncPending = $false
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $logPath = Join-Path $paths.LogDir ("{0}-{1}.log" -f $Component, $stamp)
    $transcript = $false
    try {
        Start-Transcript -Path $logPath -Append -ErrorAction Stop | Out-Null
        $transcript = $true
    } catch {
        Set-Content -Path $logPath -Value ("[{0}] [INFO] Transcript unavailable; milestone logging only." -f ((Get-Date).ToUniversalTime().ToString("u")))
    }
    $global:TripplannerSyncLog = [pscustomobject]@{
        Path = $logPath; Component = $Component; Transcript = $transcript
    }
    Add-SyncRunIndex -Component $Component -Outcome "started" -LogPath $logPath
    Write-SyncLog "Sync log started for $Component -> $logPath"
    return $true
}

function Stop-SyncLog {
    param([string]$Outcome = "completed")
    $log = $global:TripplannerSyncLog
    if (-not $log) {
        return
    }
    Write-SyncLog "Sync log $Outcome for $($log.Component)"
    Add-SyncRunIndex -Component $log.Component -Outcome $Outcome -LogPath $log.Path
    if ($log.Transcript) {
        try { Stop-Transcript | Out-Null } catch { }
    }
    $global:TripplannerSyncLog = $null
}

function Invoke-SyncGit {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $output = & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed in $WorkingDirectory."
    }
    return $output
}

function Get-FilesWithConflictMarkers {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [string[]]$Files
    )
    if (-not $Files -or $Files.Count -eq 0) {
        return @()
    }
    $hits = & git -C $WorkingDirectory grep -l -E $MarkerPattern -- @Files 2>$null
    if ($LASTEXITCODE -eq 0) {
        return @($hits)
    }
    return @()
}

function Get-PendingMerges {
    $paths = Get-SyncPaths
    if (-not (Test-Path $paths.PendingFile)) {
        return @()
    }
    try {
        $data = Get-Content -Raw -Path $paths.PendingFile | ConvertFrom-Json
        if ($data -and $data.pending) {
            return @($data.pending)
        }
    } catch {
        Write-SyncLog -Level Warn "Could not read pending merge state: $($_.Exception.Message)"
    }
    return @()
}

function Save-PendingList {
    param([object[]]$Entries)
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    if (-not $Entries -or $Entries.Count -eq 0) {
        if (Test-Path $paths.PendingFile) {
            Remove-Item -Force -Path $paths.PendingFile
        }
        return
    }
    [pscustomobject]@{ pending = @($Entries) } |
        ConvertTo-Json -Depth 6 |
        Set-Content -Path $paths.PendingFile
}

function Save-PendingMerge {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("integration", "lane")][string]$Kind,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [string]$Branch = "",
        [string]$SourceHead = "",
        [string]$StashCommit = "",
        [Parameter(Mandatory = $true)][string[]]$ConflictedFiles
    )
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $reportPath = Join-Path $paths.LogDir ("conflict-{0}-{1}.md" -f $Kind, $stamp)

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# Sync merge conflict — needs a semantic decision")
    $lines.Add("")
    $lines.Add("- Recorded (UTC): $((Get-Date).ToUniversalTime().ToString('u'))")
    $lines.Add("- Kind: $Kind")
    $lines.Add("- Label: $Label")
    if ($Branch) { $lines.Add("- Target branch: $Branch") }
    if ($SourceHead) { $lines.Add("- Source head: $SourceHead") }
    $lines.Add("- Working directory: $WorkingDirectory")
    $lines.Add("- Resume after resolving: pwsh -File scripts/dev/resume-merge.ps1")
    $lines.Add("")
    $lines.Add("## Conflicted files")
    foreach ($file in $ConflictedFiles) { $lines.Add("- $file") }
    $lines.Add("")
    foreach ($file in $ConflictedFiles) {
        $lines.Add("### $file")
        $lines.Add('```diff')
        $diff = & git -C $WorkingDirectory diff -- $file 2>&1
        foreach ($diffLine in $diff) { $lines.Add([string]$diffLine) }
        $lines.Add('```')
        $lines.Add("")
    }
    Set-Content -Path $reportPath -Value ($lines -join [Environment]::NewLine)

    $entry = [pscustomobject]@{
        kind             = $Kind
        label            = $Label
        branch           = $Branch
        sourceHead       = $SourceHead
        workingDirectory = $WorkingDirectory
        stashCommit      = $StashCommit
        conflictedFiles  = @($ConflictedFiles)
        reportPath       = $reportPath
        createdUtc       = (Get-Date).ToUniversalTime().ToString("u")
        resumeCommand    = "pwsh -File scripts/dev/resume-merge.ps1"
    }
    $list = @(Get-PendingMerges) + $entry
    Save-PendingList -Entries $list
    return $entry
}

function Complete-MergeConflict {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][ValidateSet("integration", "lane")][string]$Kind,
        [string]$Branch = "",
        [string]$SourceHead = "",
        [string]$StashCommit = ""
    )
    & git -C $WorkingDirectory rerere 2>&1 | Out-Host
    $remaining = @(Invoke-SyncGit -WorkingDirectory $WorkingDirectory -Arguments @(
            "diff", "--name-only", "--diff-filter=U"
        ))
    if ($remaining.Count -eq 0) {
        Invoke-SyncGit -WorkingDirectory $WorkingDirectory -Arguments @("commit", "--no-edit") | Out-Null
        Write-SyncLog "Reused a recorded conflict resolution for $Label."
        return
    }

    $entry = Save-PendingMerge -Kind $Kind -WorkingDirectory $WorkingDirectory -Label $Label `
        -Branch $Branch -SourceHead $SourceHead -StashCommit $StashCommit -ConflictedFiles $remaining
    $global:TripplannerSyncPending = $true
    Write-SyncLog -Level Warn "$Label has conflicts needing a semantic decision: $($remaining -join ', ')"
    Write-SyncLog -Level Warn "Conflict report: $($entry.reportPath)"
    throw "SYNC_CONFLICT_PENDING: $Label. Resolve the files under '$WorkingDirectory', then run 'pwsh -File scripts/dev/resume-merge.ps1'. Details: $($entry.reportPath)"
}

function Restore-LaneStash {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$StashCommit
    )
    $currentStash = & git -C $WorkingDirectory rev-parse --quiet --verify refs/stash 2>$null
    if ($LASTEXITCODE -ne 0 -or $currentStash -ne $StashCommit) {
        Write-SyncLog -Level Warn "$Label safety stash is not the newest stash; leaving it untouched."
        return
    }
    Write-SyncLog "Restoring uncommitted $Label changes from the safety stash..."
    & git -C $WorkingDirectory stash pop --index "stash@{0}"
    if ($LASTEXITCODE -eq 0) {
        return
    }
    $marked = @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
    Write-SyncLog -Level Warn "$Label local changes conflict with the new base; the safety stash was retained. Resolve: $($marked -join ', ')"
}
