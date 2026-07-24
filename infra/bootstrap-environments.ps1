#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Bootstrap canary and production deployments for a fresh subscription.

.DESCRIPTION
  Optional Azure OpenAI provisioning + infra deployment to canary and/or prod.
  Uses existing deployment scripts with portable parameters.

.EXAMPLE
  ./infra/bootstrap-environments.ps1 -SubscriptionId <sub-id> -ImageTag v1.2.3 -ProvisionAoai

.EXAMPLE
  ./infra/bootstrap-environments.ps1 -DeployCanaryOnly -ImageTag latest
#>

param(
    [string]$SubscriptionId = "",
    [string]$Location = "eastus2",
    [string]$ImageTag = "latest",
    [switch]$ProvisionAoai = $false,
    [switch]$DeployCanaryOnly = $false,
    [string]$CosmosAccountName = ""
)

$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

Write-Host "\nBootstrap start"
Write-Host "Subscription: $(az account show --query id -o tsv)"
Write-Host "Location: $Location"
Write-Host "Image Tag: $ImageTag"
Write-Host "Provision AOAI: $ProvisionAoai"
Write-Host "Deploy Canary Only: $DeployCanaryOnly\n"

if ($ProvisionAoai) {
    ./infra/provision-aoai.ps1 `
        -Environment canary `
        -SubscriptionId $SubscriptionId `
        -Location $Location `
        -ResourceGroup rg-tripplanner-canary `
        -SkuName Standard `
        -Capacity 20

    if (-not $DeployCanaryOnly) {
        ./infra/provision-aoai.ps1 `
            -Environment prod `
            -SubscriptionId $SubscriptionId `
            -Location $Location `
            -ResourceGroup rg-tripplanner-prod `
            -SkuName GlobalStandard `
            -Capacity 50
    }

    Write-Host "If AOAI account names differ, copy emitted values into .env before deploy scripts continue.\n"
}

./infra/deploy-data.ps1 `
  -SubscriptionId $SubscriptionId `
  -Location $Location `
  -AccountName $CosmosAccountName

if ([string]::IsNullOrWhiteSpace($CosmosAccountName)) {
  $cosmosAccounts = @(az cosmosdb list -g rg-tripplanner-data --query "[].name" -o tsv)
  if ($cosmosAccounts.Count -ne 1) {
    throw "Expected exactly one Cosmos account in rg-tripplanner-data; found $($cosmosAccounts.Count). Pass -CosmosAccountName explicitly."
  }
  $CosmosAccountName = $cosmosAccounts[0]
}

./infra/deploy-canary.ps1 `
    -ImageTag $ImageTag `
    -SubscriptionId $SubscriptionId `
    -ResourceGroup rg-tripplanner-canary `
    -NamePrefix canary `
    -Location $Location `
    -CosmosAccountName $CosmosAccountName

if (-not $DeployCanaryOnly) {
    ./infra/deploy-prod.ps1 `
        -ImageTag $ImageTag `
        -SubscriptionId $SubscriptionId `
        -ResourceGroup rg-tripplanner-prod `
        -NamePrefix prod `
        -Location $Location `
        -CosmosAccountName $CosmosAccountName
}

Write-Host "\nBootstrap complete."
