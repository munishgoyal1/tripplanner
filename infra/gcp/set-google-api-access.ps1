[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("places", "maps")]
    [string]$Capability,
    [ValidateSet("status", "apply", "enable", "disable", "on", "off")]
    [string]$Action = "status",
    [ValidateSet("all", "local", "canary", "prod")]
    [string]$Environment = "all",
    [string]$Approval = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/google-api-control-common.ps1"

$config = Get-Content (Join-Path $PSScriptRoot "../billing-guardrails.json") -Raw |
    ConvertFrom-Json
$definition = Get-GoogleApiCapability -Name $Capability
$normalizedAction = @{ on = "enable"; off = "disable" }[$Action]
if (-not $normalizedAction) { $normalizedAction = $Action }

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

function Get-ServiceStates {
    param([Parameter(Mandatory)][string]$Project)

    $enabled = @(& gcloud services list --enabled --project=$Project --format="value(config.name)")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Google service state for $Project."
    }
    $states = @{}
    foreach ($service in $definition.Services) {
        $states[$service] = $service -in $enabled
    }
    return $states
}

$targets = @($config.gcp.environments)
if ($Environment -ne "all") {
    $targets = @($targets | Where-Object { $_.name -eq $Environment })
}
if ($targets.Count -eq 0) {
    throw "No environment matched '$Environment'."
}

$willEnable = $normalizedAction -eq "enable" -or (
    $normalizedAction -eq "apply" -and
    @($targets | Where-Object {
        Get-GoogleApiDesiredState -Environment $_.name -Flag $definition.Flag
    }).Count -gt 0
)
if ($willEnable -and $Approval -ne $definition.Approval) {
    throw "Enabling paid $($definition.Name) APIs requires the final argument $($definition.Approval)."
}

foreach ($target in $targets) {
    if ($normalizedAction -in @("enable", "disable")) {
        Set-GoogleApiDesiredState -Environment $target.name -Flag $definition.Flag `
            -Enabled ($normalizedAction -eq "enable")
    }
    $desired = Get-GoogleApiDesiredState -Environment $target.name -Flag $definition.Flag

    if ($normalizedAction -ne "status") {
        if ($desired) {
            Invoke-Gcloud (@("services", "enable") + $definition.Services + @("--project=$($target.project)"))
        } else {
            foreach ($service in $definition.Services) {
                Invoke-Gcloud @(
                    "services", "disable", $service, "--project=$($target.project)",
                    "--force", "--quiet"
                )
            }
        }
    }

    $states = Get-ServiceStates -Project $target.project
    $inSync = @($states.Values | Where-Object { $_ -ne $desired }).Count -eq 0
    $drift = if ($inSync) { "in sync" } else { "DRIFT" }
    $serviceSummary = @($definition.Services | ForEach-Object {
        $state = if ($states[$_]) { "enabled" } else { "disabled" }
        "$_=$state"
    })
    Write-Host "$($target.name): desired=$desired, $drift"
    Write-Host "  $($serviceSummary -join '; ')"
}

if ($normalizedAction -in @("enable", "disable")) {
    Write-Host ""
    Write-Host "Updated $($definition.Flag) in the checked-in environment profile."
    Write-Host "Local processes require a restart; hosted environments require a deployment."
    Write-Host "No application deployment was performed."
}