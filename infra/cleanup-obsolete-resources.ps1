#!/usr/bin/env pwsh
param(
    [string[]]$CosmosAccounts = @(),
    [string[]]$ContainerRegistries = @(),
    [datetime]$CutoverDate,
    [switch]$InventoryOnly
)

$ErrorActionPreference = "Stop"

function Split-ResourceRef {
    param([string]$Reference)

    $parts = $Reference.Split('/', 2)
    if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or [string]::IsNullOrWhiteSpace($parts[1])) {
        throw "Resource reference '$Reference' must use resource-group/name format."
    }
    return $parts
}

if ($CosmosAccounts.Count -eq 0 -and $ContainerRegistries.Count -eq 0) {
    throw "Specify -CosmosAccounts and/or -ContainerRegistries as resource-group/name."
}

$containerAppsJson = az containerapp list --output json
if ($LASTEXITCODE -ne 0) {
    throw "Could not inventory Container Apps."
}

$targets = @()
foreach ($reference in $CosmosAccounts) {
    $parts = Split-ResourceRef $reference
    $resourceGroup = $parts[0]
    $name = $parts[1]
    if ($resourceGroup -eq "rg-tripplanner-data") {
        throw "Refusing to target the shared data resource group: $reference"
    }
    $endpoint = az cosmosdb show -g $resourceGroup -n $name --query documentEndpoint -o tsv
    if ($LASTEXITCODE -ne 0) {
        throw "Cosmos account not found: $reference"
    }
    if ($containerAppsJson -match [regex]::Escape($endpoint)) {
        throw "Refusing to delete $reference because a Container App still references $endpoint."
    }
    $targets += [pscustomobject]@{ Type = "Cosmos DB"; Reference = $reference }
}

foreach ($reference in $ContainerRegistries) {
    $parts = Split-ResourceRef $reference
    $resourceGroup = $parts[0]
    $name = $parts[1]
    $loginServer = az acr show -g $resourceGroup -n $name --query loginServer -o tsv
    if ($LASTEXITCODE -ne 0) {
        throw "Container registry not found: $reference"
    }
    if ($containerAppsJson -match [regex]::Escape($loginServer)) {
        throw "Refusing to delete $reference because a Container App still references $loginServer."
    }
    $targets += [pscustomobject]@{ Type = "Container Registry"; Reference = $reference }
}

$targets | Format-Table -AutoSize
if ($InventoryOnly) {
    exit 0
}

if ($CutoverDate -eq [datetime]::MinValue) {
    throw "Provide -CutoverDate for the completed migration before deletion."
}
$rollbackAge = (Get-Date).ToUniversalTime() - $CutoverDate.ToUniversalTime()
if ($rollbackAge.TotalDays -lt 7) {
    throw "Cleanup is blocked until seven full days after cutover; current age is $([math]::Round($rollbackAge.TotalDays, 2)) days."
}

$approval = Read-Host "Type DELETE_OBSOLETE_TRIPPLANNER_RESOURCES to delete these exact resources"
if ($approval -cne "DELETE_OBSOLETE_TRIPPLANNER_RESOURCES") {
    throw "Cleanup approval denied."
}

foreach ($reference in $CosmosAccounts) {
    $parts = Split-ResourceRef $reference
    az cosmosdb delete -g $parts[0] -n $parts[1] --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to delete Cosmos account $reference."
    }
}

foreach ($reference in $ContainerRegistries) {
    $parts = Split-ResourceRef $reference
    az acr delete -g $parts[0] -n $parts[1] --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to delete container registry $reference."
    }
}

Write-Host "Approved obsolete resources deleted. Resource groups were preserved." -ForegroundColor Green