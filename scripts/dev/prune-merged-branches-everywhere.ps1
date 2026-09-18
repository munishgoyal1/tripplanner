#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Delete local branches merged into master with no lost commits, even when
  checked out in a worktree or a registered sandbox.

.DESCRIPTION
  A more aggressive sibling of prune-merged-branches.ps1, which always skips
  anything checked out anywhere. This one still requires the same double
  guarantee against losing work -- every commit on the branch must already be
  an ancestor of origin/master (or master when origin cannot be reached), and
  the branch's checkout must have no uncommitted changes -- but once both hold
  it removes the worktree (or discards the sandbox) so the branch itself can
  be deleted too.

  Three cases, by how the branch is checked out:
    - Not checked out anywhere: same as prune-merged-branches.ps1, deleted
      with `git branch -d`, which itself refuses anything Git cannot prove is
      merged.
    - Checked out in a registered sandbox (tripplanner.worktrees/sandboxes.json):
      delegated to `sandbox.ps1 -Discard`, which re-verifies merged-and-clean
      itself and also owns dropping the sandbox's emulator database and
      preserving its corpus data. This script does not duplicate that.
    - Checked out in any other worktree (a plain agent worktree, a multiagent
      worktree, etc.): removed with `git worktree remove --force` after this
      script confirms `git status --porcelain` is empty, then the branch is
      deleted with `git branch -d`. When a locked file stops the folder
      deletion (common on Windows: a running esbuild service, an editor, or a
      terminal with its cwd inside), git has usually still unregistered the
      worktree, so the branch delete proceeds and the leftover folder is
      retried, then reported for manual deletion.

  The primary checkout's own current branch is never touched: there is
  nothing here to check out instead, and Git cannot delete it anyway.

  Supports -WhatIf/-Confirm to preview before deleting or discarding anything.
  Confirmation impact is High (unlike prune-merged-branches.ps1's Medium)
  because this script can remove whole worktrees, not just branch refs.

.PARAMETER KeepRemote
  Skip deleting origin's matching branch after a local branch is removed.
  By default the remote branch is deleted once the local remove succeeds.
  Forwarded to `sandbox.ps1 -Discard` as -DeleteRemoteBranch so all three
  cases share the same default.

.EXAMPLE
  ./scripts/dev/prune-merged-branches-everywhere.ps1 -WhatIf
  ./scripts/dev/prune-merged-branches-everywhere.ps1
  ./scripts/dev/prune-merged-branches-everywhere.ps1 -KeepRemote
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [string]$BaseBranch = "master",
    [switch]$NoFetch,
    [switch]$KeepRemote
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$scriptRepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$primaryRoot = Get-PrimaryRepositoryRoot -RepositoryRoot $scriptRepoRoot
$sandboxScript = Join-Path $primaryRoot "scripts/dev/sandbox.ps1"

function Remove-WorktreeLeftovers {
    # Mirrors sandbox.ps1's Remove-SandboxLeftovers: npm workspace links are
    # reparse points nothing may recurse through, and a locked binary (esbuild,
    # an editor, a terminal) needs a few retries before Windows lets go.
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

# branch -> worktree path, from every worktree (primary, sandboxes, plain, detached).
$worktreePathByBranch = @{}
$currentWorktreePath = $null
foreach ($line in @(& git -C $primaryRoot worktree list --porcelain)) {
    if ($line.StartsWith("worktree ")) {
        $currentWorktreePath = $line.Substring(9)
    } elseif ($line.StartsWith("branch refs/heads/") -and $currentWorktreePath) {
        $worktreePathByBranch[$line.Substring(18)] = $currentWorktreePath
    }
}

# branch -> sandbox registry entry, for sandboxes briefly missing their worktree.
$sandboxEntryByBranch = @{}
foreach ($entry in (Get-SandboxRegistry -PrimaryRoot $primaryRoot)) {
    $sandboxEntryByBranch[$entry.branch] = $entry
}

$localBranches = @(& git -C $primaryRoot for-each-ref --format="%(refname:short)" refs/heads)
if ($LASTEXITCODE -ne 0) { throw "Could not enumerate local branches." }
$currentBranch = (& git -C $primaryRoot branch --show-current).Trim()
$primaryRootComparable = (Resolve-Path $primaryRoot).Path

$deletedUnattached = 0
$deletedWorktrees = 0
$discardedSandboxes = 0
$leftoverFolders = [System.Collections.Generic.List[string]]::new()
$skippedPrimary = [System.Collections.Generic.List[string]]::new()
$skippedDirty = [System.Collections.Generic.List[string]]::new()
$skippedUnmerged = [System.Collections.Generic.List[string]]::new()
$skippedOther = [System.Collections.Generic.List[string]]::new()

foreach ($branch in $localBranches) {
    if ($branch -eq $BaseBranch -or $branch -eq $currentBranch) { continue }

    & git -C $primaryRoot merge-base --is-ancestor $branch $baseRef 2>$null
    if ($LASTEXITCODE -ne 0) {
        $skippedUnmerged.Add($branch)
        continue
    }

    $worktreePath = $worktreePathByBranch[$branch]

    if (-not $worktreePath) {
        if (-not $PSCmdlet.ShouldProcess($branch, "Delete local branch (git branch -d)")) { continue }
        & git -C $primaryRoot branch -d $branch 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not delete '$branch' safely; left it in place."
            continue
        }
        $deletedUnattached++
        Write-Host "Deleted local branch $branch"
        if (-not $KeepRemote) {
            & git -C $primaryRoot ls-remote --exit-code --heads origin $branch 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0 -and $PSCmdlet.ShouldProcess("origin/$branch", "Delete remote branch")) {
                & git -C $primaryRoot push origin --delete $branch
                if ($LASTEXITCODE -eq 0) { Write-Host "Deleted origin/$branch" }
                else { Write-Warning "Could not delete origin/$branch" }
            }
        }
        continue
    }

    $worktreeResolved = if (Test-Path $worktreePath) { (Resolve-Path $worktreePath).Path } else { $worktreePath }
    if ($worktreeResolved -eq $primaryRootComparable) {
        # The primary checkout cannot be torn down by this script.
        $skippedPrimary.Add($branch)
        continue
    }

    if ($sandboxEntryByBranch.ContainsKey($branch)) {
        # sandbox.ps1 -Discard re-verifies merged-and-clean itself, in addition
        # to owning the emulator-database drop and corpus preservation; do not
        # duplicate any of that here.
        $sbx = $sandboxEntryByBranch[$branch]
        if (-not $PSCmdlet.ShouldProcess($sbx.slug, "Discard sandbox (sandbox.ps1 -Discard)")) { continue }
        Push-Location $primaryRoot
        try {
            & $sandboxScript -Discard $sbx.slug -BaseBranch $BaseBranch -DeleteRemoteBranch:(-not $KeepRemote) -Confirm:$false
            if ($LASTEXITCODE -eq 0) {
                $discardedSandboxes++
            } else {
                $skippedOther.Add("$branch (sandbox discard exited $LASTEXITCODE)")
            }
        } catch {
            $skippedOther.Add("$branch (sandbox discard failed: $($_.Exception.Message))")
        } finally {
            Pop-Location
        }
        continue
    }

    if (-not (Test-Path $worktreePath)) {
        # Registered nowhere and the folder is already gone; just drop the stale ref.
        & git -C $primaryRoot worktree prune 2>$null | Out-Null
        if (-not $PSCmdlet.ShouldProcess($branch, "Delete local branch (git branch -d)")) { continue }
        & git -C $primaryRoot branch -d $branch 2>&1 | Out-Host
        if ($LASTEXITCODE -eq 0) { $deletedUnattached++; Write-Host "Deleted local branch $branch" }
        else { Write-Warning "Could not delete '$branch' safely; left it in place." }
        continue
    }

    $status = @(& git -C $worktreePath status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        $skippedOther.Add("$branch (could not read worktree status at $worktreePath)")
        continue
    }
    if ($status.Count -gt 0) {
        $skippedDirty.Add($branch)
        continue
    }

    if (-not $PSCmdlet.ShouldProcess($worktreePath, "Remove worktree and delete local branch $branch")) { continue }
    & git -C $primaryRoot worktree remove --force $worktreePath 2>&1 | Out-Host
    $folderLeftBehind = $false
    if ($LASTEXITCODE -ne 0) {
        # On Windows, git unregisters the worktree yet fails to delete a locked
        # file. Finish the teardown like sandbox.ps1's discard instead of
        # stranding the branch: prune, confirm detachment, retry the folder.
        & git -C $primaryRoot worktree prune 2>$null | Out-Null
        $stillAttached = @(& git -C $primaryRoot worktree list --porcelain) |
            Where-Object { $_ -eq "branch refs/heads/$branch" }
        if ($stillAttached) {
            Write-Warning "Could not remove worktree '$worktreePath' (a locked file is a common cause on Windows); left '$branch' in place."
            continue
        }
        if (-not (Remove-WorktreeLeftovers -Path $worktreePath)) {
            $folderLeftBehind = $true
            $leftoverFolders.Add($worktreePath)
        }
    }
    & git -C $primaryRoot branch -d $branch 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Removed worktree '$worktreePath' but could not delete '$branch' safely; left the branch in place."
        continue
    }
    $deletedWorktrees++
    if ($folderLeftBehind) {
        Write-Host "Unregistered worktree and deleted local branch $branch (folder left behind, listed below)"
    } else {
        Write-Host "Removed worktree '$worktreePath' and deleted local branch $branch"
    }
    if (-not $KeepRemote) {
        & git -C $primaryRoot ls-remote --exit-code --heads origin $branch 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0 -and $PSCmdlet.ShouldProcess("origin/$branch", "Delete remote branch")) {
            & git -C $primaryRoot push origin --delete $branch
            if ($LASTEXITCODE -eq 0) { Write-Host "Deleted origin/$branch" }
            else { Write-Warning "Could not delete origin/$branch" }
        }
    }
}

& git -C $primaryRoot worktree prune 2>$null | Out-Null

if ($skippedPrimary.Count -gt 0) {
    Write-Host "Skipped (checked out in the primary checkout):"
    foreach ($b in $skippedPrimary) { Write-Host "  $b" }
}
if ($skippedDirty.Count -gt 0) {
    Write-Host "Skipped (merged, but its worktree has uncommitted changes):"
    foreach ($b in $skippedDirty) { Write-Host "  $b" }
}
if ($skippedUnmerged.Count -gt 0) {
    Write-Host "Skipped (not fully merged into $baseRef; would lose commits):"
    foreach ($b in $skippedUnmerged) { Write-Host "  $b" }
}
if ($skippedOther.Count -gt 0) {
    Write-Host "Skipped (could not verify or clean up safely):"
    foreach ($b in $skippedOther) { Write-Host "  $b" }
}
if ($leftoverFolders.Count -gt 0) {
    Write-Host "Folders left behind (locked by another process; close it and delete manually):"
    foreach ($p in $leftoverFolders) { Write-Host "  $p" }
}

if (-not $WhatIfPreference) {
    Write-Host "Deleted $deletedUnattached unattached branch(es), removed $deletedWorktrees worktree(s) and deleted their branch(es), discarded $discardedSandboxes sandbox(es)."
}
