#!/usr/bin/env pwsh
[CmdletBinding()]
param(
	[switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stashCreated = $false

$masterChanges = & git -C $repoRoot status --porcelain
if ($LASTEXITCODE -ne 0) {
	throw "Could not inspect the master worktree."
}

if ($masterChanges) {
	Write-Host "Temporarily preserving local master changes..." -ForegroundColor Cyan
	& git -C $repoRoot stash push --include-untracked --message "run-latest-code temporary local changes"
	if ($LASTEXITCODE -ne 0) {
		throw "Could not preserve local master changes. Nothing was merged."
	}
	$stashCreated = $true
}

try {
	Write-Host "Merging the latest Agent 1 code..." -ForegroundColor Cyan
	& "$PSScriptRoot\merge-agent-1.ps1" -ValidateOnly:$ValidateOnly
} finally {
	if ($stashCreated) {
		Write-Host "Restoring local master changes..." -ForegroundColor Cyan
		& git -C $repoRoot stash pop --index
		if ($LASTEXITCODE -ne 0) {
			throw "Local master changes conflicted with the latest code. Resolve the worktree conflicts; the temporary stash was retained."
		}
	}
}

if ($ValidateOnly) {
	Write-Host "Ready: local master changes can be preserved around Worker 1 integration."
	return
}

Write-Host "Starting the latest local application..." -ForegroundColor Cyan
& "$repoRoot\scripts\dev-spa.ps1"