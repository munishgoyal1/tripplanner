#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Provision an Azure OpenAI account + deployment for a target environment.

.DESCRIPTION
    Creates (or reuses) an Azure OpenAI account and a model deployment, then
    prints non-secret environment metadata.

.EXAMPLE
  ./infra/provision-aoai.ps1 -Environment canary -SubscriptionId <sub-id>

.EXAMPLE
  ./infra/provision-aoai.ps1 -Environment prod -SkuName GlobalStandard -Capacity 50
#>

param(
    [ValidateSet("local", "canary", "prod")]
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

function Invoke-AzChecked {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [switch]$Capture
    )

    if ($Capture) {
        $output = & az @Arguments
    } else {
        & az @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
    if ($Capture) {
        return ($output -join [Environment]::NewLine).Trim()
    }
}

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    Invoke-AzChecked -Arguments @("account", "set", "--subscription", $SubscriptionId)
}

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $ResourceGroup = "rg-tripplanner-$Environment"
}

if ([string]::IsNullOrWhiteSpace($AccountName)) {
    $AccountName = switch ($Environment) {
        "local" { "aoailocaltp9fe3951c" }
        "canary" { "aoaicanarytp9fe3951c" }
        "prod" { "aoaiprodtp9fe3951c" }
    }
}

if ([string]::IsNullOrWhiteSpace($DeploymentName)) {
    $DeploymentName = switch ($Environment) {
        "local" { "gpt-4-1-local" }
        "canary" { "gpt-4-1-canary" }
        "prod" { "gpt-4-1-global" }
    }
}

Write-Host "\nPreparing Azure OpenAI for environment: $Environment"
$activeSubscription = Invoke-AzChecked -Capture -Arguments @("account", "show", "--query", "id", "-o", "tsv")
Write-Host "Subscription: $activeSubscription"
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Account: $AccountName"
Write-Host "Deployment: $DeploymentName"
Write-Host "Model: $ModelName ($ModelVersion)"
Write-Host "SKU: $SkuName (capacity: $Capacity)\n"

Invoke-AzChecked -Arguments @("group", "create", "--name", $ResourceGroup, "--location", $Location, "-o", "none")

$existingAccount = Invoke-AzChecked -Capture -Arguments @(
    "cognitiveservices", "account", "list",
    "--resource-group", $ResourceGroup,
    "--query", "[?name=='$AccountName'].name | [0]", "-o", "tsv"
)

if ([string]::IsNullOrWhiteSpace($existingAccount)) {
    Write-Host "Creating Azure OpenAI account..."
    Invoke-AzChecked -Arguments @(
        "cognitiveservices", "account", "create",
        "--resource-group", $ResourceGroup,
        "--name", $AccountName,
        "--location", $Location,
        "--kind", "OpenAI",
        "--sku", "S0",
        "--custom-domain", $AccountName,
        "--yes", "-o", "none"
    )
    Write-Host "  Created account: $AccountName"
} else {
    Write-Host "Account already exists, reusing: $existingAccount"
}

$existingDeployment = Invoke-AzChecked -Capture -Arguments @(
    "cognitiveservices", "account", "deployment", "list",
    "--resource-group", $ResourceGroup,
    "--name", $AccountName,
    "--query", "[?name=='$DeploymentName'].name | [0]", "-o", "tsv"
)

if ([string]::IsNullOrWhiteSpace($existingDeployment)) {
    Write-Host "Creating model deployment..."
    Invoke-AzChecked -Arguments @(
        "cognitiveservices", "account", "deployment", "create",
        "--resource-group", $ResourceGroup,
        "--name", $AccountName,
        "--deployment-name", $DeploymentName,
        "--model-name", $ModelName,
        "--model-version", $ModelVersion,
        "--model-format", "OpenAI",
        "--sku-name", $SkuName,
        "--sku-capacity", $Capacity,
        "-o", "none"
    )
    Write-Host "  Created deployment: $DeploymentName"
} else {
    Write-Host "Deployment already exists, reusing: $existingDeployment"
}

$endpoint = Invoke-AzChecked -Capture -Arguments @(
    "cognitiveservices", "account", "show",
    "--resource-group", $ResourceGroup,
    "--name", $AccountName,
    "--query", "properties.endpoint", "-o", "tsv"
)

Write-Host "\nAzure OpenAI ready. Non-secret environment metadata:"
Write-Host "AZURE_OPENAI_ENDPOINT=$endpoint"
Write-Host "AZURE_OPENAI_DEPLOYMENT=$DeploymentName"
Write-Host "AZURE_OPENAI_API_VERSION=2024-10-21\n"
