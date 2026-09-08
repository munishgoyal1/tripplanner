#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Inspect, maintain, restore, or tear down the local Trip Flight Recorder.

.DESCRIPTION
  Thin dispatcher over scripts/dev/debug_store_cli.py using the repository
  virtual environment when one is present.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("show", "maintain", "restore", "clear")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

. (Join-Path $PSScriptRoot "lib/python-runtime.ps1")
$python = (Resolve-TripplannerPython -RepoRoot $repoRoot).Python

$cli = Join-Path $PSScriptRoot "debug_store_cli.py"
& $python $cli $Command @Rest
exit $LASTEXITCODE
