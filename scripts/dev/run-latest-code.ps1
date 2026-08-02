#!/usr/bin/env pwsh
[CmdletBinding()]
param(
	[switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
Write-Host "Synchronizing master, Agent 1, and Agent 2..." -ForegroundColor Cyan
& "$PSScriptRoot\sync-latest.ps1" -ValidateOnly:$ValidateOnly

if ($ValidateOnly) {
	Write-Host "Ready: local changes can be preserved around worktree synchronization."
	return
}

Write-Host "Starting the latest local application..." -ForegroundColor Cyan
& "$PSScriptRoot\dev-spa.ps1"