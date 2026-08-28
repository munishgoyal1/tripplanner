#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Apply Google Cloud billing guardrails from infra/billing-guardrails.json.

.DESCRIPTION
  Idempotent. Creates or updates the ops project, per-environment and global
  budgets, the Pub/Sub shutoff topic and function, hard Maps API quotas, and the
  quota-exceeded alert policies. Re-run after editing the config to tweak limits;
  nothing is duplicated and nothing already correct is touched.

  Cloud Billing budgets only notify. The quotas applied here are the only
  real-time ceiling; the shutoff function is a backstop for a slow leak.

.EXAMPLE
  ./infra/gcp/apply-billing-guardrails.ps1 -WhatIf

.EXAMPLE
  ./infra/gcp/apply-billing-guardrails.ps1 -DeployShutoffFunction
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = "$PSScriptRoot/../billing-guardrails.json",
    [switch]$DeployShutoffFunction,
    [switch]$SkipQuotas,
    [switch]$AllowQuotaIncreases,
    [string]$GooglePlacesApproval = "",
    [string]$GoogleMapsApproval = "",
    [string]$ShutoffApproval = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/google-api-control-common.ps1"

function Invoke-Gcloud {
    param([string[]]$Arguments, [switch]$AllowFailure)
    $output = & gcloud @Arguments 2>&1
    $joined = ($output | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "gcloud $($Arguments -join ' ') failed:`n$joined"
    }
    return $joined
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud is not on PATH. Install it, then run 'gcloud auth login' and 'gcloud auth application-default login'."
}

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$gcp = $config.gcp
$billingAccount = $gcp.billingAccount
$ops = $gcp.opsProject
$placesService = "places.googleapis.com"
$topicPath = "projects/$ops/topics/$($gcp.shutoffTopic)"
$sa = "$($gcp.shutoffServiceAccount)@$ops.iam.gserviceaccount.com"

if ([bool]$gcp.shutoffEnabled -and -not $DeployShutoffFunction) {
    throw "An armed configuration requires -DeployShutoffFunction so stale events cannot survive."
}
if ($DeployShutoffFunction) {
    if (-not [bool]$gcp.shutoffEnabled) {
        throw "Refusing to deploy while gcp.shutoffEnabled=false."
    }
    if ($ShutoffApproval -ne "APPROVE_ACCOUNT_WIDE_BILLING_SHUTOFF") {
        throw "Deployment requires -ShutoffApproval APPROVE_ACCOUNT_WIDE_BILLING_SHUTOFF."
    }
}

Write-Host "GCP billing guardrails"
Write-Host "  billing account : $billingAccount"
Write-Host "  ops project     : $ops"
Write-Host "  global budget   : $($gcp.globalBudget.amount) $($gcp.currency)"
Write-Host ""

# --- ops project ------------------------------------------------------------

$existingProjects = Invoke-Gcloud @("projects", "list", "--format=value(projectId)")
if ($existingProjects -notmatch "(?m)^$([regex]::Escape($ops))$") {
    if ($PSCmdlet.ShouldProcess($ops, "Create ops project")) {
        Invoke-Gcloud @("projects", "create", $ops, "--name=$ops") | Out-Null
        Invoke-Gcloud @("beta", "billing", "projects", "link", $ops, "--billing-account=$billingAccount") | Out-Null
    }
} else {
    Write-Host "  ops project already exists"
}

# The Budgets and Quotas APIs authenticate through ADC and additionally need a
# quota project. Configure it only after the project exists on a new account.
if ($PSCmdlet.ShouldProcess($ops, "Set gcloud quota project")) {
    Invoke-Gcloud @("config", "set", "project", $ops) | Out-Null
    Invoke-Gcloud @("config", "set", "billing/quota_project", $ops) | Out-Null
    Invoke-Gcloud @("auth", "application-default", "set-quota-project", $ops) | Out-Null
}

$opsServices = @(
    "billingbudgets.googleapis.com", "cloudbilling.googleapis.com",
    "cloudquotas.googleapis.com", "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com", "monitoring.googleapis.com", "pubsub.googleapis.com",
    "cloudfunctions.googleapis.com", "cloudbuild.googleapis.com",
    "run.googleapis.com", "eventarc.googleapis.com"
)
if ($PSCmdlet.ShouldProcess($ops, "Enable ops APIs")) {
    Invoke-Gcloud (@("services", "enable") + $opsServices + @("--project=$ops")) | Out-Null
}

# Never update a global budget while an old trigger can consume the resulting
# event. Disarmed applies remove it; armed applies recreate it from a clean slate.
$existingFunction = Invoke-Gcloud @(
    "functions", "describe", "billing-shutoff", "--gen2",
    "--region=$($gcp.shutoffRegion)", "--project=$ops", "--format=value(name)"
) -AllowFailure
if (
    $existingFunction -and
    $existingFunction -notmatch "ERROR" -and
    $PSCmdlet.ShouldProcess("billing-shutoff", "Delete existing function and Eventarc trigger")
) {
    Invoke-Gcloud @(
        "functions", "delete", "billing-shutoff", "--gen2",
        "--region=$($gcp.shutoffRegion)", "--project=$ops", "--quiet"
    ) | Out-Null
    Write-Host "  removed existing billing shutoff trigger"
}

# --- per-environment services ----------------------------------------------

foreach ($env in $gcp.environments) {
    foreach ($capabilityName in @("places", "maps")) {
        $capability = Get-GoogleApiCapability -Name $capabilityName
        $enabled = Get-GoogleApiDesiredState -Environment $env.name -Flag $capability.Flag
        $approval = if ($capabilityName -eq "places") {
            $GooglePlacesApproval
        } else {
            $GoogleMapsApproval
        }
        if ($enabled -and $approval -ne $capability.Approval) {
            throw "Enabling $($capability.Name) requires -Google$($capability.Name)Approval $($capability.Approval)."
        }
        if ($enabled) {
            if ($PSCmdlet.ShouldProcess($env.project, "Enable paid Google $($capability.Name) APIs")) {
                Invoke-Gcloud (@("services", "enable") + $capability.Services + @("--project=$($env.project)")) | Out-Null
            }
        } else {
            foreach ($service in $capability.Services) {
                if ($PSCmdlet.ShouldProcess($env.project, "Disable $service")) {
                    Invoke-Gcloud @(
                        "services", "disable", $service, "--project=$($env.project)", "--force", "--quiet"
                    ) | Out-Null
                }
            }
        }
        Write-Host "  [$($env.name)] $($capability.Name) enabled: $enabled"
    }
}

# --- API key restrictions ---------------------------------------------------

foreach ($env in $gcp.environments) {
    $keys = Invoke-Gcloud @(
        "services", "api-keys", "list", "--project=$($env.project)",
        "--format=json(displayName,uid)"
    ) | ConvertFrom-Json
    $browser = @($keys | Where-Object { $_.displayName -eq $env.browserKey })
    $server = @($keys | Where-Object { $_.displayName -eq $env.serverKey })
    if ($browser.Count -ne 1 -or $server.Count -ne 1) {
        throw "[$($env.name)] Expected one browser key '$($env.browserKey)' and one server key '$($env.serverKey)'."
    }

    $browserTargets = @("maps-backend.googleapis.com", "places.googleapis.com")
    $browserArgs = @("services", "api-keys", "update", $browser[0].uid, "--project=$($env.project)")
    $browserArgs += "--allowed-referrers=$($env.browserReferrers -join ',')"
    foreach ($service in $browserTargets) { $browserArgs += "--api-target=service=$service" }
    if ($PSCmdlet.ShouldProcess($env.browserKey, "Apply browser referrers and API restrictions")) {
        Invoke-Gcloud $browserArgs | Out-Null
    }

    $serverTargets = @(
        "places.googleapis.com", "routes.googleapis.com", "static-maps-backend.googleapis.com"
    )
    $serverArgs = @("services", "api-keys", "update", $server[0].uid, "--project=$($env.project)")
    foreach ($service in $serverTargets) { $serverArgs += "--api-target=service=$service" }
    if ($PSCmdlet.ShouldProcess($env.serverKey, "Apply server API restrictions")) {
        Invoke-Gcloud $serverArgs | Out-Null
    }
    Write-Host "  [$($env.name)] API key restrictions applied"
}

# --- budgets ----------------------------------------------------------------

function Get-BudgetId {
    param([string]$DisplayName)
    $rows = Invoke-Gcloud @(
        "billing", "budgets", "list", "--billing-account=$billingAccount",
        "--filter=displayName=$DisplayName", "--format=value(name)"
    ) -AllowFailure
    if ($rows -match "ERROR") { return "" }
    $first = ($rows -split "`n" | Where-Object { $_ } | Select-Object -First 1)
    if (-not $first) { return "" }
    return ($first -split "/")[-1]
}

function Set-Budget {
    param(
        [string]$DisplayName,
        [int]$Amount,
        [double[]]$Thresholds,
        [string]$ProjectNumber,
        [switch]$WithPubSub
    )

    $budgetId = Get-BudgetId -DisplayName $DisplayName
    $verb = if ($budgetId) { "update" } else { "create" }

    # create takes --threshold-rule; update refuses it and wants the rule set
    # cleared and re-added instead.
    $rules = @()
    if ($budgetId) {
        $rules += "--clear-threshold-rules"
        foreach ($t in $Thresholds) { $rules += "--add-threshold-rule=percent=$t,basis=current-spend" }
    } else {
        foreach ($t in $Thresholds) { $rules += "--threshold-rule=percent=$t,basis=current-spend" }
    }

    $args = @("billing", "budgets", $verb)
    if ($budgetId) { $args += $budgetId }
    $args += @(
        "--billing-account=$billingAccount",
        "--display-name=$DisplayName",
        "--budget-amount=$Amount$($gcp.currency)",
        "--calendar-period=month"
    ) + $rules

    # --filter-projects takes the project number, not the project id.
    if ($ProjectNumber) { $args += "--filter-projects=projects/$ProjectNumber" }
    if ($WithPubSub) { $args += "--notifications-rule-pubsub-topic=$topicPath" }

    if ($PSCmdlet.ShouldProcess($DisplayName, "$verb budget ($Amount $($gcp.currency))")) {
        Invoke-Gcloud $args | Out-Null
        Write-Host "  budget ${verb}d: $DisplayName ($Amount $($gcp.currency))"
    }
}

if ($PSCmdlet.ShouldProcess($topicPath, "Ensure shutoff topic")) {
    $topics = Invoke-Gcloud @("pubsub", "topics", "list", "--project=$ops", "--format=value(name)") -AllowFailure
    if ($topics -notmatch [regex]::Escape($topicPath)) {
        Invoke-Gcloud @("pubsub", "topics", "create", $gcp.shutoffTopic, "--project=$ops") | Out-Null
    }
}

foreach ($env in $gcp.environments) {
    $number = Invoke-Gcloud @("projects", "describe", $env.project, "--format=value(projectNumber)")
    Set-Budget -DisplayName $env.budgetName `
        -Amount $env.budget -Thresholds $config.thresholds.environment -ProjectNumber $number
}

Set-Budget -DisplayName $gcp.globalBudget.name -Amount $gcp.globalBudget.amount `
    -Thresholds $config.thresholds.global -WithPubSub

# --- shutoff identity -------------------------------------------------------

$accounts = Invoke-Gcloud @("iam", "service-accounts", "list", "--project=$ops", "--format=value(email)") -AllowFailure
if ($accounts -notmatch [regex]::Escape($sa)) {
    if ($PSCmdlet.ShouldProcess($sa, "Create shutoff service account")) {
        Invoke-Gcloud @("iam", "service-accounts", "create", $gcp.shutoffServiceAccount, "--project=$ops") | Out-Null
    }
}

if ($PSCmdlet.ShouldProcess($sa, "Grant billing admin")) {
    Invoke-Gcloud @(
        "beta", "billing", "accounts", "add-iam-policy-binding", $billingAccount,
        "--member=serviceAccount:$sa", "--role=roles/billing.admin"
    ) | Out-Null
    foreach ($project in (@($gcp.environments.project) + @($ops))) {
        Invoke-Gcloud @(
            "projects", "add-iam-policy-binding", $project,
            "--member=serviceAccount:$sa", "--role=roles/billing.projectManager"
        ) | Out-Null
    }
    foreach ($role in @("roles/eventarc.eventReceiver", "roles/pubsub.subscriber")) {
        Invoke-Gcloud @(
            "projects", "add-iam-policy-binding", $ops,
            "--member=serviceAccount:$sa", "--role=$role"
        ) | Out-Null
    }
}

if ($DeployShutoffFunction) {
    $source = Join-Path $PSScriptRoot "billing-shutoff"
    if ($PSCmdlet.ShouldProcess("billing-shutoff", "Deploy Cloud Function")) {
        Invoke-Gcloud @(
            "functions", "deploy", "billing-shutoff", "--gen2", "--runtime=python312",
            "--region=$($gcp.shutoffRegion)", "--source=$source", "--entry-point=shutoff",
            "--trigger-topic=$($gcp.shutoffTopic)", "--service-account=$sa",
            "--trigger-service-account=$sa",
            "--set-env-vars=BILLING_ACCOUNT=$billingAccount,GUARDED_BUDGET=$($gcp.globalBudget.name)",
            "--project=$ops", "--quiet"
        ) | Out-Null
        Write-Host "  shutoff function deployed"
    }
} else {
    Write-Host "  shutoff function skipped (pass -DeployShutoffFunction; the deploy takes several minutes)"
}

# Gen2 functions run on Cloud Run. Bind the identity reported by the deployed
# Eventarc trigger rather than assuming it matches the runtime identity.
$functionName = Invoke-Gcloud @(
    "functions", "describe", "billing-shutoff", "--gen2",
    "--region=$($gcp.shutoffRegion)", "--project=$ops", "--format=value(name)"
) -AllowFailure
if ([bool]$gcp.shutoffEnabled -and $functionName -and $functionName -notmatch "ERROR") {
    $triggerServiceAccount = Invoke-Gcloud @(
        "functions", "describe", "billing-shutoff", "--gen2",
        "--region=$($gcp.shutoffRegion)", "--project=$ops",
        "--format=value(eventTrigger.serviceAccountEmail)"
    )
    if (-not $triggerServiceAccount) {
        throw "The deployed billing-shutoff function did not report an Eventarc trigger identity."
    }
    if ($PSCmdlet.ShouldProcess($triggerServiceAccount, "Arm billing shutoff Cloud Run invoker")) {
        Invoke-Gcloud @(
            "run", "services", "add-iam-policy-binding", "billing-shutoff",
            "--region=$($gcp.shutoffRegion)", "--project=$ops",
            "--member=serviceAccount:$triggerServiceAccount",
            "--role=roles/run.invoker", "--quiet"
        ) | Out-Null
        Write-Host "  billing shutoff armed"
    }
} else {
    Write-Host "  billing shutoff disarmed"
}

# --- quotas -----------------------------------------------------------------

if (-not $SkipQuotas) {
    foreach ($env in $gcp.environments) {
        foreach ($quota in $gcp.quotas) {
            $value = $quota.($env.name)
            if ($null -eq $value) { continue }
            $preferenceId = "tp-" + $quota.quotaId.ToLower().Replace("_", "")

            # Both --allow flags are required when tightening below Google's
            # defaults by more than ten percent or below current usage.
            $quotaArgs = @(
                "--project=$($env.project)",
                "--service=$($quota.service)", "--quota-id=$($quota.quotaId)",
                "--preferred-value=$value",
                "--allow-high-percentage-quota-decrease", "--allow-quota-decrease-below-usage"
            )
            if ($PSCmdlet.ShouldProcess("$($env.project)/$($quota.quotaId)", "Set quota to $value")) {
                $existingJson = Invoke-Gcloud @(
                    "quotas", "preferences", "describe", $preferenceId,
                    "--project=$($env.project)", "--format=json"
                ) -AllowFailure
                if ($existingJson -notmatch "ERROR") {
                    $existing = $existingJson | ConvertFrom-Json
                    $currentValue = [long]$existing.quotaConfig.preferredValue
                    if ($value -gt $currentValue -and -not $AllowQuotaIncreases) {
                        Write-Host "  [$($env.name)] kept tighter $($quota.quotaId) quota at $currentValue"
                        continue
                    }
                    $updateArgs = @(
                        "quotas", "preferences", "update", $preferenceId
                    ) + $quotaArgs
                    Invoke-Gcloud $updateArgs | Out-Null
                } else {
                    $createArgs = @(
                        "quotas", "preferences", "create", "--preference-id=$preferenceId"
                    ) + $quotaArgs
                    Invoke-Gcloud $createArgs | Out-Null
                }
            }
        }
        Write-Host "  [$($env.name)] quotas applied"
    }
}

# --- quota alerts -----------------------------------------------------------

$policyFile = Join-Path ([System.IO.Path]::GetTempPath()) "tp-quota-policy.json"
@'
{
  "displayName": "Maps API quota exceeded",
  "documentation": {
    "content": "A Maps Platform quota limit was hit. Requests are being rejected with RESOURCE_EXHAUSTED. Raise the limit in infra/billing-guardrails.json and re-run the guardrail script, or reduce load.",
    "mimeType": "text/markdown"
  },
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Quota exceeded",
      "conditionThreshold": {
        "filter": "metric.type=\"serviceruntime.googleapis.com/quota/exceeded\" AND resource.type=\"consumer_quota\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_COUNT_TRUE",
            "crossSeriesReducer": "REDUCE_SUM",
            "groupByFields": ["metric.label.quota_metric", "resource.label.service"]
          }
        ]
      }
    }
  ],
  "alertStrategy": { "autoClose": "86400s" }
}
'@ | Set-Content -Path $policyFile -Encoding utf8

foreach ($env in $gcp.environments) {
    if (-not $PSCmdlet.ShouldProcess($env.project, "Ensure quota alert policy")) { continue }

    Invoke-Gcloud @("services", "enable", "monitoring.googleapis.com", "--project=$($env.project)") | Out-Null

    $policies = Invoke-Gcloud @(
        "alpha", "monitoring", "policies", "list", "--project=$($env.project)",
        "--format=value(displayName)"
    ) -AllowFailure
    if ($policies -match "Maps API quota exceeded") {
        Write-Host "  [$($env.name)] quota alert already present"
        continue
    }

    # Discard stderr: gcloud prints a WARNING on an empty filter result that
    # otherwise lands in the channel id and produces a confusing 'not found'.
    $channel = (& gcloud beta monitoring channels create --project=$($env.project) `
        --display-name="Owner email" --type=email `
        --channel-labels=email_address=$($config.alertEmail) `
        --format="value(name)" --quiet 2>$null | Select-Object -Last 1)

    Invoke-Gcloud @(
        "alpha", "monitoring", "policies", "create", "--project=$($env.project)",
        "--policy-from-file=$policyFile", "--notification-channels=$channel", "--quiet"
    ) | Out-Null
    Write-Host "  [$($env.name)] quota alert created"
}

Remove-Item $policyFile -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "GCP guardrails applied."
