#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = "$PSScriptRoot/../billing-guardrails.json",
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$subscriptionId = [string]$config.azure.subscriptionId
$tenantId = [string]$config.azure.tenantId
$resourceGroup = [string]$config.azure.actionGroupResourceGroup
$location = [string]$config.azure.cutoff.location
$automationAccount = [string]$config.azure.cutoff.automationAccountName
$runbookName = [string]$config.azure.cutoff.runbookName
$webhookName = [string]$config.azure.cutoff.webhookName
$actionGroupName = [string]$config.azure.cutoff.actionGroupName
$resourceGroups = @($config.azure.environments | Where-Object { $_.name -in @("canary", "prod") } | ForEach-Object { $_.resourceGroup })

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw "az is required." }
$account = az account show --query "{id:id,tenant:tenantId,user:user.name}" --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.id -ne $subscriptionId -or $account.tenant -ne $tenantId) {
    throw "Select the configured target Azure subscription and tenant before deploying cutoff automation."
}
if ($account.user -ine "munishgoyal@aitripplanner.co") {
    throw "Refusing cutoff deployment as '$($account.user)'."
}

$requiredModules = @("Az.Accounts", "Az.Automation")
$missingModules = @($requiredModules | Where-Object { -not (Get-Module -ListAvailable $_) })
if ($missingModules.Count -gt 0) {
    if (-not $InstallDependencies) {
        throw "Missing PowerShell modules: $($missingModules -join ', '). Re-run with -InstallDependencies."
    }
    foreach ($module in $missingModules) {
        Install-Module $module -Scope CurrentUser -Repository PSGallery -Force -AllowClobber -WhatIf:$false
    }
}
Import-Module Az.Accounts
Import-Module Az.Automation

if ($WhatIfPreference) {
    Write-Host "Would deploy budget cutoff automation to $subscriptionId."
    return
}

az provider register --subscription $subscriptionId --namespace Microsoft.Automation --wait --output none
if ($LASTEXITCODE -ne 0) { throw "Microsoft.Automation registration failed." }

$accountId = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Automation/automationAccounts/$automationAccount"
$accountBody = @{
    location = $location
    identity = @{ type = "SystemAssigned" }
    properties = @{ sku = @{ name = "Basic" }; publicNetworkAccess = $true; disableLocalAuth = $true }
} | ConvertTo-Json -Depth 5 -Compress
$accountResult = az rest --method put --url "https://management.azure.com$accountId`?api-version=2024-10-23" --body $accountBody --headers "Content-Type=application/json" --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $accountResult.identity.principalId) { throw "Automation account deployment failed." }

$roleName = "Tripplanner Budget Cutoff Operator"
$roleDefinition = @{
    Name = $roleName
    Description = "Stops Tripplanner serving and disables Azure OpenAI access without delete permissions."
    Actions = @(
        "Microsoft.Resources/subscriptions/resourceGroups/read",
        "Microsoft.Resources/subscriptions/resourceGroups/resources/read",
        "Microsoft.App/containerApps/read",
        "Microsoft.App/containerApps/write",
        "Microsoft.App/jobs/read",
        "Microsoft.App/jobs/write",
        "Microsoft.CognitiveServices/accounts/read",
        "Microsoft.CognitiveServices/accounts/write"
    )
    NotActions = @()
    AssignableScopes = @("/subscriptions/$subscriptionId")
} | ConvertTo-Json -Depth 5
$roleFile = Join-Path ([System.IO.Path]::GetTempPath()) "tripplanner-cutoff-role.json"
try {
    $roleDefinition | Set-Content -Path $roleFile -Encoding utf8
    $existingRole = az role definition list --subscription $subscriptionId --name $roleName --query "[0].name" --output tsv
    if ($existingRole) {
        az role definition update --subscription $subscriptionId --role-definition $roleFile --output none
    } else {
        az role definition create --subscription $subscriptionId --role-definition $roleFile --output none
    }
    if ($LASTEXITCODE -ne 0) { throw "Cutoff role definition deployment failed." }
} finally {
    Remove-Item $roleFile -ErrorAction SilentlyContinue
}
foreach ($group in $resourceGroups) {
    $scope = "/subscriptions/$subscriptionId/resourceGroups/$group"
    az role assignment create --subscription $subscriptionId --assignee-object-id $accountResult.identity.principalId `
        --assignee-principal-type ServicePrincipal --role $roleName --scope $scope --output none
    if ($LASTEXITCODE -ne 0) { throw "Cutoff role assignment failed for $group." }
}

$token = az account get-access-token --tenant $tenantId --resource https://management.azure.com/ --query accessToken --output tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) { throw "Could not acquire Azure management token." }
$profile = Connect-AzAccount -AccessToken $token `
    -AccountId $account.user -Tenant $tenantId -Subscription $subscriptionId
$token = $null

Import-AzAutomationRunbook -ResourceGroupName $resourceGroup -AutomationAccountName $automationAccount `
    -Name $runbookName -Path (Join-Path $PSScriptRoot "budget-cutoff-runbook.ps1") `
    -Type PowerShell72 -Published -Force -DefaultProfile $profile.Context | Out-Null
Remove-AzAutomationWebhook -ResourceGroupName $resourceGroup -AutomationAccountName $automationAccount `
    -Name $webhookName -Confirm:$false -DefaultProfile $profile.Context -ErrorAction SilentlyContinue
$webhook = New-AzAutomationWebhook -ResourceGroupName $resourceGroup -AutomationAccountName $automationAccount `
    -Name $webhookName -RunbookName $runbookName -IsEnabled $true -ExpiryTime ([DateTimeOffset]"2030-12-01T00:00:00Z") `
    -Parameters @{ SubscriptionId = $subscriptionId; ResourceGroups = ($resourceGroups | ConvertTo-Json -Compress) } `
    -Force -DefaultProfile $profile.Context
if ([string]::IsNullOrWhiteSpace($webhook.WebhookURI)) { throw "Azure did not return the one-time webhook URI." }

$webhookId = "$accountId/webhooks/$webhookName"
$actionGroupId = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Insights/actionGroups/$actionGroupName"
$actionGroupBody = @{
    location = "Global"
    properties = @{
        groupShortName = "tpcutoff"
        enabled = $true
        automationRunbookReceivers = @(@{
            name = "budget-cutoff"
            automationAccountId = $accountId
            runbookName = $runbookName
            webhookResourceId = $webhookId
            serviceUri = $webhook.WebhookURI
            isGlobalRunbook = $false
            useCommonAlertSchema = $false
        })
    }
} | ConvertTo-Json -Depth 8 -Compress
az rest --method put --url "https://management.azure.com$actionGroupId`?api-version=2023-01-01" `
    --body $actionGroupBody --headers "Content-Type=application/json" --output none
if ($LASTEXITCODE -ne 0) { throw "Cutoff Action Group deployment failed." }
$webhook = $null
$actionGroupBody = $null

$budgetId = "/subscriptions/$subscriptionId/providers/Microsoft.Consumption/budgets/$($config.azure.globalBudget.name)"
$budget = az rest --method get --url "https://management.azure.com$budgetId`?api-version=2021-10-01" --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Could not read the global Azure budget." }
$actual100 = $budget.properties.notifications.PSObject.Properties | Where-Object {
    $_.Name -match '^actual100$'
} | Select-Object -First 1
if (-not $actual100) { throw "The global budget has no Actual100 notification." }
$actual100.Value.contactGroups = @($actual100.Value.contactGroups + $actionGroupId | Select-Object -Unique)
$budgetBody = @{ properties = $budget.properties } | ConvertTo-Json -Depth 12 -Compress
az rest --method put --url "https://management.azure.com$budgetId`?api-version=2021-10-01" `
    --body $budgetBody --headers "Content-Type=application/json" --output none
if ($LASTEXITCODE -ne 0) { throw "Global budget cutoff wiring failed." }

Write-Host "Azure budget cutoff automation deployed without delete permissions."
