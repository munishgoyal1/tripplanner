#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Bring every lane to the same commit, and keep going when one lane cannot.

.DESCRIPTION
  The convergence tool for when the lanes have drifted and you want them all on
  the same code again. It differs from twoway-sync-master-sbx.ps1 in what it
  tolerates rather than in what it does:

  * Uncommitted work does not stop it. Each lane's changes are set aside before
    the sync and handed back afterwards, so nothing has to be stashed by hand.
    Work in progress is never committed and never published: it is not
    finished, and only commits a lane already had reach the base branch.
  * One bad lane does not stop the others. Every failure is caught, the run
    continues, and the end of the report is a numbered list of what is left.
  * Conflicts are handed to the existing resolver, which replays resolutions
    this repository has already recorded. Anything genuinely new is left for a
    person and reported.

  It is idempotent: run it, fix what it lists, run it again. A run with nothing
  to do says so and changes nothing.

  Validation is run where it can tell you something. A lane with no commits of
  its own is never merged, so it is never validated; a lane whose changes touch
  only documentation or captured data is merged without the suite, because no
  test reads those files. Pass -AlwaysValidate to disable that judgement.

.EXAMPLE
  ./scripts/dev/full-2way-sync.ps1 -WhatIf
  ./scripts/dev/full-2way-sync.ps1
  ./scripts/dev/full-2way-sync.ps1 -Yes
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$BaseBranch = "master",
    # Skip the confirmation. The point of this script is repeated runs.
    [switch]$Yes,
    [switch]$AlwaysValidate,
    # Bring lanes up to the base without publishing any lane work to it.
    [switch]$PullOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $scriptRepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
    throw "Could not resolve the primary Tripplanner checkout."
}
$primaryRoot = Split-Path -Parent $commonGitDir.Trim()
$primaryBranch = (& git -C $primaryRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $primaryBranch -ne $BaseBranch) {
    throw "The primary checkout must be on $BaseBranch. It is on '$primaryBranch'."
}

Start-RunLog -Name "full-2way-sync" | Out-Null

$sandboxScript = Join-Path $PSScriptRoot "sandbox.ps1"
$resolverScript = Join-Path $PSScriptRoot "resolve-sandbox-conflicts.ps1"

# Numbered at the end. Each entry is one thing a person still has to do.
$remaining = [System.Collections.Generic.List[string]]::new()
$did = [System.Collections.Generic.List[string]]::new()
# Lane -> the stashes this run created, newest last. A lane can be dirtied more
# than once in a run, because other sessions keep working while this one goes.
$stashed = @{}

function Add-Did {
    # A dry run must not claim it changed anything.
    param([string]$Entry)
    if (-not $WhatIfPreference) { $did.Add($Entry) }
}

function Add-Remaining {
    param([string]$Lane, [string]$Problem, [string]$NextStep)
    $remaining.Add("$Lane|$Problem|$NextStep")
}

function Get-Dirty {
    param([string]$WorkingDirectory)
    return @(& git -C $WorkingDirectory status --porcelain)
}

function Get-Unmerged {
    # Ask git rather than matching an error message; the launchers rewrap text.
    param([string]$WorkingDirectory)
    return @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
}

function Push-LaneStash {
    <#
      Set uncommitted work aside so the lane can take part in a sync, and
      remember the exact stash commit so only this script's own stash is ever
      restored. Work in progress is never committed: it is not finished, and
      publishing it would put it on the base branch.
    #>
    param([string]$WorkingDirectory, [string]$Lane)

    $dirty = Get-Dirty -WorkingDirectory $WorkingDirectory
    if ($dirty.Count -eq 0) { return $true }
    if (-not $PSCmdlet.ShouldProcess($Lane, "Set aside $($dirty.Count) uncommitted path(s)")) { return $true }

    # -u so untracked files travel too, otherwise a merge can collide with one.
    & git -C $WorkingDirectory stash push -u -q -m "full-2way-sync $Lane" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Remaining -Lane $Lane -Problem "has uncommitted changes that could not be set aside" `
            -NextStep "Inspect 'git -C $WorkingDirectory status' by hand."
        return $false
    }
    $stashCommit = (& git -C $WorkingDirectory rev-parse --quiet --verify refs/stash).Trim()
    if (-not $stashCommit) {
        Add-Remaining -Lane $Lane -Problem "set aside its changes but no stash was recorded" `
            -NextStep "Check 'git -C $WorkingDirectory stash list' before re-running."
        return $false
    }
    if (-not $stashed.ContainsKey($Lane)) {
        $stashed[$Lane] = [System.Collections.Generic.List[object]]::new()
    }
    $stashed[$Lane].Add(@{ WorkingDirectory = $WorkingDirectory; Commit = $stashCommit; Count = $dirty.Count })
    Write-Host "[hold]    $Lane - set aside $($dirty.Count) uncommitted path(s)" -ForegroundColor Yellow
    return $true
}

function Restore-LaneStash {
    <# Give the lane its work in progress back, exactly as it was handed over. #>
    param([string]$Lane, [hashtable]$Held)

    $workingDirectory = $Held.WorkingDirectory
    # Find our own stash by commit rather than assuming it is still on top;
    # anything else in the stack belongs to the owner and must not be touched.
    $entries = @(& git -C $workingDirectory stash list --format="%H")
    $index = [Array]::IndexOf($entries, $Held.Commit)
    if ($index -lt 0) {
        Add-Remaining -Lane $Lane -Problem "work in progress is no longer in its stash list" `
            -NextStep "Recover it with 'git -C $workingDirectory stash list' and 'git stash apply <ref>'."
        return
    }
    if (-not $PSCmdlet.ShouldProcess($Lane, "Restore $($Held.Count) set-aside path(s)")) { return }

    & git -C $workingDirectory stash pop "stash@{$index}" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Remaining -Lane $Lane -Problem "work in progress conflicts with the code it just took" `
            -NextStep "Resolve it in $workingDirectory; the stash is kept, so 'git stash list' still holds it."
        return
    }
    Write-Host "[restore] $Lane - returned $($Held.Count) path(s)" -ForegroundColor Green
    Add-Did "$Lane - kept its work in progress uncommitted"
}

function Resolve-Pending {
    <#
      Finish a merge left half-done by an earlier run, using recorded
      resolutions only. Returns whether the lane is clear afterwards.
    #>
    param([string]$WorkingDirectory, [string]$Lane)

    if ((Get-Unmerged -WorkingDirectory $WorkingDirectory).Count -eq 0) { return $true }
    Write-Host "[resolve] $Lane - replaying recorded conflict resolutions" -ForegroundColor Yellow
    try {
        & $resolverScript -Sandbox $Lane -Confirm:$false
        if ($LASTEXITCODE -ne 0) { throw "the resolver returned $LASTEXITCODE" }
    } catch {
        # Expected whenever the conflict is genuinely new.
    }
    $left = Get-Unmerged -WorkingDirectory $WorkingDirectory
    if ($left.Count -gt 0) {
        Add-Remaining -Lane $Lane -Problem "has $($left.Count) conflicted file(s): $($left -join ', ')" `
            -NextStep "Resolve them in $WorkingDirectory, then run this script again."
        return $false
    }
    Write-Host "[resolve] $Lane - recovered" -ForegroundColor Green
    Add-Did "$Lane - resolved a pending merge"
    return $true
}

function Update-Lane {
    <# Merge the base into one lane, recovering from a conflict once. #>
    param([string]$WorkingDirectory, [string]$Lane)

    try {
        & $sandboxScript -Update $Lane -BaseBranch $BaseBranch -NoSync -Confirm:$false
        if ($LASTEXITCODE -ne 0) { throw "update returned $LASTEXITCODE" }
        return $true
    } catch {
        $firstError = $_.Exception.Message
        if ((Get-Unmerged -WorkingDirectory $WorkingDirectory).Count -eq 0) {
            Add-Remaining -Lane $Lane -Problem "could not take $BaseBranch : $firstError" `
                -NextStep "Run 'scripts/dev/sandbox.ps1 -Update $Lane' in a terminal and read the error."
            return $false
        }
        if (-not (Resolve-Pending -WorkingDirectory $WorkingDirectory -Lane $Lane)) { return $false }
        try {
            & $sandboxScript -Update $Lane -BaseBranch $BaseBranch -NoSync -Confirm:$false
            if ($LASTEXITCODE -ne 0) { throw "update returned $LASTEXITCODE after recovery" }
            return $true
        } catch {
            Add-Remaining -Lane $Lane -Problem "still could not take $BaseBranch : $($_.Exception.Message)" `
                -NextStep "Run 'scripts/dev/sandbox.ps1 -Update $Lane' in a terminal and read the error."
            return $false
        }
    }
}

function Test-NeedsValidation {
    <#
      Whether landing this lane could break anything a test would catch.
      Documentation and captured data are read by no test, so validating a lane
      that only touches them spends minutes to prove nothing.
    #>
    param([string]$WorkingDirectory, [string[]]$Commits)

    if ($AlwaysValidate) { return $true }
    $changed = @(& git -C $WorkingDirectory diff --name-only "origin/$BaseBranch...HEAD")
    if ($LASTEXITCODE -ne 0 -or $changed.Count -eq 0) { return $true }
    $inert = $changed | Where-Object {
        $_ -like "docs/*" -or $_ -like "debug-store/*" -or $_ -like "logs/*" -or
        $_ -like "corpus/*" -or $_ -like "*.md"
    }
    return $inert.Count -ne $changed.Count
}

Write-Host "[sync]    fetching origin" -ForegroundColor Cyan
& git -C $primaryRoot fetch -q origin
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin." }

# The primary checkout is a lane too, and a dirty one blocks every merge below.
if (-not (Push-LaneStash -WorkingDirectory $primaryRoot -Lane $BaseBranch)) {
    Write-Host "[stop]    $BaseBranch itself could not be made clean." -ForegroundColor Red
}
& git -C $primaryRoot merge --ff-only "origin/$BaseBranch" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    # Local commits on the base are normal here: it is a working lane.
    & git -C $primaryRoot merge --no-edit "origin/$BaseBranch" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Add-Remaining -Lane $BaseBranch -Problem "cannot merge origin/$BaseBranch" `
            -NextStep "Resolve it in $primaryRoot, then run this script again."
    }
}
$primaryAhead = @(& git -C $primaryRoot log --oneline "origin/$BaseBranch..HEAD")
if ($primaryAhead.Count -gt 0 -and $PSCmdlet.ShouldProcess($BaseBranch, "Push $($primaryAhead.Count) local commit(s)")) {
    & git -C $primaryRoot push -q origin HEAD
    if ($LASTEXITCODE -ne 0) {
        Add-Remaining -Lane $BaseBranch -Problem "has $($primaryAhead.Count) unpushed commit(s)" `
            -NextStep "Push $primaryRoot by hand, then run this script again."
    } else {
        Add-Did "$BaseBranch - pushed $($primaryAhead.Count) commit(s)"
    }
}

$registered = @(Get-SandboxRegistry -PrimaryRoot $primaryRoot)
if ($registered.Count -eq 0) {
    Write-Host "[ready]   No sandboxes are registered." -ForegroundColor Green
    Stop-RunLog
    return
}

Write-Host ""
Write-Host "== 1/5 make every lane clean and current ==" -ForegroundColor Green
$ready = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $registered) {
    $lane = $entry.slug
    if (-not (Test-Path $entry.worktree -PathType Container)) {
        Add-Remaining -Lane $lane -Problem "has no worktree at $($entry.worktree)" `
            -NextStep "Recreate it with New-Sandbox, or drop it with Discard-Sandbox."
        continue
    }
    Write-Host "[lane]    $lane" -ForegroundColor Cyan
    if (-not (Push-LaneStash -WorkingDirectory $entry.worktree -Lane $lane)) { continue }
    if (-not (Resolve-Pending -WorkingDirectory $entry.worktree -Lane $lane)) { continue }
    if (-not (Update-Lane -WorkingDirectory $entry.worktree -Lane $lane)) { continue }
    $ready.Add($entry)
}

Write-Host ""
Write-Host "== 2/5 publish lane work to $BaseBranch ==" -ForegroundColor Green
if ($PullOnly) {
    Write-Host "[skip]    -PullOnly: nothing is published." -ForegroundColor Yellow
} else {
    $withWork = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $ready) {
        $commits = @(& git -C $entry.worktree log --oneline "origin/$BaseBranch..HEAD")
        if ($commits.Count -eq 0) { continue }
        $withWork.Add([pscustomobject]@{
            Entry = $entry
            Commits = $commits
            Validate = Test-NeedsValidation -WorkingDirectory $entry.worktree -Commits $commits
        })
    }

    if ($withWork.Count -eq 0) {
        Write-Host "[current] No lane has work for $BaseBranch." -ForegroundColor Green
    } else {
        foreach ($item in $withWork) {
            $note = if ($item.Validate) { "with validation" } else { "no code changed, skipping validation" }
            Write-Host ("  {0} - {1} commit(s), {2}" -f $item.Entry.slug, $item.Commits.Count, $note)
        }
        $approved = $Yes -or $WhatIfPreference
        if (-not $approved) {
            Write-Host ""
            $answer = Read-Host "Publish the lanes above to $BaseBranch? [y/N]"
            $approved = $answer -in @("y", "Y", "yes", "Yes")
        }
        if (-not $approved) {
            Write-Host "[skipped] Nothing was published; lanes were still brought up to date." -ForegroundColor Yellow
        } else {
            foreach ($item in $withWork) {
                $lane = $item.Entry.slug
                Write-Host ""
                Write-Host "== merging $lane ==" -ForegroundColor Green
                # Re-check right before merging rather than trusting the sweep
                # above: validating and opening a pull request takes minutes, and
                # another session working this lane will have dirtied it again.
                if (-not (Push-LaneStash -WorkingDirectory $item.Entry.worktree -Lane $lane)) { continue }
                try {
                    # One lane failing must not strand the rest, so unlike the
                    # gated two-way sync this keeps going and reports at the end.
                    & $sandboxScript -Merge $lane -BaseBranch $BaseBranch `
                        -SkipValidation:(-not $item.Validate) -Confirm:$false
                    if ($LASTEXITCODE -ne 0) { throw "merge returned $LASTEXITCODE" }
                    Add-Did "$lane - merged $($item.Commits.Count) commit(s) into $BaseBranch"
                } catch {
                    # sandbox.ps1 speaks to someone merging one lane by hand, so
                    # its advice to commit first contradicts this script's whole
                    # promise. Say what actually happened instead.
                    $reason = $_.Exception.Message
                    if ($reason -match "uncommitted changes") {
                        $reason = "someone changed the lane while this run was merging it"
                    }
                    Add-Remaining -Lane $lane -Problem "has $($item.Commits.Count) commit(s) still waiting for $BaseBranch : $reason" `
                        -NextStep "Nothing was lost; run this script again when the lane is idle."
                }
            }
        }
    }
}

Write-Host ""
Write-Host "== 3/5 bring every lane up to the new $BaseBranch ==" -ForegroundColor Green
& git -C $primaryRoot fetch -q origin $BaseBranch
& git -C $primaryRoot merge --ff-only "origin/$BaseBranch" 2>&1 | Out-Null
foreach ($entry in $registered) {
    if (-not (Test-Path $entry.worktree -PathType Container)) { continue }
    if ($remaining | Where-Object { $_.StartsWith("$($entry.slug)|") }) { continue }
    Write-Host "[level]   $($entry.slug)" -ForegroundColor Cyan
    if (-not (Push-LaneStash -WorkingDirectory $entry.worktree -Lane $entry.slug)) { continue }
    Update-Lane -WorkingDirectory $entry.worktree -Lane $entry.slug | Out-Null
}

Write-Host ""
Write-Host "== 4/5 return work in progress ==" -ForegroundColor Green
if ($stashed.Count -eq 0) {
    Write-Host "[none]    No lane had uncommitted work." -ForegroundColor DarkGray
} else {
    foreach ($lane in @($stashed.Keys)) {
        # Newest first: they were taken in order, so they come back in reverse.
        $held = @($stashed[$lane])
        for ($i = $held.Count - 1; $i -ge 0; $i--) {
            Restore-LaneStash -Lane $lane -Held $held[$i]
        }
    }
}

Write-Host ""
Write-Host "== 5/5 verify ==" -ForegroundColor Green
& git -C $primaryRoot fetch -q origin $BaseBranch
$baseHead = (& git -C $primaryRoot rev-parse "origin/$BaseBranch").Trim()
$level = 0
foreach ($entry in $registered) {
    if (-not (Test-Path $entry.worktree -PathType Container)) { continue }
    & git -C $entry.worktree merge-base --is-ancestor $baseHead HEAD 2>$null
    if ($LASTEXITCODE -eq 0) {
        $level++
    } elseif (-not ($remaining | Where-Object { $_.StartsWith("$($entry.slug)|") })) {
        Add-Remaining -Lane $entry.slug -Problem "does not contain $BaseBranch $($baseHead.Substring(0, 7))" `
            -NextStep "Run this script again; if it repeats, update the lane by hand."
    }
}

Write-Host ""
Write-Host "────────────────────────────────────────────────────────────"
Write-Host "$BaseBranch is at $($baseHead.Substring(0, 7)). $level of $($registered.Count) lane(s) contain it."
if ($did.Count -gt 0) {
    Write-Host ""
    Write-Host "Done this run:" -ForegroundColor Green
    foreach ($item in $did) { Write-Host "  - $item" -ForegroundColor DarkGray }
}
if ($remaining.Count -eq 0) {
    Write-Host ""
    Write-Host "Nothing left to resolve. Every lane is on $BaseBranch." -ForegroundColor Green
    Stop-RunLog
    return
}

Write-Host ""
Write-Host "Still to resolve ($($remaining.Count)):" -ForegroundColor Yellow
$index = 0
foreach ($item in $remaining) {
    $index++
    $parts = $item -split "\|", 3
    Write-Host ("  {0}. {1} {2}" -f $index, $parts[0], $parts[1]) -ForegroundColor Yellow
    Write-Host ("     -> {0}" -f $parts[2]) -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "Fix any of the above, then run this script again; it resumes from wherever it is." -ForegroundColor DarkGray
Stop-RunLog
exit 1
