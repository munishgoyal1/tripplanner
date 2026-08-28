[CmdletBinding()]
param(
    [ValidateSet("status", "apply", "enable", "disable")]
    [string]$Action = "status",

    [ValidateSet("all", "local", "canary", "prod")]
    [string]$Environment = "all",

    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
$configPath = Join-Path $PSScriptRoot "../billing-guardrails.json"
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$placesService = "places.googleapis.com"
$requiredApproval = "APPROVE_GOOGLE_PLACES_SPEND"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud is not on PATH."
}

function Invoke-Gcloud {
    param([Parameter(Mandatory)][string[]]$Arguments)

    Write-Host "gcloud $($Arguments -join ' ')"
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed with exit code $LASTEXITCODE."
    }
}

function Get-PlacesServiceState {
    param([Parameter(Mandatory)][string]$Project)

    $enabled = & gcloud services list --enabled --project=$Project `
        --filter="config.name:$placesService" --format="value(config.name)"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Google Places service state for $Project."
    }
    return $enabled -eq $placesService
}

$targets = @($config.gcp.environments)
if ($Environment -ne "all") {
    $targets = @($targets | Where-Object { $_.name -eq $Environment })
}
if ($targets.Count -eq 0) {
    throw "No environment matched '$Environment'."
}

$willEnable = $Action -eq "enable" -or (
    $Action -eq "apply" -and @($targets | Where-Object { [bool]$_.placesEnabled }).Count -gt 0
)
if ($willEnable -and $Approval -ne $requiredApproval) {
    throw "Enabling a paid API requires the final argument $requiredApproval."
}

foreach ($target in $targets) {
    $project = $target.project
    $desired = if ($Action -eq "apply") {
        [bool]$target.placesEnabled
    } elseif ($Action -eq "enable") {
        $true
    } elseif ($Action -eq "disable") {
        $false
    } else {
        $null
    }

    if ($null -ne $desired) {
        if ($desired) {
            Invoke-Gcloud @("services", "enable", $placesService, "--project=$project")
        } else {
            Invoke-Gcloud @(
                "services", "disable", $placesService, "--project=$project", "--force", "--quiet"
            )
        }
    }

    $actual = Get-PlacesServiceState -Project $project
    $configured = [bool]$target.placesEnabled
    $state = if ($actual) { "enabled" } else { "disabled" }
    Write-Host "$($target.name): $state (central desired state: $configured)"
}

if ($Action -in @("enable", "disable")) {
    Write-Host ""
    Write-Host "This was an immediate override. Edit $configPath and run 'apply' for durable state."
}
