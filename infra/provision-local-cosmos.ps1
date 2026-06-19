#!/usr/bin/env pwsh
param(
    [string]$SubscriptionId = "2dd0a2f4-fc3a-4245-8e40-fadd0bbcbd5b",
    [string]$Location = "eastus2",
    [string]$ResourceGroup = "rg-tripplanner-local",
    [string]$DatabaseName = "tripplanner",
    [string]$AccountName = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AccountName)) {
    $suffix = -join ((48..57 + 97..122) | Get-Random -Count 6 | ForEach-Object { [char]$_ })
    $AccountName = "localcosmos$suffix"
}

az account set --subscription $SubscriptionId | Out-Null
az group create --name $ResourceGroup --location $Location -o none

$exists = az cosmosdb show --name $AccountName --resource-group $ResourceGroup --query name -o tsv 2>$null
if ([string]::IsNullOrWhiteSpace($exists)) {
    az cosmosdb create `
        --name $AccountName `
        --resource-group $ResourceGroup `
        --locations regionName=$Location failoverPriority=0 isZoneRedundant=False `
        --default-consistency-level Session `
        --enable-analytical-storage false `
        --enable-automatic-failover false `
        --public-network-access Enabled `
        -o none
}

$dbExists = az cosmosdb sql database show --account-name $AccountName --resource-group $ResourceGroup --name $DatabaseName --query name -o tsv 2>$null
if ([string]::IsNullOrWhiteSpace($dbExists)) {
    az cosmosdb sql database create --account-name $AccountName --resource-group $ResourceGroup --name $DatabaseName --throughput 1000 -o none
}

$containers = @("users", "trips", "audit_events")
foreach ($container in $containers) {
    $containerExists = az cosmosdb sql container show --account-name $AccountName --resource-group $ResourceGroup --database-name $DatabaseName --name $container --query name -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($containerExists)) {
        if ($container -eq "audit_events") {
            az cosmosdb sql container create --account-name $AccountName --resource-group $ResourceGroup --database-name $DatabaseName --name $container --partition-key-path '/user_id' --ttl 7776000 -o none
        } else {
            az cosmosdb sql container create --account-name $AccountName --resource-group $ResourceGroup --database-name $DatabaseName --name $container --partition-key-path '/user_id' -o none
        }
    }
}

$endpoint = az cosmosdb show --name $AccountName --resource-group $ResourceGroup --query documentEndpoint -o tsv
$key = az cosmosdb keys list --name $AccountName --resource-group $ResourceGroup --query primaryMasterKey -o tsv

Write-Output "LOCAL_RG=$ResourceGroup"
Write-Output "LOCAL_COSMOS_ACCOUNT=$AccountName"
Write-Output "LOCAL_COSMOS_ENDPOINT=$endpoint"
Write-Output "LOCAL_COSMOS_KEY=$key"
Write-Output "LOCAL_COSMOS_DATABASE=$DatabaseName"
