#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(1, 2)]
    [int]$WorkerNumber,

    [switch]$ValidateOnly
)

$arguments = @{}
if ($PSBoundParameters.ContainsKey("WorkerNumber")) {
    $arguments.WorkerNumber = $WorkerNumber
}
if ($ValidateOnly) {
    $arguments.ValidateOnly = $true
}

& "$PSScriptRoot\merge-latest-worktrees.ps1" @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
