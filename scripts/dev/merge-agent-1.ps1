#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

Write-Warning "merge-agent-1.ps1 is retained as an alias; it now integrates both workers."
& "$PSScriptRoot\merge-workers.ps1" -ValidateOnly:$ValidateOnly