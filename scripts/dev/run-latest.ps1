#!/usr/bin/env pwsh
[CmdletBinding()]
param(
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
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$branch = (& git -C $repoRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "master") {
	throw "Run-Latest is for the primary master checkout. Use a sandbox launcher for isolated work."
}

Write-Host "Synchronizing master with origin/master..." -ForegroundColor Cyan
& git -C $repoRoot fetch -q origin master
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/master." }
if (-not $ValidateOnly) {
	& git -C $repoRoot merge --ff-only origin/master
	if ($LASTEXITCODE -ne 0) { throw "Could not fast-forward master to origin/master." }
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