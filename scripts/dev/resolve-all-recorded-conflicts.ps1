#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Replay recorded conflict resolutions in every attached worktree.

.DESCRIPTION
  Scans the primary checkout and every attached sandbox, multiagent, or branch
  worktree for a pending merge. Each pending merge is handed to the canonical
  conflict resolver, which replays only resolutions already recorded by Git
  rerere and commits the merge when it is fully resolved.

  New conflicts remain unresolved and are reported after every worktree has been
  checked. This command does not fetch, start or abort merges, or push branches.

.EXAMPLE
  ./scripts/dev/resolve-all-recorded-conflicts.ps1
  ./scripts/dev/resolve-all-recorded-conflicts.ps1 -WhatIf
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
. "$PSScriptRoot/lib/sandbox-registry.ps1"

$checkoutRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$repoRoot = Get-PrimaryRepositoryRoot -RepositoryRoot $checkoutRoot
$resolverScript = Join-Path $PSScriptRoot "resolve-sandbox-conflicts.ps1"

Start-RunLog -Name "resolve-all-recorded-conflicts" | Out-Null

function Get-AttachedWorktrees {
    $worktrees = [System.Collections.Generic.List[object]]::new()
    $current = $null

    foreach ($line in @(& git -C $repoRoot worktree list --porcelain)) {
        if ($line.StartsWith("worktree ")) {
            if ($null -ne $current) { $worktrees.Add($current) }
            $current = [pscustomobject]@{
                path = $line.Substring(9)
                branch = ""
                prunable = $false
            }
            continue
        }
        if ($null -eq $current) { continue }
        if ($line.StartsWith("branch refs/heads/")) {
            $current.branch = $line.Substring(18)
        } elseif ($line.StartsWith("prunable")) {
            $current.prunable = $true
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not enumerate Git worktrees." }
    if ($null -ne $current) { $worktrees.Add($current) }
    return @($worktrees)
}

function Test-PendingMerge {
    param([string]$WorkingDirectory)

    $unmerged = @(& git -C $WorkingDirectory diff --name-only --diff-filter=U)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect conflicts in '$WorkingDirectory'."
    }
    & git -C $WorkingDirectory rev-parse --quiet --verify MERGE_HEAD 2>$null | Out-Null
    return $unmerged.Count -gt 0 -or $LASTEXITCODE -eq 0
}

function Get-NormalizedWorktreePath {
    param([string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
}

$sandboxByWorktree = @{}
$registryPath = Get-SandboxRegistryPath -PrimaryRoot $repoRoot
if (Test-Path $registryPath) {
    foreach ($entry in @(Get-SandboxRegistry -PrimaryRoot $repoRoot)) {
        $path = Get-NormalizedWorktreePath -Path ([string]$entry.worktree)
        $sandboxByWorktree[$path] = $entry
    }
}

$pending = 0
$resolved = [System.Collections.Generic.List[string]]::new()
$unresolved = [System.Collections.Generic.List[string]]::new()

foreach ($worktree in @(Get-AttachedWorktrees)) {
    if ($worktree.prunable -or -not (Test-Path -LiteralPath $worktree.path)) { continue }

    $path = Get-NormalizedWorktreePath -Path ([string]$worktree.path)
    $lane = if ($worktree.branch) { $worktree.branch } else { "(detached: $path)" }
    try {
        $recoveryPending = Test-PendingMerge -WorkingDirectory $path
        if ($sandboxByWorktree.ContainsKey($path)) {
            $statePath = Join-Path $repoRoot (
                "logs/sandbox/pending-conflict-$((Split-Path -Leaf $path)).json"
            )
            $recoveryPending = $recoveryPending -or (Test-Path $statePath)
        }
        if (-not $recoveryPending) { continue }
        $pending += 1

        if (-not $worktree.branch) {
            throw "The worktree is detached; attach it to a branch before finishing its merge."
        }
        if (-not $PSCmdlet.ShouldProcess(
            $lane,
            "Replay recorded conflict resolution and finish pending merge"
        )) {
            continue
        }

        if ($sandboxByWorktree.ContainsKey($path)) {
            & $resolverScript -Sandbox $sandboxByWorktree[$path].slug -Confirm:$false
        } else {
            & $resolverScript -WorkingDirectory $path -Lane $lane -Confirm:$false
        }
        if ($LASTEXITCODE -ne 0) {
            throw "The conflict resolver exited with code $LASTEXITCODE."
        }
        $resolved.Add($lane)
    } catch {
        $unresolved.Add("$lane|$($_.Exception.Message)")
        Write-Warning "[$lane] $($_.Exception.Message)"
    }
}

if ($WhatIfPreference) {
    Write-Host "`nPreview complete: $pending pending merge(s) found; no worktree was changed."
    return
}

Write-Host ""
if ($pending -eq 0) {
    Write-Host "[no-op] No attached worktree has a pending merge." -ForegroundColor Yellow
    return
}
Write-Host "Resolved $($resolved.Count) of $pending pending merge(s)." -ForegroundColor Green
foreach ($lane in $resolved) {
    Write-Host "  [resolved] $lane" -ForegroundColor Green
}
if ($unresolved.Count -eq 0) { return }

Write-Host "`nStill requires manual resolution:" -ForegroundColor Yellow
$number = 0
foreach ($item in $unresolved) {
    $number += 1
    $parts = $item.Split("|", 2)
    Write-Host "  $number. $($parts[0]): $($parts[1])" -ForegroundColor Yellow
}
throw "$($unresolved.Count) worktree(s) still contain conflicts not covered by a recorded resolution."
