#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
& "$PSScriptRoot\merge-worker.ps1" -WorkerNumber 2 -ValidateOnly:$ValidateOnly