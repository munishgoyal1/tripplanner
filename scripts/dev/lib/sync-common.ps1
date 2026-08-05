#!/usr/bin/env pwsh
# Shared helpers for the worktree synchronization scripts.
# Provides run logging (transcript + append-only index) and a non-interactive
# merge-conflict flow that records a resumable pending state instead of blocking
# on an interactive prompt. Dot-source this file: . "$PSScriptRoot/lib/sync-common.ps1".

$MarkerPattern = "^(<<<<<<< |\|\|\|\|\|\|\| |=======$|>>>>>>> )"

. "$PSScriptRoot/run-log.ps1"

function Get-SyncPaths {
    $primaryRoot = Get-PrimaryRepoRoot
    $logDir = Join-Path $primaryRoot "logs/sync"
    [pscustomobject]@{
        PrimaryRoot = $primaryRoot
        LogDir      = $logDir
        PendingFile = Join-Path $logDir "pending-merge.json"
        RunsIndex   = Join-Path $primaryRoot "logs/last-run/runs.log"
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
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $paths.RunsIndex) | Out-Null
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
        "Error" {
            $global:TripplannerSyncFailed = $true
            Write-Host $line -ForegroundColor Red
        }
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
    $global:TripplannerSyncValidationFailed = $false
    $global:TripplannerSyncFailed = $false
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    # Keep the two previous runs beside the current one; a sync failure is usually
    # only explainable by comparing it against the run before it.
    $logPath = Join-Path (Get-RunLogDirectory) "$Component.log"
    Backup-RunLog -Path $logPath
    $transcript = $false
    try {
        Start-Transcript -Path $logPath -Force -ErrorAction Stop | Out-Null
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
    param([string]$Outcome = "")
    $log = $global:TripplannerSyncLog
    if (-not $log) {
        return
    }
    if (-not $Outcome) {
        $Outcome = if ($global:TripplannerSyncFailed -or $global:TripplannerSyncPending -or
            $global:TripplannerSyncValidationFailed) { "failed" } else { "completed" }
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
        [Parameter(Mandatory = $true)][ValidateSet("integration", "lane", "stash")][string]$Kind,
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
    $list = @(
        Get-PendingMerges |
            Where-Object { ([string]$_.workingDirectory).TrimEnd("\") -ne $WorkingDirectory.TrimEnd("\") }
    ) + $entry
    Save-PendingList -Entries $list
    return $entry
}

function Get-SafetyStashCommit {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Branch
    )
    $suffix = "update-from-master temporary " + $(if ($Branch -eq "master") { "MasterAgent (0) changes" } else {
        "Agent $($Branch -replace '^agents/worker-', '') changes"
    })
    foreach ($line in @(& git -C $WorkingDirectory stash list --format="%H`t%gs" 2>$null)) {
        $parts = $line -split "`t", 2
        if ($parts.Count -eq 2 -and $parts[1].EndsWith($suffix)) { return $parts[0] }
    }
    return ""
}

function Remove-SafetyStash {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$StashCommit
    )
    foreach ($line in @(& git -C $WorkingDirectory stash list --format="%gd`t%H" 2>$null)) {
        $parts = $line -split "`t", 2
        if ($parts.Count -eq 2 -and $parts[1] -eq $StashCommit) {
            Invoke-SyncGit -WorkingDirectory $WorkingDirectory -Arguments @("stash", "drop", $parts[0]) | Out-Null
            return
        }
    }
    Write-SyncLog -Level Warn "Safety stash $($StashCommit.Substring(0, 7)) was already absent; continuing."
}

function Register-OrphanedLaneConflicts {
    # Git's index is authoritative if pending-merge.json was absent or stale.
    $paths = Get-SyncPaths
    $known = @(Get-PendingMerges)
    $roots = @($paths.PrimaryRoot) + @(1..3 | ForEach-Object { "$($paths.PrimaryRoot).worktrees\worker-$_" })
    foreach ($wd in $roots) {
        if (-not (Test-Path $wd -PathType Container)) { continue }
        $unmerged = @(& git -C $wd diff --name-only --diff-filter=U 2>$null)
        if ($unmerged.Count -eq 0) { continue }
        if ($known | Where-Object { ([string]$_.workingDirectory).TrimEnd("\") -eq $wd.TrimEnd("\") }) { continue }

        $branch = [string](@(& git -C $wd branch --show-current 2>$null)[0])
        if ([string]::IsNullOrWhiteSpace($branch)) { continue }
        $label = if ($branch -eq "master") { "MasterAgent (0)" } else {
            "Agent $($branch -replace '^agents/worker-', '')"
        }
        $mergeHead = [string](@(& git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null)[0])
        $kind = if ($mergeHead) { "lane" } else { "stash" }
        $stashCommit = Get-SafetyStashCommit -WorkingDirectory $wd -Branch $branch
        $entry = Save-PendingMerge -Kind $kind -WorkingDirectory $wd -Label $label -Branch $branch `
            -SourceHead $mergeHead -StashCommit $stashCommit -ConflictedFiles $unmerged
        $known += $entry
        Write-SyncLog -Level Warn "Recovered unrecorded $kind conflict for ${label}: $($unmerged -join ', ')"
    }
}

function Complete-MergeConflict {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][ValidateSet("integration", "lane", "stash")][string]$Kind,
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
    throw "SYNC_CONFLICT_PENDING: $Label. Automatic resolution runs next; if it cannot finish, resolve the files under '$WorkingDirectory' and run 'pwsh -File scripts/dev/resume-merge.ps1'. Details: $($entry.reportPath)"
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

function Save-ValidationReport {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string[]]$Failures
    )
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $reportPath = Join-Path $paths.LogDir ("validation-{0}.md" -f $stamp)
    $lines = @(
        "# Sync validation failed",
        "",
        "- When (UTC): $((Get-Date).ToUniversalTime().ToString('u'))",
        "- Merged tree: $WorkingDirectory",
        "",
        "## Failing checks",
        ""
    )
    foreach ($failure in $Failures) { $lines += "- $failure" }
    $lines += @(
        "",
        "The integrated result was NOT published; master is unchanged. Fix the",
        "merged tree above (or the offending commit), then re-run the sync. The",
        "integration worktree was preserved for inspection."
    )
    Set-Content -Path $reportPath -Value $lines -Encoding UTF8
    return $reportPath
}

function Get-PytestFailureIds {
    param([AllowEmptyCollection()][AllowEmptyString()][string[]]$Lines = @())
    $ids = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $Lines) {
        if ($line -match '^\s*(?:FAILED|ERROR)\s+(\S+)') {
            [void]$ids.Add($Matches[1])
        }
    }
    return @($ids | Select-Object -Unique)
}

function Get-ValidationBaseline {
    # Returns the recorded set of known-failing pytest node ids, or $null when no
    # baseline exists yet (the first run seeds it and does not block). A green
    # baseline is an EMPTY set, not $null: returning it bare would unroll to $null
    # and make every clean run look like a first run, silently absorbing the next
    # real regression as "pre-existing".
    $path = Join-Path (Get-SyncPaths).LogDir "validation-baseline.json"
    if (-not (Test-Path $path)) { return $null }
    try {
        $data = Get-Content $path -Raw | ConvertFrom-Json
        $ids = @($data.failures | Where-Object { $_ })
        return , $ids
    } catch {
        return , @()
    }
}

function Set-ValidationBaseline {
    param([string[]]$Ids)
    $paths = Get-SyncPaths
    New-Item -ItemType Directory -Force -Path $paths.LogDir | Out-Null
    $path = Join-Path $paths.LogDir "validation-baseline.json"
    $payload = [pscustomobject]@{
        updatedUtc = (Get-Date).ToUniversalTime().ToString("u")
        failures   = @($Ids | Select-Object -Unique)
    }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -Path $path -Encoding UTF8
}

function Copy-LocalConfigForValidation {
    # A merge worktree is a fresh checkout, so git-ignored local configuration is
    # absent. Settings-dependent tests then fail for reasons that have nothing to
    # do with the merge, and at the gate that is indistinguishable from a real
    # regression: it blocks the merge and poisons the baseline with phantom ids.
    # Seed the worktree from the primary checkout so the gate measures the merge.
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$PrimaryRoot
    )

    foreach ($name in @(".env")) {
        $source = Join-Path $PrimaryRoot $name
        $target = Join-Path $WorkingDirectory $name
        if ((Test-Path $source -PathType Leaf) -and -not (Test-Path $target)) {
            Copy-Item -Path $source -Destination $target -Force
            Write-SyncLog "Seeded $name into the merge worktree so validation matches the primary checkout."
        }
    }
}

function Invoke-IntegrationValidation {
    # Verifies a merged tree BEFORE it is published to master so a clean-but-broken
    # merge cannot become the base everyone builds on. Dependencies are reused from
    # the primary worktree (frontend node_modules via a junction; the primary .venv
    # for Python) with PYTHONPATH pointed at the merged src, so nothing is
    # reinstalled. Frontend vitest is a HARD gate (it is hermetic). Python is a
    # REGRESSION gate: it blocks only on failures that are NEW versus a
    # self-updating baseline, so pre-existing environmental/date-dependent failures
    # never block a merge. A check whose toolchain is absent is skipped, not failed.
    # Set TRIPPLANNER_SKIP_SYNC_VALIDATION=1 to bypass entirely.
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$PrimaryRoot
    )

    if ($env:TRIPPLANNER_SKIP_SYNC_VALIDATION) {
        Write-SyncLog -Level Warn "Validation skipped (TRIPPLANNER_SKIP_SYNC_VALIDATION set); the merged code was NOT verified."
        return $true
    }

    Copy-LocalConfigForValidation -WorkingDirectory $WorkingDirectory -PrimaryRoot $PrimaryRoot

    Write-SyncLog "Validating the merged tree before publishing to master..."
    $blocking = [System.Collections.Generic.List[string]]::new()

    # Python unit suite: regression gate against a self-updating baseline.
    $pytestDir = Join-Path $WorkingDirectory "tests"
    $python = Join-Path $PrimaryRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path $python)) {
        $onPath = Get-Command python -ErrorAction SilentlyContinue
        $python = if ($onPath) { $onPath.Source } else { $null }
    }
    if ((Test-Path $pytestDir -PathType Container) -and $python) {
        & $python -c "import pytest, pydantic" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-SyncLog "Running pytest on the merged tree..."
            $priorPythonPath = $env:PYTHONPATH
            $env:PYTHONPATH = (Join-Path $WorkingDirectory "src")
            Push-Location $WorkingDirectory
            try {
                $pytestOutput = & $python -m pytest -q 2>&1
                $code = $LASTEXITCODE
            } finally {
                Pop-Location
                $env:PYTHONPATH = $priorPythonPath
            }
            $pytestOutput | Out-Host
            $current = @(Get-PytestFailureIds -Lines @($pytestOutput | ForEach-Object { [string]$_ }))
            if ($code -notin @(0, 5) -and $current.Count -eq 0) {
                $current = @("pytest:run-error(exit $code)")
            }
            $baseline = Get-ValidationBaseline
            if ($null -eq $baseline) {
                Set-ValidationBaseline -Ids $current
                if ($current.Count -gt 0) {
                    Write-SyncLog -Level Warn "Python baseline established with $($current.Count) pre-existing failure(s); these won't block merges. Fix them to tighten the gate: $($current -join ', ')"
                } else {
                    Write-SyncLog "pytest passed (clean baseline established)."
                }
            } else {
                $new = @($current | Where-Object { $_ -notin $baseline })
                if ($new.Count -gt 0) {
                    foreach ($id in $new) { $blocking.Add("pytest regression: $id") }
                } else {
                    Set-ValidationBaseline -Ids $current
                    if ($current.Count -gt 0) {
                        Write-SyncLog -Level Warn "$($current.Count) known pre-existing Python failure(s) ignored via baseline."
                    } else {
                        Write-SyncLog "pytest passed; no regressions."
                    }
                }
            }
        } else {
            Write-SyncLog -Level Warn "Skipping pytest: $python lacks test dependencies (import pytest/pydantic failed)."
        }
    }

    # Frontend unit suite (vitest on jsdom): hard gate, it is hermetic.
    $frontendDir = Join-Path $WorkingDirectory "frontend"
    if ((Test-Path (Join-Path $frontendDir "package.json")) -and
        (Get-Command npm -ErrorAction SilentlyContinue)) {
        $primaryModules = Join-Path $PrimaryRoot "frontend/node_modules"
        $mergedModules = Join-Path $frontendDir "node_modules"
        $linkedModules = $false
        if ((Test-Path $primaryModules -PathType Container) -and -not (Test-Path $mergedModules)) {
            New-Item -ItemType Junction -Path $mergedModules -Target $primaryModules -ErrorAction SilentlyContinue | Out-Null
            $linkedModules = Test-Path $mergedModules
        }
        if (Test-Path $mergedModules) {
            Write-SyncLog "Running frontend vitest on the merged tree..."
            try {
                & npm --prefix $frontendDir run test 2>&1 | Out-Host
                $code = $LASTEXITCODE
            } finally {
                if ($linkedModules) {
                    # Remove only the junction link; never recurse into the primary's modules.
                    & cmd /c rmdir "$mergedModules" 2>$null
                }
            }
            if ($code -ne 0) {
                $blocking.Add("frontend vitest (exit $code)")
            } else {
                Write-SyncLog "Frontend vitest passed."
            }
        } else {
            Write-SyncLog -Level Warn "Skipping frontend tests: node_modules was unavailable to link."
        }
    }

    if ($blocking.Count -gt 0) {
        $report = Save-ValidationReport -WorkingDirectory $WorkingDirectory -Failures @($blocking)
        $global:TripplannerSyncValidationFailed = $true
        Write-SyncLog -Level Error "Validation failed: $($blocking -join '; '). Report: $report"
        return $false
    }
    Write-SyncLog "Validation passed; the merged tree is safe to publish."
    return $true
}

function Complete-PendingMerges {
    # Finishes every merge recorded as pending once its conflicted files are
    # marker-free. Returns how many are still pending and whether an integration
    # merge completed (so callers can propagate the new master into every lane).
    param([switch]$KeepIntegrationWorktree)

    $paths = Get-SyncPaths
    $pending = @(Get-PendingMerges)
    if ($pending.Count -eq 0) {
        return [pscustomobject]@{ StillPending = 0; IntegrationCompleted = $false }
    }

    Write-SyncLog "Finishing $($pending.Count) pending merge(s)..."
    $stillPending = [System.Collections.Generic.List[object]]::new()
    $integrationCompleted = $false

    foreach ($entry in $pending) {
        $wd = [string]$entry.workingDirectory
        Write-SyncLog "Resuming $($entry.kind) merge for $($entry.label) in $wd"

        if (-not (Test-Path $wd -PathType Container)) {
            Write-SyncLog -Level Error "Working directory is missing: $wd. Dropping this entry."
            continue
        }

        & git -C $wd rev-parse --git-dir 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog -Level Error "$wd is no longer a git worktree (removed?). Dropping this entry."
            continue
        }

        $marked = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($entry.conflictedFiles))
        if ($marked.Count -gt 0) {
            Write-SyncLog -Level Error "Conflict markers still present in: $($marked -join ', '). Resolve them, then re-run."
            $stillPending.Add($entry)
            continue
        }

        if ($entry.kind -eq "stash") {
            Invoke-SyncGit -WorkingDirectory $wd -Arguments (@("add", "--") + @($entry.conflictedFiles)) | Out-Null
            $unresolved = @(Invoke-SyncGit -WorkingDirectory $wd -Arguments @("diff", "--name-only", "--diff-filter=U"))
            if ($unresolved.Count -gt 0) {
                Write-SyncLog -Level Error "Stash restore is still unresolved: $($unresolved -join ', ')."
                $stillPending.Add($entry)
                continue
            }
            if ($entry.stashCommit) {
                Remove-SafetyStash -WorkingDirectory $wd -StashCommit ([string]$entry.stashCommit)
            }
            Invoke-SyncGit -WorkingDirectory $wd -Arguments (@("reset", "--") + @($entry.conflictedFiles)) | Out-Null
            Write-SyncLog "Restored local changes for $($entry.label); no commit or push was created."
            continue
        }

        & git -C $wd rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
        $midMerge = ($LASTEXITCODE -eq 0)
        if ($midMerge) {
            & git -C $wd rerere 2>&1 | Out-Host
            Invoke-SyncGit -WorkingDirectory $wd -Arguments (@("add", "--") + @($entry.conflictedFiles)) | Out-Null
            $unresolved = @(Invoke-SyncGit -WorkingDirectory $wd -Arguments @("diff", "--name-only", "--diff-filter=U"))
            if ($unresolved.Count -gt 0) {
                Write-SyncLog -Level Error "Still unresolved after staging: $($unresolved -join ', ')."
                $stillPending.Add($entry)
                continue
            }
            # --check also flags benign whitespace nits; only leftover markers may block the merge.
            $checkOutput = @(& git -C $wd diff --cached --check 2>&1)
            $leftoverMarkers = @($checkOutput | Where-Object { $_ -match "conflict marker" })
            if ($leftoverMarkers.Count -gt 0) {
                Write-SyncLog -Level Error "Leftover conflict markers staged: $($leftoverMarkers -join '; ')"
                $stillPending.Add($entry)
                continue
            }
            if ($checkOutput.Count -gt 0) {
                Write-SyncLog -Level Warn "Whitespace nits in the merged result (not blocking): $($checkOutput.Count) line(s)."
            }
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("commit", "--no-edit") | Out-Null
            Write-SyncLog "Committed the resolved merge for $($entry.label)."
        } else {
            Write-SyncLog "No merge in progress in $wd; assuming the resolution was already committed."
        }

        if ($entry.kind -eq "integration") {
            if (-not (Invoke-IntegrationValidation -WorkingDirectory $wd -PrimaryRoot $paths.PrimaryRoot)) {
                Write-SyncLog -Level Error "Not publishing $($entry.label): the merged tree failed validation. Kept pending."
                $stillPending.Add($entry)
                continue
            }
            $resultHead = Invoke-SyncGit -WorkingDirectory $wd -Arguments @("rev-parse", "HEAD")
            Write-SyncLog "Pushing integrated result $($resultHead.Substring(0, 7)) to master..."
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("push", "origin", "${resultHead}:refs/heads/master") | Out-Null

            if (-not $KeepIntegrationWorktree) {
                & git -C $paths.PrimaryRoot worktree remove --force $wd 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-SyncLog -Level Warn "Could not remove temporary integration worktree: $wd"
                }
            }

            try {
                Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("fetch", "origin") | Out-Null
                $primaryBranch = Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("branch", "--show-current")
                if ($primaryBranch -eq "master") {
                    Invoke-SyncGit -WorkingDirectory $paths.PrimaryRoot -Arguments @("merge", "origin/master", "--ff-only") | Out-Null
                    Write-SyncLog "Fast-forwarded primary master to the integrated result."
                }
            } catch {
                Write-SyncLog -Level Warn "Primary fast-forward skipped: $($_.Exception.Message)"
            }
            $integrationCompleted = $true
        } else {
            $branch = [string]$entry.branch
            Invoke-SyncGit -WorkingDirectory $wd -Arguments @("push", "-u", "origin", "HEAD:refs/heads/$branch") | Out-Null
            Write-SyncLog "Pushed $($entry.label) to $branch."
            if ($entry.stashCommit) {
                Restore-LaneStash -WorkingDirectory $wd -Label $entry.label -StashCommit ([string]$entry.stashCommit)
            }
        }

        Write-SyncLog "Resolved pending merge for $($entry.label)."
    }

    Save-PendingList -Entries @($stillPending)
    return [pscustomobject]@{
        StillPending         = $stillPending.Count
        IntegrationCompleted = $integrationCompleted
    }
}

function Invoke-PendingMergeHeal {
    # Called at the start of a sync run: if a prior run left resolved-but-unfinished
    # merges, finish them in-flow so no separate resume step or re-run is needed.
    # Throws only when files still carry conflict markers (a real semantic decision).
    Register-OrphanedLaneConflicts
    $pending = @(Get-PendingMerges)
    if ($pending.Count -eq 0) {
        return
    }
    Write-SyncLog "Detected $($pending.Count) pending merge(s); finishing before synchronizing..."
    $healed = Complete-PendingMerges
    if ($healed.StillPending -gt 0) {
        throw "SYNC_PENDING: $($healed.StillPending) merge(s) still need attention (unresolved conflict markers or a failed validation gate). See the reports above; the next sync retries automatically once they are fixed."
    }
    Write-SyncLog "All previously pending merges finished."
}

function Invoke-LanePropagation {
    # Pushes the freshly integrated master into every worktree so the run ends
    # with all lanes current. Resilient: a novel per-lane conflict is recorded and
    # reported without stopping the other lanes.
    param([Parameter(Mandatory = $true)][string]$ScriptRoot)

    Write-SyncLog "Propagating integrated master into every worktree..."
    $laneNames = @{ 0 = "MasterAgent (0)"; 1 = "Agent 1"; 2 = "Agent 2"; 3 = "Agent 3 - Infra" }
    $failures = 0
    foreach ($number in 0, 1, 2, 3) {
        try {
            & "$ScriptRoot\update-from-master.ps1" $number
        } catch {
            $failures++
            Write-SyncLog -Level Warn "$($laneNames[$number]) needs attention: $($_.Exception.Message)"
        }
    }
    if ($failures -gt 0) {
        throw "$failures worktree(s) still need resolution; resolve the files listed above, then re-run."
    }
    Write-SyncLog "Every worktree is current."
}

function Resolve-CopilotCli {
    # Returns the Copilot CLI path, or $null when it is not installed. Callers that
    # resolve automatically must degrade quietly; only the manual entry point throws.
    param([string]$Override)

    if ($Override) {
        if (-not (Test-Path $Override)) { throw "Copilot CLI not found at: $Override" }
        return $Override
    }
    if ($env:COPILOT_CLI -and (Test-Path $env:COPILOT_CLI)) { return $env:COPILOT_CLI }
    # Prefer the npm global install; the VS Code shim loops on an install prompt.
    try {
        $npmPrefix = (& npm prefix -g 2>$null)
        if ($npmPrefix) {
            $prefix = ([string]@($npmPrefix)[0]).Trim()
            foreach ($name in @("copilot.cmd", "copilot")) {
                $candidate = Join-Path $prefix $name
                if (Test-Path $candidate) { return $candidate }
            }
        }
    } catch { }
    $onPath = Get-Command copilot -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty Source
    if ($onPath) { return $onPath }
    return $null
}

function Build-ConflictResolutionPrompt {
    param([Parameter(Mandatory = $true)][string[]]$Files)

    $fileList = ($Files -join ", ")
    return (
        "You are resolving Git MERGE CONFLICTS in this repository checkout. The " +
        "working tree is mid-merge and these files ONLY contain conflict markers " +
        "(<<<<<<<, |||||||, =======, >>>>>>>) shown with the common ancestor " +
        "(zdiff3): $fileList. Resolve every conflict with a correct SEMANTIC merge " +
        "that PRESERVES the intent of BOTH sides; never blanket-pick one side and " +
        "discard the other; prefer the additive or superset outcome when both " +
        "changes must coexist. Rules: edit ONLY those files; remove ALL conflict " +
        "markers and leave valid, compilable code; do NOT run git add, commit, " +
        "merge, or push and do NOT create branches (only edit files); do NOT " +
        "change unrelated code, imports, or formatting beyond what the merge needs."
    )
}

function Invoke-CopilotConflictResolution {
    # Clears conflict markers in every pending merge using the Copilot CLI.
    # Returns $true only when no pending merge carries markers afterwards.
    # Never throws: automatic callers rethrow the original sync failure instead.
    param(
        [string]$CopilotPath,
        [string]$Model,
        [switch]$AllowAllPaths
    )

    $copilot = Resolve-CopilotCli -Override $CopilotPath
    if (-not $copilot) {
        Write-SyncLog -Level Warn "GitHub Copilot CLI not found; skipping automatic resolution. Install with: npm install -g @github/copilot"
        return $false
    }

    Register-OrphanedLaneConflicts
    $pending = @(Get-PendingMerges)
    if ($pending.Count -eq 0) {
        Write-SyncLog "No pending merges recorded; nothing to resolve."
        return $true
    }

    Write-SyncLog "Using Copilot CLI: $copilot"
    Write-SyncLog "Attempting Copilot resolution for $($pending.Count) pending merge(s)..."
    $unresolved = 0

    foreach ($entry in $pending) {
        $wd = [string]$entry.workingDirectory
        $label = [string]$entry.label
        if (-not (Test-Path $wd -PathType Container)) {
            Write-SyncLog -Level Warn "Working directory missing for ${label}: $wd. Skipping."
            $unresolved++
            continue
        }

        $files = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($entry.conflictedFiles))
        if ($files.Count -eq 0) {
            Write-SyncLog "$label is already marker-free; nothing for Copilot to do."
            continue
        }

        Write-SyncLog "Asking Copilot to resolve $($files.Count) file(s) for ${label}: $($files -join ', ')"
        $prompt = Build-ConflictResolutionPrompt -Files $files
        $copilotArgs = @("-p", $prompt, "--allow-all-tools", "--deny-tool=shell(git push)")
        if ($AllowAllPaths) { $copilotArgs += "--allow-all-paths" }
        if ($Model) { $copilotArgs += @("--model", $Model) }

        Push-Location $wd
        try {
            & $copilot @copilotArgs
            $copilotExit = $LASTEXITCODE
        } catch {
            Write-SyncLog -Level Warn "Copilot CLI failed for ${label}: $($_.Exception.Message)"
            $copilotExit = 1
        } finally {
            Pop-Location
        }
        if ($copilotExit -ne 0) {
            Write-SyncLog -Level Warn "Copilot exited with code $copilotExit for $label (continuing to marker check)."
        }

        $still = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($files))
        if ($still.Count -gt 0) {
            Write-SyncLog -Level Error "Copilot did not clear all markers for ${label}: $($still -join ', '). Left for manual or chat resolution."
            $unresolved++
        } else {
            Write-SyncLog "Copilot cleared all conflict markers for $label."
        }
    }

    return ($unresolved -eq 0)
}

function Test-ConflictPending {
    # State-based conflict detection. Message matching alone is unreliable because
    # all-worktrees-sync aggregates per-lane errors into its own summary message.
    try {
        Register-OrphanedLaneConflicts
        foreach ($entry in @(Get-PendingMerges)) {
            $wd = [string]$entry.workingDirectory
            if (-not (Test-Path $wd -PathType Container)) { continue }
            $files = @(Get-FilesWithConflictMarkers -WorkingDirectory $wd -Files @($entry.conflictedFiles))
            if ($files.Count -gt 0) { return $true }
        }
    } catch {
        return $false
    }
    return $false
}

function Invoke-SyncWithAutoResolve {
    # Runs a sync body and, when it stops on a novel semantic conflict, resolves it
    # with the Copilot CLI and retries in-flow. Without this the owner has to notice
    # the failure and run Resolve-Conflicts.cmd by hand for a routine conflict.
    # Safety is unchanged: Copilot only edits files, and the retried sync still runs
    # the staging, validation, and publish gates.
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Body,
        [switch]$NoAutoResolve
    )

    if ($global:TripplannerAutoResolveActive) {
        return & $Body   # a nested sync script lets the outermost one own the retry
    }
    $disabled = $NoAutoResolve -or ($env:TRIPPLANNER_NO_AUTO_RESOLVE -in @("1", "true", "True"))
    $global:TripplannerAutoResolveActive = $true
    try {
        try {
            return & $Body
        } catch {
            if ($disabled -or -not (Test-ConflictPending)) { throw }

            Write-SyncLog -Level Warn "Sync stopped on a conflict; attempting automatic resolution before giving up..."
            $resolved = $false
            try {
                $resolved = Invoke-CopilotConflictResolution
            } catch {
                Write-SyncLog -Level Warn "Automatic resolution failed: $($_.Exception.Message)"
            }
            if (-not $resolved) {
                Write-SyncLog -Level Error "Automatic resolution could not clear every conflict; manual resolution is needed."
                throw
            }

            Write-SyncLog "Conflicts resolved automatically; resuming synchronization..."
            return & $Body   # the retry heals the pending merge, then validates and publishes
        }
    } finally {
        $global:TripplannerAutoResolveActive = $false
    }
}
