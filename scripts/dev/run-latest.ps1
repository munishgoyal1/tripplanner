#!/usr/bin/env pwsh
[CmdletBinding()]
param(
	[Parameter(Position = 0)]
	[ValidateSet("all")]
	[string]$Target,

	[Alias("All")]
	[switch]$AllWorktrees,

	[switch]$ValidateOnly,
	[int]$ApiPort = 8000,
	[int]$FrontendPort = 5173,
	[int]$LabsPort = 5175,
	[switch]$BackendOnly,
	[switch]$FrontendOnly,
	[switch]$NoLabs,
	[switch]$Watch,
	[switch]$Logs,
	[ValidateSet("azure", "emulator")]
	[string]$CosmosBackend,
	[switch]$UseCanaryData
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/run-log.ps1"
Start-RunLog -Name "run-latest" | Out-Null
. "$PSScriptRoot/lib/sync-common.ps1"
$syncParameters = @{}
if ($ValidateOnly) {
	$syncParameters.ValidateOnly = $true
}

$syncLogOwned = Start-SyncLog -Component "run-latest"
try {
    if ($Target -eq "all" -or $AllWorktrees) {
        Write-Host "Synchronizing latest committed code into all worktrees..." -ForegroundColor Cyan
        & "$PSScriptRoot\all-worktrees-sync.ps1" @syncParameters
    } else {
        Write-Host "Synchronizing latest committed code into this worktree..." -ForegroundColor Cyan
        & "$PSScriptRoot\sync-latest.ps1" @syncParameters
    }
} finally {
    if ($syncLogOwned) { Stop-SyncLog }
}

if ($ValidateOnly) {
	Write-Host "Ready: synchronization validation completed without starting the local stack."
	return
}

$devSpaParameters = @{}
foreach ($name in @(
	"ApiPort",
	"FrontendPort",
	"LabsPort",
	"BackendOnly",
	"FrontendOnly",
	"NoLabs",
	"Watch",
	"Logs",
	"CosmosBackend",
	"UseCanaryData"
)) {
	if ($PSBoundParameters.ContainsKey($name)) {
		$devSpaParameters[$name] = $PSBoundParameters[$name]
	}
}

Write-Host "Starting the latest local dev stack with dev-spa.ps1..." -ForegroundColor Cyan
& "$PSScriptRoot\dev-spa.ps1" @devSpaParameters