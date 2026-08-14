#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Inspect, maintain, restore, or tear down the local debug trip store.

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

$candidates = @(
    (Join-Path $repoRoot ".venv/bin/python"),
    (Join-Path $repoRoot ".venv/Scripts/python.exe")
)
$python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    $python = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    throw "No Python interpreter found. Create the repository virtual environment first."
}

$cli = Join-Path $PSScriptRoot "debug_store_cli.py"
& $python $cli $Command @Rest
exit $LASTEXITCODE
