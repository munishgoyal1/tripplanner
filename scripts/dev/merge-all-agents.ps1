#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly,

    [switch]$ResolveConflicts
)

$ErrorActionPreference = "Stop"
$mergeWorker = Join-Path $PSScriptRoot "merge-worker.ps1"

Write-Host "Preflighting Agent 1 and Agent 2..." -ForegroundColor Cyan
& $mergeWorker -WorkerNumber 1 -ValidateOnly
& $mergeWorker -WorkerNumber 2 -ValidateOnly

if ($ValidateOnly) {
    Write-Host "Ready: both agents can be integrated sequentially."
    return
}

Write-Host "Integrating Agent 1..." -ForegroundColor Cyan
& $mergeWorker -WorkerNumber 1 -ResolveConflicts:$ResolveConflicts
Write-Host "Integrating Agent 2..." -ForegroundColor Cyan
& $mergeWorker -WorkerNumber 2 -ResolveConflicts:$ResolveConflicts

Write-Host "Done: Agent 1 and Agent 2 are integrated into master." -ForegroundColor Green