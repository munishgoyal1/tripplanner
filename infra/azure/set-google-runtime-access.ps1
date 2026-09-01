#!/usr/bin/env pwsh
<#+
.SYNOPSIS
    Synchronize Google runtime access without rebuilding or fully deploying Tripplanner.

.DESCRIPTION
    Keeps the checked-in hosted profile, Google Service Usage, and the running
    Azure Container App revision aligned. Container Apps receive a same-image
    revision containing only the Google runtime flag changes.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "apply", "enable", "disable", "on", "off", "help", "?")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateSet("all", "canary", "prod")]
    [string]$Environment = "all",

    [Parameter(Position = 2)]
    [string]$GoogleMapsApproval = "",

    [Parameter(Position = 3)]
    [string]$GooglePlacesApproval = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$configPath = Join-Path $repoRoot "infra/billing-guardrails.json"
$commonPath = Join-Path $repoRoot "infra/gcp/google-api-control-common.ps1"
$mapsControl = Join-Path $repoRoot "infra/gcp/set-google-maps-access.ps1"
$placesControl = Join-Path $repoRoot "infra/gcp/set-google-places-access.ps1"
. $commonPath

function Show-GoogleRuntimeHelp {
    Write-Host @"
set-google-runtime-access.ps1 - synchronize hosted Google runtime access.

Usage: set-google-runtime-access.ps1 [status|apply|enable|disable|help|?]
                                     [all|canary|prod]
                                     [maps-approval] [places-approval]

This is the Google handler behind Apply-Runtime-Config. Prefer the common owner
launcher for routine status and apply operations.
"@
}

if ($Action -in @("help", "?")) {
    Show-GoogleRuntimeHelp
    exit 0
}

$normalizedAction = @{ on = "enable"; off = "disable" }[$Action]
if (-not $normalizedAction) { $normalizedAction = $Action }

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "az is not on PATH. Install the Azure CLI, then sign in with the approved personal account."
}
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud is not on PATH."
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json
$gcloudAccounts = @(& gcloud auth list --filter="status:ACTIVE" --format="value(account)")
if ($LASTEXITCODE -ne 0 -or $gcloudAccounts.Count -ne 1) {
    throw "Could not resolve exactly one active gcloud account."
}
if ($gcloudAccounts[0] -ine $config.gcp.operatorAccount) {
    throw "Refusing Google Cloud access as '$($gcloudAccounts[0])'. Sign in with $($config.gcp.operatorAccount)."
}

function Invoke-AzJson {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $raw = & az @Arguments --only-show-errors --output json 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "az $($Arguments -join ' ') failed:`n$raw"
    }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return $raw | ConvertFrom-Json
}

function Get-EnvironmentValue {
    param(
        [Parameter(Mandatory)]$Variables,
        [Parameter(Mandatory)][string]$Name
    )

    $entry = @($Variables | Where-Object { $_.name -eq $Name })
    if ($entry.Count -ne 1) { return "<missing>" }
    return [string]$entry[0].value
}

function Get-ContainerApp {
    param([Parameter(Mandatory)][string]$ResourceGroup)

    $apps = @(Invoke-AzJson @(
        "containerapp", "list", "--resource-group", $ResourceGroup,
        "--query", "[].{name:name}"
    ))
    if ($apps.Count -ne 1) {
        throw "Expected exactly one Container App in $ResourceGroup; found $($apps.Count)."
    }
    return $apps[0]
}

function Get-ContainerAppState {
    param(
        [Parameter(Mandatory)][string]$ResourceGroup,
        [Parameter(Mandatory)][string]$Name
    )

    return Invoke-AzJson @(
        "containerapp", "show", "--resource-group", $ResourceGroup, "--name", $Name,
        "--query", "{image:properties.template.containers[0].image,env:properties.template.containers[0].env,latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,traffic:properties.configuration.ingress.traffic}"
    )
}

function Assert-GoogleApprovals {
    if ($GoogleMapsApproval -cne "APPROVE_GOOGLE_MAPS_SPEND") {
        throw "Enabling Maps requires APPROVE_GOOGLE_MAPS_SPEND as the third argument."
    }
    if ($GooglePlacesApproval -cne "APPROVE_GOOGLE_PLACES_SPEND") {
        throw "Enabling Places requires APPROVE_GOOGLE_PLACES_SPEND as the fourth argument."
    }
}

$account = Invoke-AzJson @("account", "show", "--query", "{id:id,name:name,user:user.name}")
if ($account.user -ine "munishgoyal1@gmail.com") {
    throw "Refusing Azure access as '$($account.user)'. Sign in with munishgoyal1@gmail.com."
}
if ($account.id -ne $config.azure.subscriptionId -or
    $account.name -ne "Visual Studio Enterprise Subscription") {
    throw "Refusing Azure subscription '$($account.name)' ($($account.id)). Select the configured personal Visual Studio Enterprise subscription."
}

$targets = @($config.azure.environments | Where-Object {
    $_.name -in @("canary", "prod") -and
    ($Environment -eq "all" -or $_.name -eq $Environment)
})
if ($targets.Count -eq 0) {
    throw "No hosted environment matched '$Environment'."
}

if ($normalizedAction -eq "enable") {
    Assert-GoogleApprovals
}

Write-Host "Tripplanner Google runtime control"
Write-Host "  action       : $normalizedAction"
Write-Host "  environment  : $Environment"
Write-Host "  subscription : $($account.name) ($($account.id))"
Write-Host ""

foreach ($target in $targets) {
    if ($normalizedAction -in @("enable", "disable")) {
        $enabled = $normalizedAction -eq "enable"
        Set-GoogleApiDesiredState -Environment $target.name -Flag "ENABLE_GOOGLE_MAPS" -Enabled $enabled
        Set-GoogleApiDesiredState -Environment $target.name -Flag "ENABLE_GOOGLE_PLACES" -Enabled $enabled
    }

    $mapsEnabled = Get-GoogleApiDesiredState -Environment $target.name -Flag "ENABLE_GOOGLE_MAPS"
    $placesEnabled = Get-GoogleApiDesiredState -Environment $target.name -Flag "ENABLE_GOOGLE_PLACES"
    if (($normalizedAction -ne "status") -and ($mapsEnabled -or $placesEnabled)) {
        if ($mapsEnabled -and $GoogleMapsApproval -cne "APPROVE_GOOGLE_MAPS_SPEND") {
            throw "Applying enabled Maps state requires APPROVE_GOOGLE_MAPS_SPEND as the third argument."
        }
        if ($placesEnabled -and $GooglePlacesApproval -cne "APPROVE_GOOGLE_PLACES_SPEND") {
            throw "Applying enabled Places state requires APPROVE_GOOGLE_PLACES_SPEND as the fourth argument."
        }
    }

    $app = Get-ContainerApp -ResourceGroup $target.resourceGroup
    $before = Get-ContainerAppState -ResourceGroup $target.resourceGroup -Name $app.name
    $desiredMaps = if ($mapsEnabled) { "1" } else { "0" }
    $desiredPlaces = if ($placesEnabled) { "1" } else { "0" }
    $actualMaps = Get-EnvironmentValue -Variables $before.env -Name "ENABLE_GOOGLE_MAPS"
    $actualPlaces = Get-EnvironmentValue -Variables $before.env -Name "ENABLE_GOOGLE_PLACES"
    $runtimeInSync = $actualMaps -eq $desiredMaps -and $actualPlaces -eq $desiredPlaces

    if ($normalizedAction -ne "status") {
        # Enable cloud services first; disable them only after the app stops calling them.
        if ($mapsEnabled) { & $mapsControl apply $target.name $GoogleMapsApproval }
        if ($placesEnabled) { & $placesControl apply $target.name $GooglePlacesApproval }

        if (-not $runtimeInSync) {
            Write-Host "[$($target.name)] Creating a same-image runtime revision for $($app.name)..."
            & az containerapp update `
                --resource-group $target.resourceGroup `
                --name $app.name `
                --set-env-vars `
                    "ENABLE_GOOGLE_MAPS=$desiredMaps" `
                    "ENABLE_GOOGLE_PLACES=$desiredPlaces" `
                --only-show-errors `
                --output none
            if ($LASTEXITCODE -ne 0) {
                throw "Container App runtime update failed for $($app.name)."
            }

            $after = Get-ContainerAppState -ResourceGroup $target.resourceGroup -Name $app.name
            if ($after.image -ne $before.image) {
                throw "Runtime update changed the image for $($app.name): '$($before.image)' to '$($after.image)'."
            }
            if ($after.latest -ne $after.ready) {
                throw "New revision '$($after.latest)' is not the latest ready revision for $($app.name)."
            }
            $latestTraffic = @($after.traffic | Where-Object {
                $_.latestRevision -eq $true -and [int]$_.weight -eq 100
            })
            if ($latestTraffic.Count -ne 1) {
                throw "The latest revision does not own 100% of traffic for $($app.name)."
            }
            $before = $after
        } else {
            Write-Host "[$($target.name)] Runtime flags already match; no revision created."
        }

        if (-not $mapsEnabled) { & $mapsControl apply $target.name }
        if (-not $placesEnabled) { & $placesControl apply $target.name }
    }

    $actualMaps = Get-EnvironmentValue -Variables $before.env -Name "ENABLE_GOOGLE_MAPS"
    $actualPlaces = Get-EnvironmentValue -Variables $before.env -Name "ENABLE_GOOGLE_PLACES"
    $inSync = $actualMaps -eq $desiredMaps -and $actualPlaces -eq $desiredPlaces
    $syncState = if ($inSync) { "in sync" } else { "DRIFT" }
    Write-Host "[$($target.name)] $($app.name): $syncState"
    Write-Host "  image=$($before.image)"
    Write-Host "  revision=$($before.ready)"
    Write-Host "  ENABLE_GOOGLE_MAPS=$actualMaps (desired $desiredMaps)"
    Write-Host "  ENABLE_GOOGLE_PLACES=$actualPlaces (desired $desiredPlaces)"

    if ($normalizedAction -eq "status") {
        & $mapsControl status $target.name
        & $placesControl status $target.name
    }
}

if ($normalizedAction -eq "status") {
    Write-Host ""
    Write-Host "Status is read-only. Use apply to repair runtime drift from the checked-in profiles."
} else {
    Write-Host ""
    Write-Host "Google runtime access is synchronized without rebuilding the image or running a full deployment." -ForegroundColor Green
}