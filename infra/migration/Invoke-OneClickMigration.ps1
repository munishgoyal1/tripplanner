#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet("Provision", "CopyData", "Migrate")]
    [string]$Operation,
    [string]$ConfigPath = $env:TRIPPLANNER_MIGRATION_CONFIG,
    [string]$GoogleManifestPath = "$PSScriptRoot/google/google-account-migration.json",
    [string]$RunId = "",
    [string]$EvidenceRoot = "",
    [string]$Approval = "",
    [string]$SourceGcloudConfiguration = $env:TRIPPLANNER_SOURCE_GCLOUD_CONFIGURATION,
    [string]$TargetGcloudConfiguration = $env:TRIPPLANNER_TARGET_GCLOUD_CONFIGURATION,
    [switch]$SkipGoogle
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
. "$PSScriptRoot/common.ps1"

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "cloud-account-migration.json"
}
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
    $EvidenceRoot = Join-Path $repoRoot "logs/migration"
}
$config = Read-MigrationConfig -Path $ConfigPath
Assert-ConfiguredValue "azure.target.subscriptionId" $config.azure.target.subscriptionId
if ($Operation -eq "Migrate" -and -not $SkipGoogle) {
    $googleManifest = Read-MigrationConfig -Path $GoogleManifestPath
    if ([string]::IsNullOrWhiteSpace($SourceGcloudConfiguration)) {
        $SourceGcloudConfiguration = [string]$googleManifest.source.gcloudConfiguration
    }
    if ([string]::IsNullOrWhiteSpace($TargetGcloudConfiguration)) {
        $TargetGcloudConfiguration = [string]$googleManifest.target.gcloudConfiguration
    }
}
if ([string]::IsNullOrWhiteSpace($RunId)) {
    $targetSlug = ([string]$config.azure.target.subscriptionId) -replace '[^A-Za-z0-9._-]', '-'
    $RunId = "cloud-account-$targetSlug"
}

$requiredApproval = switch ($Operation) {
    "Provision" { "PROVISION_ALL_CLOUD_INFRASTRUCTURE" }
    "CopyData" { "COPY_ALL_CLOUD_DATA" }
    "Migrate" { "MIGRATE_TO_NEW_AZURE_AND_GOOGLE_ACCOUNTS" }
}
if ([string]::IsNullOrWhiteSpace($Approval)) {
    $Approval = Read-Host "Type $requiredApproval to continue"
}
Assert-Approval $Approval $requiredApproval "$Operation operation"

$azureOrchestrator = Join-Path $PSScriptRoot "Invoke-CloudMigration.ps1"
$googleOrchestrator = Join-Path $PSScriptRoot "google/migrate-google-account.ps1"

function Invoke-AzurePhase {
    param(
        [Parameter(Mandatory)][string]$Phase,
        [string]$PhaseApproval = ""
    )
    & $azureOrchestrator -ConfigPath $ConfigPath -Phase $Phase -Cloud azure `
        -RunId $RunId -EvidenceRoot $EvidenceRoot -Approval $PhaseApproval `
        -Resume -WhatIf:$WhatIfPreference
    if ($LASTEXITCODE -ne 0) { throw "Azure migration phase '$Phase' failed." }
}

function Invoke-AzureProvision {
    Invoke-AzurePhase -Phase preflight
    Invoke-AzurePhase -Phase inventory
    Invoke-AzurePhase -Phase provision -PhaseApproval "APPROVE_TARGET_PROVISIONING"
}

function Invoke-AzureDataCopy {
    Invoke-AzurePhase -Phase data -PhaseApproval "APPROVE_DATA_COPY"
}

switch ($Operation) {
    "Provision" {
        Invoke-AzureProvision
        Write-Host "Google Cloud projects migrate in place, so no Google infrastructure recreation is required."
    }
    "CopyData" {
        Invoke-AzureDataCopy
        Write-Host "Google Cloud project data stays with each in-place project move, so no Google data copy is required."
    }
    "Migrate" {
        if (-not $SkipGoogle -and
            ([string]::IsNullOrWhiteSpace($SourceGcloudConfiguration) -or
             [string]::IsNullOrWhiteSpace($TargetGcloudConfiguration))) {
            throw "Migrate requires source and target gcloud configurations, or -SkipGoogle for Azure-only recovery."
        }

        Invoke-AzureProvision
        Invoke-AzureDataCopy
        Invoke-AzurePhase -Phase validate
        if (-not $SkipGoogle) {
            & $googleOrchestrator -Phase Migrate -ManifestPath $GoogleManifestPath `
                -SourceGcloudConfiguration $SourceGcloudConfiguration `
                -TargetGcloudConfiguration $TargetGcloudConfiguration `
                -GrantApproval "GRANT_GOOGLE_MIGRATION_CONTROL" `
                -CutoverApproval "MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING" `
                -WhatIf:$WhatIfPreference
            if ($LASTEXITCODE -ne 0) { throw "Google account migration failed." }
        }
        Write-Host "Target migration completed and validated. Traffic cutover, source retirement, and billing-account closure remain separate owner actions."
    }
}

Write-Host "$Operation completed. Azure evidence: $EvidenceRoot/$RunId"