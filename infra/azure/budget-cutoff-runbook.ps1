param(
    [object]$WebhookData,
    [Parameter(Mandatory)]
    [string]$SubscriptionId,
    [Parameter(Mandatory)]
    [string]$ResourceGroups
)

$ErrorActionPreference = "Stop"

$payload = $WebhookData.RequestBody | ConvertFrom-Json
$budgetName = [string]($payload.data.BudgetName ?? $payload.data.context.name)
$threshold = [decimal]($payload.data.NotificationThresholdAmount ?? $payload.data.context.notificationThresholdAmount)
if ($budgetName -ne "tripplanner-global-8000inr" -or $threshold -lt 100) {
    Write-Output "Ignoring non-cutoff budget notification."
    return
}

$subscriptionId = $SubscriptionId
$resourceGroups = $ResourceGroups | ConvertFrom-Json
$apiVersion = "2025-01-01"

Connect-AzAccount -Identity | Out-Null
Set-AzContext -SubscriptionId $subscriptionId | Out-Null

function Invoke-ArmRequest {
    param(
        [Parameter(Mandatory)][ValidateSet("GET", "POST", "PATCH")][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [string]$Payload = ""
    )

    $parameters = @{
        Method = $Method
        Path = $Path
    }
    if ($Payload) { $parameters.Payload = $Payload }
    Invoke-AzRestMethod @parameters | Out-Null
}

foreach ($resourceGroup in @($resourceGroups)) {
    $basePath = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup"
    $resources = (Invoke-AzRestMethod -Method GET -Path "$basePath/resources?api-version=2021-04-01").Content |
        ConvertFrom-Json

    foreach ($resource in @($resources.value)) {
        switch ([string]$resource.type) {
            "Microsoft.App/containerApps" {
                Invoke-ArmRequest -Method POST -Path "$($resource.id)/stop?api-version=$apiVersion"
            }
            "Microsoft.App/jobs" {
                $body = @{ properties = @{ configuration = @{ triggerType = "Manual" } } } |
                    ConvertTo-Json -Depth 5 -Compress
                Invoke-ArmRequest -Method PATCH -Path "$($resource.id)?api-version=$apiVersion" -Payload $body
            }
            "Microsoft.CognitiveServices/accounts" {
                $body = @{ properties = @{ publicNetworkAccess = "Disabled" } } |
                    ConvertTo-Json -Depth 3 -Compress
                Invoke-ArmRequest -Method PATCH -Path "$($resource.id)?api-version=2024-10-01" -Payload $body
            }
        }
    }
}

Write-Output "Tripplanner serving and Azure OpenAI access disabled at the global budget cutoff."
