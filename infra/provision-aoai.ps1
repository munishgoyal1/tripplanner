#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Provision an Azure OpenAI account + deployment for a target environment.

.DESCRIPTION
  Creates (or reuses) an Azure OpenAI account and a model deployment, then
  prints environment-variable lines you can paste into .env.

.EXAMPLE
  ./infra/provision-aoai.ps1 -Environment canary -SubscriptionId <sub-id>

.EXAMPLE
  ./infra/provision-aoai.ps1 -Environment prod -SkuName GlobalStandard -Capacity 50
#>

param(
    [ValidateSet("canary", "prod")]
    [string]$Environment,
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "",
    [string]$AccountName = "",
    [string]$Location = "eastus2",
    [string]$DeploymentName = "",
    [string]$ModelName = "gpt-4.1",
    [string]$ModelVersion = "2025-04-14",
    [ValidateSet("Standard", "GlobalStandard")]
    [string]$SkuName = "Standard",
    [int]$Capacity = 20
)

$ErrorActionPreference = "Stop"

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    az account set --subscription $SubscriptionId
}

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $ResourceGroup = if ($Environment -eq "prod") { "rg-tripplanner-prod" } else { "rg-tripplanner-canary" }
}

if ([string]::IsNullOrWhiteSpace($AccountName)) {
    $AccountName = if ($Environment -eq "prod") { "aoaiprodtripplanner" } else { "aoaicanarytripplanner" }
}

if ([string]::IsNullOrWhiteSpace($DeploymentName)) {
    $DeploymentName = if ($Environment -eq "prod") { "gpt-4-1-global" } else { "gpt-4-1-canary" }
}

Write-Host "\nPreparing Azure OpenAI for environment: $Environment"
Write-Host "Subscription: $(az account show --query id -o tsv)"
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Account: $AccountName"
Write-Host "Deployment: $DeploymentName"
Write-Host "Model: $ModelName ($ModelVersion)"
Write-Host "SKU: $SkuName (capacity: $Capacity)\n"

az group create --name $ResourceGroup --location $Location -o none

$existingAccount = az cognitiveservices account show `
    --resource-group $ResourceGroup `
    --name $AccountName `
    --query name -o tsv 2>$null

if ([string]::IsNullOrWhiteSpace($existingAccount)) {
    Write-Host "Creating Azure OpenAI account..."
    az cognitiveservices account create `
        --resource-group $ResourceGroup `
        --name $AccountName `
        --location $Location `
        --kind OpenAI `
        --sku S0 `
        --custom-domain $AccountName `
        --yes -o none
    Write-Host "  Created account: $AccountName"
} else {
    Write-Host "Account already exists, reusing: $existingAccount"
}

$existingDeployment = az cognitiveservices account deployment show `
    --resource-group $ResourceGroup `
    --name $AccountName `
    --deployment-name $DeploymentName `
    --query name -o tsv 2>$null

if ([string]::IsNullOrWhiteSpace($existingDeployment)) {
    Write-Host "Creating model deployment..."
    az cognitiveservices account deployment create `
        --resource-group $ResourceGroup `
        --name $AccountName `
        --deployment-name $DeploymentName `
        --model-name $ModelName `
        --model-version $ModelVersion `
        --model-format OpenAI `
        --sku-name $SkuName `
        --sku-capacity $Capacity -o none
    Write-Host "  Created deployment: $DeploymentName"
} else {
    Write-Host "Deployment already exists, reusing: $existingDeployment"
}

$endpoint = az cognitiveservices account show `
    --resource-group $ResourceGroup `
    --name $AccountName `
    --query properties.endpoint -o tsv

$key = az cognitiveservices account keys list `
    --resource-group $ResourceGroup `
    --name $AccountName `
    --query key1 -o tsv

Write-Host "\nAzure OpenAI ready. Paste these into .env for this environment:"
Write-Host "AZURE_OPENAI_ENDPOINT=$endpoint"
Write-Host "AZURE_OPENAI_API_KEY=$key"
Write-Host "AZURE_OPENAI_DEPLOYMENT=$DeploymentName"
Write-Host "AZURE_OPENAI_API_VERSION=2024-10-21\n"
