#!/usr/bin/env pwsh
[CmdletBinding()]
param(
	[switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
Write-Host "Synchronizing latest committed code into this worktree..." -ForegroundColor Cyan
& "$PSScriptRoot\sync-latest.ps1" -ValidateOnly:$ValidateOnly

if ($ValidateOnly) {
	Write-Host "Ready: local changes can be preserved around worktree synchronization."
	return
}

Write-Host "Starting the latest local dev stack with dev-spa.ps1..." -ForegroundColor Cyan
& "$PSScriptRoot\dev-spa.ps1"