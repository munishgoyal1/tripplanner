#!/usr/bin/env pwsh
param(
    [string]$SubscriptionId = "",
    [string]$Location = "eastus2",
    [string]$ResourceGroup = "rg-tripplanner-data",
    [string]$AccountName = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$templateFile = Join-Path $PSScriptRoot "data-stack.bicep"
$parametersFile = Join-Path $PSScriptRoot "data.bicepparam"

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

$existingFreeTierJson = az cosmosdb list --query "[?enableFreeTier].{name:name,resourceGroup:resourceGroup}" -o json | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect existing Cosmos DB accounts."
}
$existingFreeTier = @($existingFreeTierJson | ConvertFrom-Json)
if ($existingFreeTier.Count -gt 0) {
    $matchingAccount = @($existingFreeTier | Where-Object {
        $_.resourceGroup -eq $ResourceGroup -and
        ([string]::IsNullOrWhiteSpace($AccountName) -or $_.name -eq $AccountName)
    })
    if ($matchingAccount.Count -ne 1) {
        $references = $existingFreeTier | ForEach-Object { "$($_.resourceGroup)/$($_.name)" }
        throw "This subscription already has a different lifetime free-tier Cosmos account: $($references -join ', '). Reuse it or revise the deployment plan."
    }
    $AccountName = $matchingAccount[0].name
}

$overrides = @("dataResourceGroupName=$ResourceGroup", "location=$Location")
if (-not [string]::IsNullOrWhiteSpace($AccountName)) {
    $overrides += "cosmosAccountName=$AccountName"
}

$verb = if ($DryRun) { "what-if" } else { "create" }
$rawDeployment = az deployment sub $verb `
    --name tripplanner-shared-data `
    --location $Location `
    --template-file $templateFile `
    --parameters $parametersFile `
    --parameters $overrides `
    --only-show-errors `
    --output json | Out-String
if ($LASTEXITCODE -ne 0) {
    throw "Shared data-plane deployment $verb failed."
}

if ($DryRun) {
    Write-Output $rawDeployment
    exit 0
}

$jsonStart = $rawDeployment.IndexOf('{')
$jsonEnd = $rawDeployment.LastIndexOf('}')
if ($jsonStart -lt 0 -or $jsonEnd -lt $jsonStart) {
    throw "Deployment succeeded but did not return parseable JSON. Raw output:`n$rawDeployment"
}
$deployment = $rawDeployment.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
$outputs = $deployment.properties.outputs
Write-Output "COSMOS_RESOURCE_GROUP=$($outputs.dataResourceGroupName.value)"
Write-Output "COSMOS_ACCOUNT_NAME=$($outputs.cosmosAccountName.value)"
Write-Output "COSMOS_DATABASE_CANARY=tripplanner-canary"
Write-Output "COSMOS_DATABASE_PROD=tripplanner-prod"