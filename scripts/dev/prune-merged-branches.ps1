#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Delete local branches already merged into master, verified to lose no commits.

.DESCRIPTION
  Periodic branch-clutter cleanup: finished gpt-<task>, bugfix, and other
  one-off branches pile up once their pull requests land. This finds local
  branches whose every commit is already an ancestor of origin/master (or
  master when origin cannot be reached) and removes them with `git branch -d`,
  which itself refuses to delete anything Git cannot prove is merged. That
  makes the ancestor check and the delete command a double guarantee against
  losing a commit.

  Branches attached to any worktree (the primary checkout, registered
  sandboxes, multiagent worktrees, or a temporary sync worktree) are always
  skipped: Git cannot delete a checked-out branch, and removing its worktree is
  a separate, lane-owning decision this script does not make. Branches that
  still have commits master does not are reported and left alone.

  In addition, detached-HEAD worktrees (no branch, left over from abandoned
  syncs or old agent runs) are removed when their HEAD is already in master
  and the folder is clean.

  Supports -WhatIf/-Confirm to preview before deleting anything.

.PARAMETER KeepRemote
  Skip deleting origin's matching branch after the local branch is removed.
  By default the remote branch is deleted once the local delete succeeds.

.EXAMPLE
  ./scripts/dev/prune-merged-branches.ps1 -WhatIf
  ./scripts/dev/prune-merged-branches.ps1
  ./scripts/dev/prune-merged-branches.ps1 -KeepRemote
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$BaseBranch = "master",
    [switch]$NoFetch,
    [switch]$KeepRemote
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$primaryRoot = Get-PrimaryRepositoryRoot -RepositoryRoot $scriptRepoRoot
$primaryRootComparable = (Resolve-Path $primaryRoot).Path

function Remove-WorktreeLeftovers {
    # Reparse points (npm workspace symlinks) must be removed separately on
    # Windows before recursing; locked binaries need a few retries.
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    Get-ChildItem -LiteralPath $Path -Force -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint) } |
        ForEach-Object {
            if ($IsWindows) { & cmd /c rmdir "$($_.FullName)" }
            else { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        }
    foreach ($attempt in 1..12) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $Path)) { return $true }
        if ($attempt -lt 12) { Start-Sleep -Milliseconds 250 }
    }
    return $false
}

if (-not $NoFetch) {
    & git -C $primaryRoot fetch origin --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "git fetch origin failed; comparing against the local $BaseBranch instead."
    }
}

$baseRef = "origin/$BaseBranch"
& git -C $primaryRoot rev-parse --quiet --verify $baseRef 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $baseRef = $BaseBranch }
& git -C $primaryRoot rev-parse --quiet --verify $baseRef 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not resolve '$baseRef' to compare branches against." }

# A branch checked out in any worktree cannot be deleted by Git and is always skipped.
# Detached-HEAD worktrees are collected separately for cleanup at the end.
$attachedBranches = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$detachedWorktreeList = [System.Collections.Generic.List[object]]::new()
$currentWorktreePath = $null
$currentHead = $null
foreach ($line in @(& git -C $primaryRoot worktree list --porcelain)) {
    if ($line.StartsWith("worktree ")) {
        $currentWorktreePath = $line.Substring(9)
        $currentHead = $null
    } elseif ($line.StartsWith("HEAD ")) {
        $currentHead = $line.Substring(5)
    } elseif ($line.StartsWith("branch refs/heads/")) {
        $attachedBranches.Add($line.Substring(18)) | Out-Null
    } elseif ($line -eq "detached" -and $currentWorktreePath) {
        $detachedWorktreeList.Add([pscustomobject]@{ Path = $currentWorktreePath; Head = $currentHead })
    }
}
# Registered sandboxes are owned by the sandbox tooling even if briefly missing a worktree.
foreach ($entry in (Get-SandboxRegistry -PrimaryRoot $primaryRoot)) {
    $attachedBranches.Add($entry.branch) | Out-Null
}

$localBranches = @(& git -C $primaryRoot for-each-ref --format="%(refname:short)" refs/heads)
if ($LASTEXITCODE -ne 0) { throw "Could not enumerate local branches." }
$currentBranch = (& git -C $primaryRoot branch --show-current).Trim()

$merged = [System.Collections.Generic.List[string]]::new()
$skippedAttached = [System.Collections.Generic.List[string]]::new()
$skippedUnmerged = [System.Collections.Generic.List[string]]::new()
$deletedDetached = 0
$leftoverFolders = [System.Collections.Generic.List[string]]::new()

foreach ($branch in $localBranches) {
    if ($branch -eq $BaseBranch -or $branch -eq $currentBranch) { continue }
    if ($attachedBranches.Contains($branch)) {
        $skippedAttached.Add($branch)
        continue
    }
    & git -C $primaryRoot merge-base --is-ancestor $branch $baseRef 2>$null
    if ($LASTEXITCODE -eq 0) {
        $merged.Add($branch)
    } else {
        $skippedUnmerged.Add($branch)
    }
}

if ($skippedAttached.Count -gt 0) {
    Write-Host "Skipped (checked out in a worktree or a registered sandbox):"
    foreach ($b in $skippedAttached) { Write-Host "  $b" }
}
if ($skippedUnmerged.Count -gt 0) {
    Write-Host "Skipped (not fully merged into $baseRef; would lose commits):"
    foreach ($b in $skippedUnmerged) { Write-Host "  $b" }
}

$deletedCount = 0
if ($merged.Count -gt 0) {
    Write-Host "Merged into $baseRef with no unique commits:"
    foreach ($b in $merged) { Write-Host "  $b" }
    foreach ($branch in $merged) {
        if (-not $PSCmdlet.ShouldProcess($branch, "Delete local branch (git branch -d)")) { continue }
        & git -C $primaryRoot branch -d $branch 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not delete '$branch' safely; left it in place."
            continue
        }
        $deletedCount++
        Write-Host "Deleted local branch $branch"
        if (-not $KeepRemote) {
            & git -C $primaryRoot ls-remote --exit-code --heads origin $branch 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                if ($PSCmdlet.ShouldProcess("origin/$branch", "Delete remote branch")) {
                    & git -C $primaryRoot push origin --delete $branch
                    if ($LASTEXITCODE -eq 0) { Write-Host "Deleted origin/$branch" }
                    else { Write-Warning "Could not delete origin/$branch" }
                }
            }
        }
    }
} elseif ($detachedWorktreeList.Count -eq 0) {
    Write-Host "No merged branches or detached worktrees to clean up."
    exit 0
}

& git -C $primaryRoot worktree prune 2>$null | Out-Null

# Detached-HEAD worktrees whose HEAD is already in master: remove them.
foreach ($wt in $detachedWorktreeList) {
    $wtResolved = if (Test-Path $wt.Path) { (Resolve-Path $wt.Path).Path } else { $wt.Path }
    if ($wtResolved -eq $primaryRootComparable) { continue }
    if (-not $wt.Head) { Write-Warning "Skipped detached worktree $($wt.Path): no HEAD."; continue }
    & git -C $primaryRoot merge-base --is-ancestor $wt.Head $baseRef 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Skipped detached worktree $($wt.Path) (HEAD $($wt.Head.Substring(0, 8)) not in $baseRef)."
        continue
    }
    if (-not (Test-Path $wt.Path)) { continue }
    $status = @(& git -C $wt.Path status --porcelain 2>$null)
    if ($LASTEXITCODE -ne 0 -or $status.Count -gt 0) {
        Write-Host "Skipped detached worktree $($wt.Path) (uncommitted changes)."
        continue
    }
    if (-not $PSCmdlet.ShouldProcess($wt.Path, "Remove detached worktree")) { continue }
    & git -C $primaryRoot worktree remove --force $wt.Path 2>&1 | Out-Host
    $folderLeftBehind = $false
    if ($LASTEXITCODE -ne 0) {
        & git -C $primaryRoot worktree prune 2>$null | Out-Null
        if (-not (Remove-WorktreeLeftovers -Path $wt.Path)) {
            $folderLeftBehind = $true
            $leftoverFolders.Add($wt.Path)
        }
    }
    $deletedDetached++
    if ($folderLeftBehind) {
        Write-Host "Unregistered detached worktree at $($wt.Path) (folder left behind, listed below)"
    } else {
        Write-Host "Removed detached worktree at $($wt.Path)"
    }
}
if ($leftoverFolders.Count -gt 0) {
    Write-Host "Folders left behind (locked by another process; close it and delete manually):"
    foreach ($p in $leftoverFolders) { Write-Host "  $p" }
}

if (-not $WhatIfPreference) {
    $parts = [System.Collections.Generic.List[string]]::new()
    if ($merged.Count -gt 0) { $parts.Add("deleted $deletedCount of $($merged.Count) merged branch(es)") }
    if ($detachedWorktreeList.Count -gt 0) { $parts.Add("removed $deletedDetached of $($detachedWorktreeList.Count) detached worktree(s)") }
    if ($parts.Count -gt 0) { Write-Host (($parts -join "; ") + ".") }
}
