#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Move all projects, resources, and billing control from one Google account to another.

.DESCRIPTION
  The workflow preserves projects in place so project IDs, project numbers, resources,
  OAuth clients, API keys, and project-level quotas do not change. It discovers every
  project linked to the source billing account; no project is silently left billable.

  Plan is read-only. Grant, Cutover, and Retire require separate exact approvals.
  GA4 property transfer, target payment-profile setup, and final source billing-account
  closure are Google Console actions and are represented as explicit checkpoints.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet("Plan", "Grant", "Cutover", "Verify", "Retire", "Migrate", "All")]
    [string]$Phase = "Plan",
    [string]$ManifestPath = "$PSScriptRoot/google-account-migration.json",
    [string]$GrantApproval = "",
    [string]$CutoverApproval = "",
    [string]$RetireApproval = "",
    [string]$ManualCompletionApproval = "",
    [string]$SourceGcloudConfiguration = "",
    [string]$TargetGcloudConfiguration = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/google-migration-common.ps1"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud is not on PATH. Install the Google Cloud SDK first."
}

$manifest = Read-GoogleMigrationManifest -Path $ManifestPath

function Select-GcloudConfiguration {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$ExpectedPrincipal
    )

    Invoke-GcloudMigration @("config", "configurations", "activate", $Name, "--quiet") | Out-Null
    Assert-ActiveGooglePrincipal -Expected $ExpectedPrincipal
}

function Invoke-Plan {
    Assert-ActiveGooglePrincipal -Expected $manifest.source.principal
    $allProjects = @(Get-SourceBillingProjects -Manifest $manifest -IncludeExcluded)
    $projects = @($allProjects | Where-Object {
        $_.projectId -notin @($manifest.projectSelection.excludeProjectIds)
    })
    if ($projects.Count -eq 0) {
        throw "No projects were found on source billing account $($manifest.source.billingAccount)."
    }
    $existingIds = @(Get-ExistingMigrationProjectIds `
        -Manifest $manifest -ManifestPath $ManifestPath)
    $projectIds = @(@($projects.projectId) + $existingIds | Sort-Object -Unique)
    $states = @($projectIds | ForEach-Object { Get-ProjectMigrationState -ProjectId $_ })
    $checkpoint = Write-MigrationProjectCheckpoint `
        -Manifest $manifest -ManifestPath $ManifestPath -ProjectIds @($states.projectId)
    $knownIds = @($manifest.knownProjects.id)
    $body = [ordered]@{
        sourceOrganization = $manifest.source.organization
        sourceBillingAccount = $manifest.source.billingAccount
        targetOrganization = $manifest.target.organization
        targetBillingAccount = $manifest.target.billingAccount
        projects = $states
        discoveredProjectIds = @($states.projectId)
        inaccessibleProjectIds = @($states | Where-Object { -not $_.accessible } | ForEach-Object { $_.projectId })
        additionalProjectIds = @($states.projectId | Where-Object { $_ -notin $knownIds })
        excludedSourceBilledProjectIds = @($allProjects.projectId | Where-Object {
            $_ -in @($manifest.projectSelection.excludeProjectIds)
        })
        projectCheckpoint = $checkpoint
        manualCheckpoints = @(
            "Create the target billing account and payment profile.",
            "Grant the target principal access to its target organization and billing account.",
            "Move GA4 property '$($manifest.analytics.propertyName)' without changing measurement ID $($manifest.analytics.measurementId).",
            "Close the source billing account in Google Console after Retire succeeds."
        )
    }
    Write-MigrationReport -Manifest $manifest -Phase "Plan" -Body $body -ManifestPath $ManifestPath
}

function Invoke-Grant {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    Assert-ActiveGooglePrincipal -Expected $manifest.source.principal
    if ($GrantApproval -cne "GRANT_GOOGLE_MIGRATION_CONTROL") {
        throw "Grant requires -GrantApproval GRANT_GOOGLE_MIGRATION_CONTROL."
    }
    $projects = @(Get-SourceBillingProjects -Manifest $manifest)
    $states = @($projects | ForEach-Object { Get-ProjectMigrationState -ProjectId $_.projectId })
    Assert-ProjectsAccessible -States $states
    $checkpointIds = @(Get-MigrationProjectIds -Manifest $manifest -ManifestPath $ManifestPath)
    if (@($projects.projectId | Where-Object { $_ -notin $checkpointIds }).Count -gt 0) {
        throw "Source billing gained a project after Plan. Rerun Plan before granting access."
    }
    foreach ($state in $states) {
        foreach ($role in @(
            "roles/iam.serviceAccountViewer",
            "roles/oauthconfig.editor",
            "roles/resourcemanager.projectIamAdmin",
            "roles/serviceusage.apiKeysAdmin"
        )) {
            if ($PSCmdlet.ShouldProcess($state.projectId, "Grant target principal $role")) {
                Invoke-GcloudMigration @(
                    "projects", "add-iam-policy-binding", $state.projectId,
                    "--member=user:$($manifest.target.principal)",
                    "--role=$role", "--quiet"
                ) | Out-Null
            }
        }
    }
    foreach ($environment in $manifest.knownProjects | Where-Object { $_.environment -ne "ops" }) {
        foreach ($role in @("roles/cloudquotas.admin", "roles/monitoring.editor")) {
            if ($PSCmdlet.ShouldProcess($environment.projectId, "Grant target principal $role")) {
                Invoke-GcloudMigration @(
                    "projects", "add-iam-policy-binding", $environment.projectId,
                    "--member=user:$($manifest.target.principal)",
                    "--role=$role", "--quiet"
                ) | Out-Null
            }
        }
    }
    $opsProject = @($manifest.knownProjects | Where-Object { $_.environment -eq "ops" })[0].projectId
    foreach ($role in @(
        "roles/iam.serviceAccountAdmin",
        "roles/pubsub.admin",
        "roles/serviceusage.serviceUsageConsumer"
    )) {
        if ($PSCmdlet.ShouldProcess($opsProject, "Grant target principal $role")) {
            Invoke-GcloudMigration @(
                "projects", "add-iam-policy-binding", $opsProject,
                "--member=user:$($manifest.target.principal)",
                "--role=$role", "--quiet"
            ) | Out-Null
        }
    }
    foreach ($state in $states | Where-Object {
        $null -eq $_.parent -or [string]$_.parent.id -ne [string]$manifest.source.organization
    }) {
        foreach ($role in @("roles/resourcemanager.projectMover")) {
            if ($PSCmdlet.ShouldProcess($state.projectId, "Grant target principal $role")) {
                Invoke-GcloudMigration @(
                    "projects", "add-iam-policy-binding", $state.projectId,
                    "--member=user:$($manifest.target.principal)",
                    "--role=$role", "--quiet"
                ) | Out-Null
            }
        }
    }
    if ($PSCmdlet.ShouldProcess($manifest.source.billingAccount, "Grant target billing administrator")) {
        Invoke-GcloudMigration @(
            "beta", "billing", "accounts", "add-iam-policy-binding",
            $manifest.source.billingAccount, "--member=user:$($manifest.target.principal)",
            "--role=roles/billing.admin", "--quiet"
        ) | Out-Null
    }
    foreach ($role in @(
        "roles/resourcemanager.organizationAdmin",
        "roles/resourcemanager.projectMover",
        "roles/resourcemanager.projectCreator",
        "roles/billing.admin",
        "roles/serviceusage.serviceUsageAdmin"
    )) {
        if ($PSCmdlet.ShouldProcess($manifest.source.organization, "Grant target $role")) {
            Invoke-GcloudMigration @(
                "organizations", "add-iam-policy-binding", $manifest.source.organization,
                "--member=user:$($manifest.target.principal)", "--role=$role", "--quiet"
            ) | Out-Null
        }
    }
    $body = [ordered]@{
        migrationProjects = @($projects.projectId)
        targetPrincipal = $manifest.target.principal
        accessMode = "Source organization Project Mover plus billing administrator"
        next = "Sign in as the target principal, configure target organization and billing, then run Cutover."
    }
    Write-MigrationReport -Manifest $manifest -Phase "Grant" -Body $body -ManifestPath $ManifestPath
}

function New-TargetGuardrailsConfig {
    Assert-TargetConfigured -Manifest $manifest
    $sourcePath = Resolve-ManifestRelativePath -ManifestPath $ManifestPath -RelativePath $manifest.guardrailsConfig
    $config = Get-Content -Raw -Path $sourcePath | ConvertFrom-Json
    $config.alertEmail = $manifest.target.alertEmail
    $config.gcp.billingAccount = $manifest.target.billingAccount
    $temporaryPath = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-target-billing-guardrails.json"
    $config | ConvertTo-Json -Depth 20 | Set-Content -Path $temporaryPath -Encoding utf8
    return $temporaryPath
}

function Set-RepositoryTargetConfiguration {
    $configPath = Resolve-ManifestRelativePath `
        -ManifestPath $ManifestPath -RelativePath $manifest.guardrailsConfig
    $config = Get-Content -Raw -Path $configPath | ConvertFrom-Json
    $config.alertEmail = $manifest.target.alertEmail
    $config.gcp.operatorAccount = $manifest.target.principal
    $config.gcp.billingAccount = $manifest.target.billingAccount
    $temporaryPath = "$configPath.migration.tmp"
    try {
        $config | ConvertTo-Json -Depth 20 | Set-Content -Path $temporaryPath -Encoding utf8
        $written = Get-Content -Raw -Path $temporaryPath | ConvertFrom-Json
        if ($written.alertEmail -ne $manifest.target.alertEmail -or
            $written.gcp.operatorAccount -ne $manifest.target.principal -or
            $written.gcp.billingAccount -ne $manifest.target.billingAccount) {
            throw "Target repository configuration verification failed."
        }
        Move-Item -Path $temporaryPath -Destination $configPath -Force
    } finally {
        Remove-Item $temporaryPath -ErrorAction SilentlyContinue
    }
    Write-Host "Updated repository GCP ownership configuration: $configPath"
}

function Invoke-Cutover {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    Assert-TargetConfigured -Manifest $manifest
    Assert-ActiveGooglePrincipal -Expected $manifest.target.principal
    if ($CutoverApproval -cne "MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING") {
        throw "Cutover requires -CutoverApproval MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING."
    }
    Invoke-GcloudMigration @(
        "beta", "billing", "accounts", "describe", $manifest.target.billingAccount,
        "--format=value(open)"
    ) | Out-Null
    $projects = @(Get-SourceBillingProjects -Manifest $manifest)
    $checkpointIds = @(Get-MigrationProjectIds -Manifest $manifest -ManifestPath $ManifestPath)
    $newSourceIds = @(
        $projects | ForEach-Object { $_.projectId } | Where-Object { $_ -notin $checkpointIds }
    )
    if ($newSourceIds.Count -gt 0) {
        throw "Source billing gained projects after Plan: $($newSourceIds -join ', '). Rerun Plan."
    }
    $states = @($checkpointIds | ForEach-Object { Get-ProjectMigrationState -ProjectId $_ })
    Assert-ProjectsAccessible -States $states
    $unexpectedBilling = @($states | Where-Object {
        $_.billingAccount -notin @($manifest.source.billingAccount, $manifest.target.billingAccount)
    })
    if ($unexpectedBilling.Count -gt 0) {
        throw "Checkpoint projects use an unexpected billing account: $($unexpectedBilling.projectId -join ', ')."
    }
    # Projects are moved and relinked, never recreated or deleted, so their IDs,
    # OAuth clients, API keys, resources, data, and project quotas remain intact.
    foreach ($state in $states) {
        if ($null -eq $state.parent -or
            [string]$state.parent.id -ne [string]$manifest.target.organization) {
            if ($PSCmdlet.ShouldProcess($state.projectId, "Move project to target organization")) {
                Invoke-GcloudMigration @(
                    "beta", "projects", "move", $state.projectId,
                    "--organization=$($manifest.target.organization)", "--quiet"
                ) | Out-Null
            }
        }
        if ($state.billingAccount -ne $manifest.target.billingAccount -and
            $PSCmdlet.ShouldProcess($state.projectId, "Link target billing account")) {
            Invoke-GcloudMigration @(
            "beta", "billing", "projects", "link", $state.projectId,
                "--billing-account=$($manifest.target.billingAccount)", "--quiet"
            ) | Out-Null
        }
    }

    $targetConfig = New-TargetGuardrailsConfig
    try {
        $applyScript = Resolve-ManifestRelativePath -ManifestPath $ManifestPath -RelativePath "../../gcp/apply-billing-guardrails.ps1"
        if ($PSCmdlet.ShouldProcess($manifest.target.billingAccount, "Recreate budgets, quotas, key restrictions, and alerts")) {
            & $applyScript -ConfigPath $targetConfig `
                -GoogleMapsApproval APPROVE_GOOGLE_MAPS_SPEND `
                -GooglePlacesApproval APPROVE_GOOGLE_PLACES_SPEND
            if ($LASTEXITCODE -ne 0) { throw "Target billing guardrail apply failed." }
        }
    } finally {
        Remove-Item $targetConfig -ErrorAction SilentlyContinue
    }
    Invoke-Verify
    if ($PSCmdlet.ShouldProcess("repository guardrail configuration", "Record target Google ownership")) {
        Set-RepositoryTargetConfiguration
    }
}

function Invoke-Verify {
    Assert-TargetConfigured -Manifest $manifest
    Assert-ActiveGooglePrincipal -Expected $manifest.target.principal
    $projectIds = @(Get-MigrationProjectIds -Manifest $manifest -ManifestPath $ManifestPath)
    $allSourceProjects = @(Get-SourceBillingProjects -Manifest $manifest -IncludeExcluded)
    $sourceProjects = @($allSourceProjects | Where-Object {
        $_.projectId -notin @($manifest.projectSelection.excludeProjectIds)
    })
    $states = @($projectIds | ForEach-Object { Get-ProjectMigrationState -ProjectId $_ })
    $failures = @()
    foreach ($state in $states) {
        if (-not $state.accessible) {
            $failures += "$($state.projectId) is not accessible to the target principal."
            continue
        }
        if ($null -eq $state.parent -or
            [string]$state.parent.id -ne [string]$manifest.target.organization) {
            $failures += "$($state.projectId) is not in target organization."
        }
        if ($state.billingAccount -ne $manifest.target.billingAccount -or -not $state.billingEnabled) {
            $failures += "$($state.projectId) is not enabled on target billing."
        }
    }
    if ($sourceProjects.Count -gt 0) {
        $sourceProjectIds = @($sourceProjects | ForEach-Object { $_.projectId })
        $failures += "Source billing still funds: $($sourceProjectIds -join ', ')."
    }
    $body = [ordered]@{
        passed = $failures.Count -eq 0
        failures = $failures
        projects = $states
        sourceBillingProjects = @($sourceProjects | ForEach-Object { $_.projectId })
        excludedSourceBillingProjects = @(
            $allSourceProjects |
                ForEach-Object { $_.projectId } |
                Where-Object { $_ -in @($manifest.projectSelection.excludeProjectIds) }
        )
    }
    Write-MigrationReport -Manifest $manifest -Phase "Verify" -Body $body -ManifestPath $ManifestPath
    if ($failures.Count -gt 0) { throw ($failures -join "`n") }
}

function Invoke-Retire {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    Assert-TargetConfigured -Manifest $manifest
    Assert-ActiveGooglePrincipal -Expected $manifest.target.principal
    if ($RetireApproval -cne "RETIRE_OLD_GOOGLE_ACCOUNT") {
        throw "Retire requires -RetireApproval RETIRE_OLD_GOOGLE_ACCOUNT."
    }
    if ($ManualCompletionApproval -cne "CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED") {
        throw "Confirm the GA4 property and target payments profile first with -ManualCompletionApproval CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED."
    }
    Invoke-Verify
    $projectIds = @(Get-MigrationProjectIds -Manifest $manifest -ManifestPath $ManifestPath)
    foreach ($projectId in $projectIds) {
        if ($PSCmdlet.ShouldProcess($projectId, "Remove source principal project owner")) {
            Invoke-GcloudMigration @(
                "projects", "remove-iam-policy-binding", $projectId,
                "--member=user:$($manifest.source.principal)", "--role=roles/owner", "--all", "--quiet"
            ) | Out-Null
        }
    }
    foreach ($role in @(
        "roles/resourcemanager.organizationAdmin", "roles/resourcemanager.projectMover",
        "roles/resourcemanager.projectCreator", "roles/billing.admin",
        "roles/billing.creator", "roles/serviceusage.serviceUsageAdmin",
        "roles/iam.workforcePoolAdmin"
    )) {
        if ($PSCmdlet.ShouldProcess($manifest.source.organization, "Remove source principal $role")) {
            Invoke-GcloudMigration @(
                "organizations", "remove-iam-policy-binding", $manifest.source.organization,
                "--member=user:$($manifest.source.principal)", "--role=$role", "--all", "--quiet"
            ) -AllowFailure | Out-Null
        }
    }
    if ($PSCmdlet.ShouldProcess($manifest.source.billingAccount, "Remove source billing administrator")) {
        Invoke-GcloudMigration @(
            "beta", "billing", "accounts", "remove-iam-policy-binding",
            $manifest.source.billingAccount, "--member=user:$($manifest.source.principal)",
            "--role=roles/billing.admin", "--all", "--quiet"
        ) | Out-Null
    }
    $budgets = Invoke-GcloudMigration @(
        "billing", "budgets", "list", "--billing-account=$($manifest.source.billingAccount)",
        "--format=value(name)"
    )
    $deletedBudgets = @()
    foreach ($budget in @($budgets -split "`n" | Where-Object { $_ -match "/budgets/" })) {
        $budgetId = ($budget -split "/")[-1]
        if ($PSCmdlet.ShouldProcess($budget, "Delete obsolete source billing budget")) {
            Invoke-GcloudMigration @(
                "billing", "budgets", "delete", $budgetId,
                "--billing-account=$($manifest.source.billingAccount)", "--quiet"
            ) | Out-Null
            $deletedBudgets += $budget
        }
    }
    $remainingExcluded = @(Get-SourceBillingProjects -Manifest $manifest -IncludeExcluded |
        Where-Object { $_.projectId -in @($manifest.projectSelection.excludeProjectIds) })
    $body = [ordered]@{
        retiredPrincipal = $manifest.source.principal
        retiredProjects = $projectIds
        sourceBillingProjects = @($remainingExcluded.projectId)
        sourceBudgetsDeleted = $deletedBudgets
        manualFinalAction = "Close source billing account $($manifest.source.billingAccount) in Google Cloud Console. gcloud has no billing-account close command."
        chargingRisk = "Only owner-approved excluded projects may remain linked. Close or unlink them separately before closing the source billing account."
    }
    Write-MigrationReport -Manifest $manifest -Phase "Retire" -Body $body -ManifestPath $ManifestPath
}

switch ($Phase) {
    "Plan" { Invoke-Plan }
    "Grant" { Invoke-Grant }
    "Cutover" { Invoke-Cutover }
    "Verify" { Invoke-Verify }
    "Retire" { Invoke-Retire }
    "Migrate" {
        if ([string]::IsNullOrWhiteSpace($SourceGcloudConfiguration) -or
            [string]::IsNullOrWhiteSpace($TargetGcloudConfiguration)) {
            throw "Migrate requires -SourceGcloudConfiguration and -TargetGcloudConfiguration."
        }
        Assert-TargetConfigured -Manifest $manifest
        if ($GrantApproval -cne "GRANT_GOOGLE_MIGRATION_CONTROL" -or
            $CutoverApproval -cne "MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING") {
            throw "Migrate requires Grant and Cutover approvals."
        }
        Select-GcloudConfiguration `
            -Name $SourceGcloudConfiguration -ExpectedPrincipal $manifest.source.principal
        Invoke-Plan
        Invoke-Grant
        Select-GcloudConfiguration `
            -Name $TargetGcloudConfiguration -ExpectedPrincipal $manifest.target.principal
        Invoke-Cutover
    }
    "All" {
        if ([string]::IsNullOrWhiteSpace($SourceGcloudConfiguration) -or
            [string]::IsNullOrWhiteSpace($TargetGcloudConfiguration)) {
            throw "All requires -SourceGcloudConfiguration and -TargetGcloudConfiguration."
        }
        Assert-TargetConfigured -Manifest $manifest
        if ($GrantApproval -cne "GRANT_GOOGLE_MIGRATION_CONTROL" -or
            $CutoverApproval -cne "MOVE_ALL_GOOGLE_PROJECTS_AND_BILLING" -or
            $RetireApproval -cne "RETIRE_OLD_GOOGLE_ACCOUNT" -or
            $ManualCompletionApproval -cne "CONFIRM_GA4_AND_PAYMENTS_TRANSFERRED") {
            throw "All requires every phase approval, including confirmed GA4 and payments transfer."
        }
        Select-GcloudConfiguration `
            -Name $SourceGcloudConfiguration -ExpectedPrincipal $manifest.source.principal
        Invoke-Plan
        Invoke-Grant
        Select-GcloudConfiguration `
            -Name $TargetGcloudConfiguration -ExpectedPrincipal $manifest.target.principal
        Invoke-Cutover
        Invoke-Retire
    }
}