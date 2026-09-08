#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Run every trip rule over the local corpus and report what is new.

.DESCRIPTION
  Thin dispatcher over scripts/dev/trip_audit.py using the repository virtual
  environment when one is present. Reads stored trips only: no model calls, no
  provider calls, no writes to any trip.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

. (Join-Path $PSScriptRoot "lib/python-runtime.ps1")
$runtime = Resolve-TripplannerPython -RepoRoot $repoRoot
$python = $runtime.Python
$primaryRoot = $runtime.PrimaryRoot

if ($repoRoot -ne $primaryRoot) {
    $sourceEnv = Join-Path $primaryRoot ".env"
    if (Test-Path $sourceEnv -PathType Leaf) {
        Copy-Item -LiteralPath $sourceEnv -Destination (Join-Path $repoRoot ".env") -Force
        Write-Host "[env]     refreshed .env from the primary checkout" -ForegroundColor DarkGray
    } else {
        Write-Warning "The primary checkout has no .env; sandbox credentials were not refreshed."
    }
}

$cli = Join-Path $PSScriptRoot "trip_audit.py"
& $python $cli @Rest
exit $LASTEXITCODE
