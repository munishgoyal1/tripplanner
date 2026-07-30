#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Write-Host "Merging the latest Agent 1 code..." -ForegroundColor Cyan
& "$PSScriptRoot\merge-agent-1.ps1"

Write-Host "Starting the latest local application..." -ForegroundColor Cyan
& "$repoRoot\scripts\dev-spa.ps1"