#!/usr/bin/env pwsh
<#+
.SYNOPSIS
    Report, disable, or enable Tripplanner's allowlisted emergency controls.

.DESCRIPTION
    Provides one operator entry point for cost, legal, security, or operational
    emergencies. It delegates to existing provider controls so their account,
    project, subscription, environment, and approval gates remain authoritative.
    No arguments performs a read-only status check across every registered control.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "disable", "enable", "off", "on")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateSet("all", "google", "azure", "local", "canary", "prod")]
    [string]$Target = "all",

    [Parameter(Position = 2)]
    [string]$AzureApproval = "",

    [Parameter(Position = 3)]
    [string]$GoogleMapsApproval = "",

    [Parameter(Position = 4)]
    [string]$GooglePlacesApproval = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$normalizedAction = @{ on = "enable"; off = "disable" }[$Action]
if (-not $normalizedAction) { $normalizedAction = $Action }
$providerScope = if ($Target -in @("google", "azure")) { $Target } else { "all" }
$environment = if ($Target -in @("local", "canary", "prod")) { $Target } else { "all" }

# Add future emergency controls here. The provider-specific script retains
# ownership of credentials, allowlists, mutation details, and final validation.
$controls = @(
    [pscustomobject]@{
        Name = "Azure services"
        Scope = "azure"
        Script = Join-Path $repoRoot "infra/azure/set-azure-services-access.ps1"
        DisableOrder = 10
        EnableOrder = 30
        Approval = $AzureApproval
        EnableApproval = "APPROVE_AZURE_SPEND"
    },
    [pscustomobject]@{
        Name = "Google Maps"
        Scope = "google"
        Script = Join-Path $repoRoot "infra/gcp/set-google-maps-access.ps1"
        DisableOrder = 20
        EnableOrder = 20
        Approval = $GoogleMapsApproval
        EnableApproval = "APPROVE_GOOGLE_MAPS_SPEND"
    },
    [pscustomobject]@{
        Name = "Google Places"
        Scope = "google"
        Script = Join-Path $repoRoot "infra/gcp/set-google-places-access.ps1"
        DisableOrder = 30
        EnableOrder = 10
        Approval = $GooglePlacesApproval
        EnableApproval = "APPROVE_GOOGLE_PLACES_SPEND"
    }
)

$selected = @($controls | Where-Object {
    $providerScope -eq "all" -or $_.Scope -eq $providerScope
})
if ($selected.Count -eq 0) {
    throw "No emergency controls are registered for target '$Target'."
}

if ($normalizedAction -eq "enable") {
    $missingApprovals = @($selected | Where-Object {
        $required = [string]$_.EnableApproval
        $required -and $_.Approval -cne $required
    } | ForEach-Object { "  $($_.Name): $($_.EnableApproval)" })
    if ($missingApprovals.Count -gt 0) {
        throw "Required approvals were not supplied:`n$($missingApprovals -join "`n")"
    }
}

$orderProperty = if ($normalizedAction -eq "enable") { "EnableOrder" } else { "DisableOrder" }
$selected = @($selected | Sort-Object $orderProperty)

Write-Host "Tripplanner emergency control"
Write-Host "  action      : $normalizedAction"
Write-Host "  target      : $Target"
Write-Host "  environment : $environment"
Write-Host "  controls    : $($selected.Name -join ', ')"
Write-Host ""

$failures = @()
foreach ($control in $selected) {
    Write-Host "[$($control.Name)]" -ForegroundColor Cyan
    try {
        & $control.Script $normalizedAction $environment $control.Approval
        if ($LASTEXITCODE -ne 0) {
            throw "exited with code $LASTEXITCODE"
        }
    } catch {
        $failures += "$($control.Name): $($_.Exception.Message)"
        Write-Error $failures[-1] -ErrorAction Continue
    }
    Write-Host ""
}

if ($failures.Count -gt 0) {
    throw "$($failures.Count) emergency control(s) failed:`n  $($failures -join "`n  ")"
}

if ($normalizedAction -eq "status") {
    Write-Host "Emergency status check completed successfully." -ForegroundColor Green
} else {
    Write-Host "Emergency $normalizedAction completed for every selected control." -ForegroundColor Green
    Write-Host "Profile changes require a local restart or hosted deployment to persist in app configuration."
}
