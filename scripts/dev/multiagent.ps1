#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Control the multiagent coordinator: start, stop, pause, status, plan, audit.

.DESCRIPTION
  Thin dispatcher over scripts/dev/multiagent.py using the repository virtual
  environment when one is present.

    The coordinator dispatches routine queued work, audit bugs, and explicitly
    approved gated work. It works in its own worktrees under
    <primary>.worktrees/multiagent and never touches a sandbox, a port, or a
    deployment.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonGitDir = & git -C $repoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) {
  throw "Could not resolve the primary Tripplanner checkout."
}
$repoRoot = Split-Path -Parent $commonGitDir.Trim()

. (Join-Path $PSScriptRoot "lib/python-runtime.ps1")
$python = (Resolve-TripplannerPython -RepoRoot $repoRoot).Python

$cli = Join-Path $PSScriptRoot "multiagent.py"
# -u so a controller that streams through this dispatcher is never buffered.
& $python -u $cli @Rest
exit $LASTEXITCODE
