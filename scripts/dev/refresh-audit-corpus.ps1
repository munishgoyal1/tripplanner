#!/usr/bin/env pwsh

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

& (Join-Path $PSScriptRoot "build-corpus.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& (Join-Path $PSScriptRoot "trip-audit.ps1")
exit $LASTEXITCODE