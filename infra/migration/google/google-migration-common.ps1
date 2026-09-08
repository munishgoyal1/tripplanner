Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-GcloudMigration {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & gcloud @Arguments 2>&1
    $joined = ($output | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "gcloud $($Arguments -join ' ') failed:`n$joined"
    }
    return $joined
}

function Get-ActiveGooglePrincipal {
    $output = Invoke-GcloudMigration @(
        "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
    )
    $accounts = @($output -split "`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
    if ($accounts.Count -ne 1) {
        throw "Expected exactly one active gcloud account; found $($accounts.Count)."
    }
    return $accounts[0].Trim()
}

function Assert-ActiveGooglePrincipal {
    param([Parameter(Mandatory)][string]$Expected)

    $actual = Get-ActiveGooglePrincipal
    if ($actual -ine $Expected) {
        throw "This phase requires '$Expected', but the active gcloud account is '$actual'."
    }
}

function Read-GoogleMigrationManifest {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path $Path)) { throw "Migration manifest not found: $Path" }
    $manifest = Get-Content -Raw -Path $Path | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1) { throw "Unsupported migration schemaVersion." }
    if ($manifest.projectSelection.mode -ne "all-linked-to-source-billing") {
        throw "projectSelection.mode must be all-linked-to-source-billing."
    }
    if ($manifest.source.principal -ieq $manifest.target.principal) {
        throw "Source and target principals must differ."
    }
    return $manifest
}

function Assert-TargetConfigured {
    param([Parameter(Mandatory)]$Manifest)

    foreach ($value in @($Manifest.target.organization, $Manifest.target.billingAccount)) {
        if ([string]::IsNullOrWhiteSpace($value) -or $value -eq "REQUIRED") {
            throw "Set target.organization and target.billingAccount in the migration manifest first."
        }
    }
    if ($Manifest.target.billingAccount -eq $Manifest.source.billingAccount) {
        throw "Target billing account must differ from the source billing account."
    }
}

function Get-SourceBillingProjects {
    param(
        [Parameter(Mandatory)]$Manifest,
        [switch]$IncludeExcluded
    )

    $raw = Invoke-GcloudMigration @(
        "beta", "billing", "projects", "list",
        "--billing-account=$($Manifest.source.billingAccount)",
        "--format=json(projectId,billingAccountName,billingEnabled,name)"
    )
    $projects = @($raw | ConvertFrom-Json | Where-Object { $_.billingEnabled })
    if (-not $IncludeExcluded) {
        $excluded = @($Manifest.projectSelection.excludeProjectIds)
        $projects = @($projects | Where-Object { $_.projectId -notin $excluded })
    }
    return @($projects | Sort-Object projectId)
}

function Get-ProjectMigrationState {
    param([Parameter(Mandatory)][string]$ProjectId)

    $projectRaw = Invoke-GcloudMigration @(
        "projects", "describe", $ProjectId,
        "--format=json(projectId,projectNumber,name,parent,lifecycleState)"
    ) -AllowFailure
    if ($projectRaw -match "ERROR:") {
        return [ordered]@{
            projectId = $ProjectId
            accessible = $false
            accessError = $projectRaw
        }
    }
    $project = $projectRaw | ConvertFrom-Json
    $billing = Invoke-GcloudMigration @(
        "beta", "billing", "projects", "describe", $ProjectId,
        "--format=json(billingAccountName,billingEnabled)"
    ) | ConvertFrom-Json
    $parent = if ($project.PSObject.Properties.Name -contains "parent") {
        $project.parent
    } else {
        $null
    }
    return [ordered]@{
        projectId = $project.projectId
        accessible = $true
        projectNumber = $project.projectNumber
        name = $project.name
        lifecycleState = $project.lifecycleState
        parent = $parent
        billingAccount = ([string]$billing.billingAccountName -replace "^billingAccounts/", "")
        billingEnabled = [bool]$billing.billingEnabled
    }
}

function Assert-ProjectsAccessible {
    param([Parameter(Mandatory)]$States)

    $inaccessible = @($States | Where-Object { -not $_.accessible })
    if ($inaccessible.Count -gt 0) {
        throw "Restore target/source access to every source-billed project before mutation: $($inaccessible.projectId -join ', ')."
    }
}

function Write-MigrationReport {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$Phase,
        [Parameter(Mandatory)]$Body,
        [Parameter(Mandatory)][string]$ManifestPath
    )

    $base = Split-Path -Parent $ManifestPath
    $directory = Join-Path $base $Manifest.reportDirectory
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $path = Join-Path $directory "$timestamp-$($Phase.ToLowerInvariant()).json"
    $report = [ordered]@{
        schemaVersion = 1
        phase = $Phase
        generatedAt = (Get-Date).ToUniversalTime().ToString("o")
        activePrincipal = Get-ActiveGooglePrincipal
        sourcePrincipal = $Manifest.source.principal
        targetPrincipal = $Manifest.target.principal
        body = $Body
    }
    $report | ConvertTo-Json -Depth 20 | Set-Content -Path $path -Encoding utf8
    Write-Host "Migration report: $path"
    return $path
}

function Get-MigrationReportDirectory {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$ManifestPath
    )

    return Join-Path (Split-Path -Parent $ManifestPath) $Manifest.reportDirectory
}

function Write-MigrationProjectCheckpoint {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$ManifestPath,
        [Parameter(Mandatory)][string[]]$ProjectIds
    )

    $directory = Get-MigrationReportDirectory -Manifest $Manifest -ManifestPath $ManifestPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $path = Join-Path $directory "project-checkpoint.json"
    [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString("o")
        sourceBillingAccount = $Manifest.source.billingAccount
        projectIds = @($ProjectIds | Sort-Object -Unique)
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $path -Encoding utf8
    return $path
}

function Get-MigrationProjectIds {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$ManifestPath
    )

    $directory = Get-MigrationReportDirectory -Manifest $Manifest -ManifestPath $ManifestPath
    $path = Join-Path $directory "project-checkpoint.json"
    if (-not (Test-Path $path)) {
        throw "Project checkpoint not found. Run Plan from the source account before continuing."
    }
    $checkpoint = Get-Content -Raw -Path $path | ConvertFrom-Json
    if ($checkpoint.sourceBillingAccount -ne $Manifest.source.billingAccount) {
        throw "Project checkpoint belongs to a different source billing account."
    }
    $projectIds = @($checkpoint.projectIds | Sort-Object -Unique)
    if ($projectIds.Count -eq 0) { throw "Project checkpoint is empty." }
    return $projectIds
}

function Get-ExistingMigrationProjectIds {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$ManifestPath
    )

    $directory = Get-MigrationReportDirectory -Manifest $Manifest -ManifestPath $ManifestPath
    $path = Join-Path $directory "project-checkpoint.json"
    if (-not (Test-Path $path)) { return @() }
    $excluded = @($Manifest.projectSelection.excludeProjectIds)
    return @(Get-MigrationProjectIds -Manifest $Manifest -ManifestPath $ManifestPath | Where-Object {
        $_ -notin $excluded
    })
}

function Resolve-ManifestRelativePath {
    param(
        [Parameter(Mandatory)][string]$ManifestPath,
        [Parameter(Mandatory)][string]$RelativePath
    )

    $base = Split-Path -Parent $ManifestPath
    return [System.IO.Path]::GetFullPath((Join-Path $base $RelativePath))
}