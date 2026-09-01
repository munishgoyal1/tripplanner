#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [ValidateSet("preflight", "inventory", "provision", "data", "validate", "cutover", "retire", "all")]
    [string]$Phase = "preflight",
    [ValidateSet("all", "azure", "google")]
    [string]$Cloud = "all",
    [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [string]$EvidenceRoot = "logs/migration",
    [string]$Approval = "",
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/common.ps1"

$config = Read-MigrationConfig -Path $ConfigPath
if ($config.schemaVersion -ne 1) {
    throw "Unsupported migration config schemaVersion '$($config.schemaVersion)'."
}
if ($Cloud -eq "google" -or ($Cloud -eq "all" -and [bool]$config.google.enabled)) {
    throw "Google migration uses infra/migration/google/migrate-google-account.ps1 and its dedicated approvals. Set google.enabled=false for Azure orchestration."
}
if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
    throw "RunId may contain only letters, numbers, dot, underscore, and hyphen."
}
if ($Phase -eq "all" -and -not $Resume) {
    throw "The all phase is resumable by design. Pass -Resume and a stable -RunId after reviewing preflight output."
}

$phases = if ($Phase -eq "all") {
    @("preflight", "inventory", "provision", "data", "validate", "cutover", "retire")
} else {
    @($Phase)
}
$clouds = if ($Cloud -eq "all") { @("azure") } else { @($Cloud) }

foreach ($selectedPhase in $phases) {
    foreach ($selectedCloud in $clouds) {
        if (-not [bool]$config.$selectedCloud.enabled) {
            Write-Host "[$selectedCloud] skipped (disabled in config)"
            continue
        }
        $evidenceDirectory = New-MigrationEvidenceDirectory `
            -Root $EvidenceRoot -Cloud $selectedCloud -RunId $RunId
        if ($Resume -and (Test-Path (Join-Path $evidenceDirectory "$selectedPhase.json"))) {
            Write-Host "[$selectedCloud] $selectedPhase skipped (checkpoint already exists)"
            continue
        }
        $script = Join-Path $PSScriptRoot "$selectedCloud/Invoke-$($selectedCloud.Substring(0, 1).ToUpper())$($selectedCloud.Substring(1))Migration.ps1"
        & $script -ConfigPath $ConfigPath -Phase $selectedPhase `
            -RunId $RunId -EvidenceDirectory $evidenceDirectory `
            -Approval $Approval -WhatIf:$WhatIfPreference
        if ($LASTEXITCODE -ne 0) {
            throw "$selectedCloud migration phase '$selectedPhase' failed."
        }
    }
}

Write-Host "Migration phase '$Phase' completed. Evidence: $EvidenceRoot/$RunId"