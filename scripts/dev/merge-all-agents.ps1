#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$mergeAgent1 = Join-Path $PSScriptRoot "merge-agent-1.ps1"
$mergeAgent2 = Join-Path $PSScriptRoot "merge-agent-2.ps1"

Write-Host "Preflighting Agent 1 and Agent 2..." -ForegroundColor Cyan
& $mergeAgent1 -ValidateOnly
& $mergeAgent2 -ValidateOnly

if ($ValidateOnly) {
    Write-Host "Ready: both agents can be integrated sequentially."
    return
}

Write-Host "Integrating Agent 1..." -ForegroundColor Cyan
& $mergeAgent1
Write-Host "Integrating Agent 2..." -ForegroundColor Cyan
& $mergeAgent2

Write-Host "Done: Agent 1 and Agent 2 are integrated into master." -ForegroundColor Green