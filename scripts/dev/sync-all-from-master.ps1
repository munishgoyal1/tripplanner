#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Fast-forward primary master from origin/master, then pull it into every local lane.

.DESCRIPTION
  Analogous to sync-sbxs-from-master.ps1, but scoped to every local branch instead
  of only registered sandboxes: registered sandboxes, multiagent worktrees, and
  branches without an attached worktree. This is a thin wrapper around
  full-2way-sync.ps1's default "all" scope with -PullOnly, so lanes take incoming
  master commits but no lane work is published back to master.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$BaseBranch = "master",
    [switch]$AlwaysValidate
)

$ErrorActionPreference = "Stop"
$fullSyncScript = Join-Path $PSScriptRoot "full-2way-sync.ps1"

# Array splats bind positionally only; named/switch parameters need a hashtable splat.
$namedArguments = @{ BaseBranch = $BaseBranch; PullOnly = $true }
if ($AlwaysValidate) { $namedArguments.AlwaysValidate = $true }
if ($WhatIfPreference) { $namedArguments.WhatIf = $true }

& $fullSyncScript "all" @namedArguments
exit $LASTEXITCODE
