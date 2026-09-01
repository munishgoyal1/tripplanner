#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [Parameter(Mandatory)][ValidateSet("preflight", "inventory", "provision", "data", "validate", "cutover", "retire")][string]$Phase,
    [Parameter(Mandatory)][string]$RunId,
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
$migrationRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $migrationRoot "../..")
. "$migrationRoot/common.ps1"

$config = Read-MigrationConfig -Path $ConfigPath
$google = $config.google
$source = $google.source
$target = $google.target
$projects = @($google.projects)

function Invoke-GcloudMigration {
    param(
        [Parameter(Mandatory)][string]$Account,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Description,
        [switch]$Capture
    )
    return Invoke-CheckedCommand -Executable "gcloud" `
        -Arguments ($Arguments + @("--account=$Account")) `
        -Description $Description -Capture:$Capture
}

function Get-GcloudJson {
    param(
        [Parameter(Mandatory)][string]$Account,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Description
    )
    $raw = Invoke-GcloudMigration -Account $Account -Arguments ($Arguments + @("--format=json")) `
        -Description $Description -Capture
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    return $raw | ConvertFrom-Json
}

function Get-ProjectBillingAccount {
    param([Parameter(Mandatory)][string]$Project, [Parameter(Mandatory)][string]$Account)
    return Invoke-GcloudMigration -Account $Account -Capture -Description "read billing for $Project" -Arguments @(
        "beta", "billing", "projects", "describe", $Project,
        "--format=value(billingAccountName)"
    )
}

function Assert-GoogleConfig {
    foreach ($name in @("source.account", "source.billingAccount", "target.account", "target.billingAccount")) {
        $segments = $name.Split('.')
        Assert-ConfiguredValue "google.$name" $google.($segments[0]).($segments[1])
    }
    if ($source.account -ieq $target.account -or $source.billingAccount -eq $target.billingAccount) {
        throw "Google source and target accounts and billing accounts must be different."
    }
    if (@($source.account, $target.account) -icontains "mugoy@microsoft.com") {
        throw "The prohibited work identity must not appear in migration configuration."
    }
    if ($projects.Count -eq 0) { throw "google.projects must list every Tripplanner project." }
}

function Get-ProjectPolicy {
    param([Parameter(Mandatory)][string]$Project, [Parameter(Mandatory)][string]$Account)
    return Get-GcloudJson -Account $Account -Description "read IAM for $Project" -Arguments @(
        "projects", "get-iam-policy", $Project
    )
}

function Test-ProjectMemberRole {
    param($Policy, [string]$Member, [string]$Role)
    return @($Policy.bindings | Where-Object {
        $_.role -eq $Role -and $Member -in @($_.members)
    }).Count -gt 0
}

Assert-CommandAvailable "gcloud"
Assert-GoogleConfig

switch ($Phase) {
    "preflight" {
        $authenticatedRaw = Invoke-GcloudMigration -Account $source.account -Capture `
            -Description "list authenticated Google accounts" -Arguments @("auth", "list", "--format=value(account)")
        $authenticated = @($authenticatedRaw -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        foreach ($account in @($source.account, $target.account)) {
            if ($authenticated -notcontains $account) { throw "Google account '$account' is not authenticated in gcloud." }
        }
        $billingAccounts = @(Get-GcloudJson -Account $target.account -Description "list target billing accounts" -Arguments @(
            "billing", "accounts", "list"
        ))
        if ($target.billingAccount -notin @($billingAccounts.name -replace '^billingAccounts/', '')) {
            throw "Target billing account $($target.billingAccount) is not visible to $($target.account)."
        }
        $projectEvidence = @()
        foreach ($project in $projects) {
            $details = Get-GcloudJson -Account $source.account -Description "inspect $project" -Arguments @(
                "projects", "describe", $project
            )
            $projectEvidence += [ordered]@{ project = $project; number = $details.projectNumber; state = $details.lifecycleState }
        }
        Write-MigrationCheckpoint $EvidenceDirectory "preflight" ([ordered]@{
            sourceAccount = $source.account
            targetAccount = $target.account
            targetBillingAccount = $target.billingAccount
            projects = $projectEvidence
        })
    }
    "inventory" {
        Assert-MigrationCheckpoint $EvidenceDirectory "preflight"
        $inventory = @()
        foreach ($project in $projects) {
            $inventory += [ordered]@{
                project = $project
                billingAccount = Get-ProjectBillingAccount $project $source.account
                iam = Get-ProjectPolicy $project $source.account
                enabledServices = @(Invoke-GcloudMigration -Account $source.account -Capture `
                    -Description "list enabled services for $project" -Arguments @(
                        "services", "list", "--enabled", "--project=$project", "--format=value(config.name)"
                    ))
                apiKeys = @(Get-GcloudJson -Account $source.account -Description "inventory API keys for $project" -Arguments @(
                    "services", "api-keys", "list", "--project=$project"
                ))
            }
        }
        Write-MigrationJson (Join-Path $EvidenceDirectory "source-projects.json") $inventory
        Write-MigrationCheckpoint $EvidenceDirectory "inventory" ([ordered]@{ projectCount = $projects.Count })
    }
    "provision" {
        Assert-MigrationCheckpoint $EvidenceDirectory "inventory"
        Assert-Approval $Approval "APPROVE_TARGET_PROVISIONING" "Google target ownership grant"
        if ($WhatIfPreference) { Write-Host "Would grant the target principal ownership of each configured Google project."; break }
        foreach ($project in $projects) {
            Invoke-GcloudMigration -Account $source.account -Description "grant target owner on $project" -Arguments @(
                "projects", "add-iam-policy-binding", $project,
                "--member=user:$($target.account)", "--role=roles/owner", "--quiet"
            )
        }
        Write-MigrationCheckpoint $EvidenceDirectory "provision" ([ordered]@{
            targetPrincipal = $target.account
            role = "roles/owner"
            projects = $projects
        })
    }
    "data" {
        Assert-MigrationCheckpoint $EvidenceDirectory "provision"
        Write-MigrationCheckpoint $EvidenceDirectory "data" ([ordered]@{
            mode = "project-transfer-in-place"
            detail = "Project-contained resources and data retain their project IDs; no data-plane copy is required."
        })
    }
    "validate" {
        Assert-MigrationCheckpoint $EvidenceDirectory "data"
        foreach ($project in $projects) {
            $policy = Get-ProjectPolicy $project $target.account
            if (-not (Test-ProjectMemberRole $policy "user:$($target.account)" "roles/owner")) {
                throw "Target account is not an owner of $project."
            }
        }
        Write-MigrationCheckpoint $EvidenceDirectory "validate" ([ordered]@{
            targetOwnerVerified = $true
            projects = $projects
        })
    }
    "cutover" {
        Assert-MigrationCheckpoint $EvidenceDirectory "validate"
        Assert-Approval $Approval "APPROVE_CLOUD_CUTOVER" "Google billing cutover"
        if ($WhatIfPreference) { Write-Host "Would move configured projects and link them to target billing."; break }
        foreach ($project in $projects) {
            if (-not [string]::IsNullOrWhiteSpace([string]$target.organizationId)) {
                Invoke-GcloudMigration -Account $target.account -Description "move $project to target organization" -Arguments @(
                    "beta", "projects", "move", $project, "--organization=$($target.organizationId)", "--quiet"
                )
            }
            Invoke-GcloudMigration -Account $target.account -Description "link $project to target billing" -Arguments @(
                "beta", "billing", "projects", "link", $project,
                "--billing-account=$($target.billingAccount)"
            )
        }
        $guardrails = Get-Content (Join-Path $repoRoot "infra/billing-guardrails.json") -Raw | ConvertFrom-Json
        $guardrails.alertEmail = $target.account
        $guardrails.gcp.billingAccount = $target.billingAccount
        $runtimeConfig = Join-Path $EvidenceDirectory "target-billing-guardrails.json"
        Write-MigrationJson $runtimeConfig $guardrails
        $previousAccount = $env:CLOUDSDK_CORE_ACCOUNT
        try {
            $env:CLOUDSDK_CORE_ACCOUNT = $target.account
            & (Join-Path $repoRoot "infra/gcp/apply-billing-guardrails.ps1") `
                -ConfigPath $runtimeConfig -GooglePlacesApproval APPROVE_GOOGLE_PLACES_SPEND `
                -GoogleMapsApproval APPROVE_GOOGLE_MAPS_SPEND
            if ($LASTEXITCODE -ne 0) { throw "Target Google billing guardrails failed." }
        } finally {
            $env:CLOUDSDK_CORE_ACCOUNT = $previousAccount
        }
        foreach ($project in $projects) {
            $billing = Get-ProjectBillingAccount $project $target.account
            if ($billing -notmatch [regex]::Escape($target.billingAccount)) {
                throw "$project is not linked to target billing."
            }
        }
        Write-MigrationCheckpoint $EvidenceDirectory "cutover" ([ordered]@{
            targetBillingAccount = $target.billingAccount
            projects = $projects
            guardrails = $runtimeConfig
        })
    }
    "retire" {
        Assert-MigrationCheckpoint $EvidenceDirectory "cutover"
        Assert-Approval $Approval "APPROVE_SOURCE_RETIREMENT" "Google source retirement"
        if ($WhatIfPreference) { Write-Host "Would remove source IAM and configured budgets after verifying target billing."; break }
        foreach ($project in $projects) {
            $billing = Get-ProjectBillingAccount $project $target.account
            if ($billing -notmatch [regex]::Escape($target.billingAccount)) {
                throw "Refusing source IAM removal while $project is not on target billing."
            }
            if ([bool]$google.removeSourcePrincipalOnRetire) {
                $policy = Get-ProjectPolicy $project $target.account
                foreach ($binding in @($policy.bindings | Where-Object {
                    "user:$($source.account)" -in @($_.members)
                })) {
                    Invoke-GcloudMigration -Account $target.account -Description "remove source $($binding.role) from $project" -Arguments @(
                        "projects", "remove-iam-policy-binding", $project,
                        "--member=user:$($source.account)", "--role=$($binding.role)", "--quiet"
                    )
                }
            }
        }
        if ([bool]$google.deleteSourceBudgetsOnRetire) {
            $configured = Get-Content (Join-Path $repoRoot "infra/billing-guardrails.json") -Raw | ConvertFrom-Json
            $budgetNames = @($configured.gcp.globalBudget.name) + @($configured.gcp.environments.budgetName)
            $budgets = @(Get-GcloudJson -Account $source.account -Description "list source budgets" -Arguments @(
                "billing", "budgets", "list", "--billing-account=$($source.billingAccount)"
            ))
            foreach ($budget in @($budgets | Where-Object { $_.displayName -in $budgetNames })) {
                $budgetId = ([string]$budget.name).Split('/')[-1]
                Invoke-GcloudMigration -Account $source.account -Description "delete source budget $($budget.displayName)" -Arguments @(
                    "billing", "budgets", "delete", $budgetId,
                    "--billing-account=$($source.billingAccount)", "--quiet"
                )
            }
        }
        Write-MigrationCheckpoint $EvidenceDirectory "retire" ([ordered]@{
            sourcePrincipalRemoved = [bool]$google.removeSourcePrincipalOnRetire
            sourceBudgetsDeleted = [bool]$google.deleteSourceBudgetsOnRetire
            manualAction = "Close the old Google billing account if it has no unrelated projects or obligations."
        })
    }
}