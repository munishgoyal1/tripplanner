#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Apply Azure billing guardrails from infra/billing-guardrails.json.

.DESCRIPTION
  Idempotent. Creates or updates the budget alert action group and the
  per-resource-group and subscription budgets. Re-run after editing the config
  to tweak limits; budgets are written with PUT so re-running simply converges.

  Azure has no equivalent to detaching billing, so there is no shutoff function
  here. The subscription spending limit is the only true hard stop and this
  script reports its state.

.EXAMPLE
  ./infra/azure/apply-billing-guardrails.ps1 -WhatIf

.EXAMPLE
  ./infra/azure/apply-billing-guardrails.ps1
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = "$PSScriptRoot/../billing-guardrails.json"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "az is not on PATH. Install the Azure CLI, then run 'az login'."
}

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$azure = $config.azure
$subscription = $azure.subscriptionId

$current = az account show --query "{id:id, user:user.name}" -o json | ConvertFrom-Json
if ($current.id -ne $subscription) {
    az account set --subscription $subscription
    $current = az account show --query "{id:id, user:user.name}" -o json | ConvertFrom-Json
}

Write-Host "Azure billing guardrails"
Write-Host "  subscription  : $($current.id)"
Write-Host "  signed in as  : $($current.user)"
Write-Host "  global budget : $($azure.globalBudget.amount) $($azure.currency)"
Write-Host ""

$limit = az rest --method get `
    --url "https://management.azure.com/subscriptions/$subscription`?api-version=2022-12-01" `
    --query "subscriptionPolicies.spendingLimit" -o tsv
Write-Host "  spending limit: $limit  (the only hard stop Azure offers on this subscription)"

# --- action group -----------------------------------------------------------

$actionGroupId = "/subscriptions/$subscription/resourceGroups/$($azure.actionGroupResourceGroup)/providers/microsoft.insights/actionGroups/$($azure.actionGroupName)"

if ($PSCmdlet.ShouldProcess($azure.actionGroupName, "Ensure budget action group")) {
    az monitor action-group create `
        --name $azure.actionGroupName `
        --resource-group $azure.actionGroupResourceGroup `
        --short-name $azure.actionGroupShortName `
        --action email owner $config.alertEmail `
        --output none
    Write-Host "  action group ready"
}

# --- budgets ----------------------------------------------------------------

function Set-AzureBudget {
    param([string]$Scope, [string]$Name, [int]$Amount, [double[]]$Thresholds)

    $notifications = [ordered]@{}
    foreach ($t in $Thresholds) {
        $percent = [int]($t * 100)
        $notifications["Actual$percent"] = [ordered]@{
            enabled       = $true
            operator      = "GreaterThanOrEqualTo"
            threshold     = $percent
            contactEmails = @($config.alertEmail)
            contactGroups = @($actionGroupId)
            thresholdType = "Actual"
        }
    }
    # Forecast fires before the money is spent; actual fires after.
    $notifications["Forecast100"] = [ordered]@{
        enabled       = $true
        operator      = "GreaterThanOrEqualTo"
        threshold     = 100
        contactEmails = @($config.alertEmail)
        contactGroups = @($actionGroupId)
        thresholdType = "Forecasted"
    }

    $start = (Get-Date -Day 1).ToUniversalTime().ToString("yyyy-MM-01T00:00:00Z")
    $body = [ordered]@{
        properties = [ordered]@{
            category      = "Cost"
            amount        = $Amount
            timeGrain     = "Monthly"
            timePeriod    = [ordered]@{ startDate = $start; endDate = "2030-12-01T00:00:00Z" }
            notifications = $notifications
        }
    } | ConvertTo-Json -Depth 10

    $file = Join-Path ([System.IO.Path]::GetTempPath()) "tp-azure-budget.json"
    $body | Set-Content -Path $file -Encoding utf8

    if ($PSCmdlet.ShouldProcess($Name, "Set budget to $Amount $($azure.currency)")) {
        az rest --method put `
            --url "https://management.azure.com$Scope/providers/Microsoft.Consumption/budgets/$Name`?api-version=2021-10-01" `
            --body "@$file" --headers "Content-Type=application/json" --output none
        Write-Host "  budget set: $Name ($Amount $($azure.currency))"
    }
    Remove-Item $file -ErrorAction SilentlyContinue
}

foreach ($env in $azure.environments) {
    Set-AzureBudget -Scope "/subscriptions/$subscription/resourceGroups/$($env.resourceGroup)" `
    -Name $env.budgetName `
        -Amount $env.budget -Thresholds $config.thresholds.environment
}

Set-AzureBudget -Scope "/subscriptions/$subscription" `
    -Name $azure.globalBudget.name -Amount $azure.globalBudget.amount `
    -Thresholds $config.thresholds.global

Write-Host ""
Write-Host "Azure guardrails applied."
Write-Host "Review month-to-date spend with ./infra/show-billing-status.ps1"
