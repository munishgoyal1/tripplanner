#!/usr/bin/env pwsh
param(
    [string]$ResourceGroup = "rg-tripplanner-local"
)

$ErrorActionPreference = "Stop"

$accounts = az cosmosdb list -g $ResourceGroup --query "[?starts_with(name, 'localcosmos')].name" -o tsv
$acct = @($accounts -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
if (-not $acct) {
    Write-Output "LOCAL_COSMOS_ACCOUNT="
    exit 1
}

$endpoint = az cosmosdb show -g $ResourceGroup -n $acct --query documentEndpoint -o tsv
$key = az cosmosdb keys list -g $ResourceGroup -n $acct --query primaryMasterKey -o tsv

Write-Output "LOCAL_RG=$ResourceGroup"
Write-Output "LOCAL_COSMOS_ACCOUNT=$acct"
Write-Output "LOCAL_COSMOS_ENDPOINT=$endpoint"
Write-Output "LOCAL_COSMOS_KEY=$key"
Write-Output "LOCAL_COSMOS_DATABASE=tripplanner"
