. "$PSScriptRoot/../scripts/dev/lib/run-log.ps1"

function Get-DeploymentUser {
    foreach ($candidate in @($env:USERNAME, $env:USER, $env:LOGNAME)) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            return $candidate
        }
    }
    return [System.Environment]::UserName
}

function Import-DeploymentEnvironment {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path $Path)) {
        # Worktrees and sandboxes never carry .env.*; fall back to the primary checkout.
        $shared = Join-Path (Get-PrimaryRepoRoot) (Split-Path -Leaf $Path)
        if (-not (Test-Path $shared)) {
            throw "Deployment environment file not found: $Path (also looked in $shared)"
        }
        Write-Host "[env]     $shared"
        $Path = $shared
    }

    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()

            # The target environment's file wins. Deferring to whatever the shell
            # already exported let a local .env leak into canary and prod, which
            # is how both ended up on the local Redis and its namespace.
            $existing = [Environment]::GetEnvironmentVariable($name, 'Process')
            if ($null -ne $existing -and $existing -ne $value) {
                Write-Host "[env]     $name overridden by $(Split-Path -Leaf $Path)"
            }
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

function Get-RuntimeLimitEnvArgs {
    <#
    .SYNOPSIS
    Every runtime limit from a config profile, as NAME=value args for
    `az containerapp update --set-env-vars`.

    .DESCRIPTION
    Both deploy scripts previously hand-listed the limit variables they pushed
    into Container Apps. That list covered six of the twenty-two names in the
    profile, so canary and production silently ran the hardcoded defaults in
    limits_config.py for everything else -- prod ran a tool-phase budget of 10
    while prod.env said 50. Deriving the list from the profile's own throttling
    block means adding a limit to the profile is enough; the deploy cannot
    drift from it again.

    Names come from the config file; values come from the process environment,
    so a secret overlay imported afterwards still wins.
    #>
    param([Parameter(Mandatory)][string]$ConfigFile)

    if (-not (Test-Path $ConfigFile)) {
        $ConfigFile = Join-Path (Get-PrimaryRepoRoot) $ConfigFile
        if (-not (Test-Path $ConfigFile)) {
            throw "Config profile not found for limit export: $ConfigFile"
        }
    }

    $startMarker = '# === Request throttling & usage limits ==='
    $endMarker = '# === End: Request throttling & usage limits ==='
    $inBlock = $false
    $args = @()

    foreach ($line in Get-Content $ConfigFile) {
        if ($line.Trim() -eq $startMarker) { $inBlock = $true; continue }
        if ($line.Trim() -eq $endMarker) { $inBlock = $false; continue }
        if (-not $inBlock) { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=') {
            $name = $matches[1].Trim()
            $value = [Environment]::GetEnvironmentVariable($name, 'Process')
            if ([string]::IsNullOrWhiteSpace($value)) {
                # An empty value would reach the container as NAME= and the app
                # would fall back to a code default -- silently, and for a cost
                # ceiling that is the difference between enforced and absent.
                throw "Runtime limit $name is empty after importing $ConfigFile. Refusing to deploy a profile whose limits would not take effect."
            }
            $args += "$name=$value"
        }
    }

    if ($args.Count -eq 0) {
        throw "No runtime limits found in $ConfigFile. The throttling block markers may have changed."
    }
    return $args
}

function ConvertFrom-AzureCliJson {
    param(
        [Parameter(Mandatory)][string]$Output,
        [Parameter(Mandatory)][string]$Action
    )

    $jsonStart = $Output.IndexOf('{')
    $jsonEnd = $Output.LastIndexOf('}')
    if ($jsonStart -lt 0 -or $jsonEnd -lt $jsonStart) {
        throw "$Action did not return JSON. Raw output:`n$Output"
    }
    return $Output.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
}

function Get-AzureOpenAiResourceGroup {
    param(
        [Parameter(Mandatory)][string]$AccountName,
        [Parameter(Mandatory)][string]$SubscriptionId
    )

    $resourceGroups = @(az resource list `
        --subscription $SubscriptionId `
        --name $AccountName `
        --resource-type Microsoft.CognitiveServices/accounts `
        --query "[].resourceGroup" `
        --output tsv)
    if ($LASTEXITCODE -ne 0 -or $resourceGroups.Count -ne 1) {
        throw "Expected exactly one Azure OpenAI account named $AccountName in subscription $SubscriptionId."
    }
    return $resourceGroups[0]
}

function Assert-DeploymentHasNoDeletes {
    param(
        [Parameter(Mandatory)]$WhatIf,
        [Parameter(Mandatory)][string]$EnvironmentName
    )

    $deletes = @($WhatIf.properties.changes | Where-Object { $_.changeType -eq "Delete" })
    if ($deletes.Count -gt 0) {
        throw "$EnvironmentName what-if contains $($deletes.Count) delete operation(s); review with -DryRun."
    }
}

function Start-DeploymentTimer {
    return [System.Diagnostics.Stopwatch]::StartNew()
}

function Complete-DeploymentTimer {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][System.Diagnostics.Stopwatch]$Timer
    )

    $Timer.Stop()
    $seconds = [math]::Round($Timer.Elapsed.TotalSeconds, 1)
    Write-Host "[timing]  $Name`: ${seconds}s"
    return $seconds
}