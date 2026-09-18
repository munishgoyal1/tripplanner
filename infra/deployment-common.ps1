. "$PSScriptRoot/../scripts/dev/lib/run-log.ps1"

# Every `az deployment` call compiles Bicep and, by default, first asks GitHub
# whether a newer Bicep exists: ~2.7s and a network round trip per compile,
# for a nag. Upgrade deliberately with `az bicep upgrade` instead.
$env:AZURE_BICEP_CHECK_VERSION = "false"

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

function Test-GhcrPublishToken {
    <#
    .SYNOPSIS
    Why a token cannot publish to GHCR as $User, or $null when it can.

    .DESCRIPTION
    GHCR's own read endpoints prove nothing: the package is public, so an
    anonymous manifest read succeeds with no credential at all.
    That is how an empty Docker credential store passed the old preflight and
    failed only at `docker push`, eleven minutes into a canary deploy. GitHub's
    /user endpoint reports the token's owner and classic scopes, which are what
    GHCR checks on push.
    #>
    param(
        [Parameter(Mandatory)][string]$Token,
        [Parameter(Mandatory)][string]$User
    )

    try {
        $response = Invoke-WebRequest `
            -Uri "https://api.github.com/user" `
            -Headers @{ Authorization = "Bearer $Token"; "User-Agent" = "tripplanner-deploy" } `
            -TimeoutSec 20 `
            -ErrorAction Stop
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        if ($status -eq 401) {
            return "GitHub rejected it as expired or revoked"
        }
        return "GitHub could not verify it ($($_.Exception.Message))"
    }

    $login = ($response.Content | ConvertFrom-Json).login
    if ($login -ne $User) {
        return "it belongs to '$login', not '$User'"
    }
    $scopes = @((@($response.Headers['X-OAuth-Scopes']) -join ',').Split(',') |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ })
    if ($scopes -notcontains "write:packages") {
        $held = if ($scopes.Count -eq 0) { "none" } else { $scopes -join ', ' }
        return "it lacks the classic write:packages scope (scopes: $held)"
    }
    return $null
}

function Get-DockerStoredRegistryToken {
    param([Parameter(Mandatory)][string]$Registry)

    $configDir = if ($env:DOCKER_CONFIG) { $env:DOCKER_CONFIG } else { Join-Path $HOME ".docker" }
    $configPath = Join-Path $configDir "config.json"
    if (-not (Test-Path $configPath)) {
        return $null
    }
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }

    $inline = $config.auths.$Registry.auth
    if (-not [string]::IsNullOrWhiteSpace($inline)) {
        $pair = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($inline))
        return ($pair -split ':', 2)[1]
    }

    $store = $config.credHelpers.$Registry
    if ([string]::IsNullOrWhiteSpace($store)) {
        $store = $config.credsStore
    }
    if ([string]::IsNullOrWhiteSpace($store)) {
        return $null
    }
    $helper = Get-Command "docker-credential-$store" -ErrorAction SilentlyContinue
    if ($null -eq $helper) {
        return $null
    }
    foreach ($server in @($Registry, "https://$Registry")) {
        $raw = ($server | & $helper.Source get 2>$null | Out-String)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
            continue
        }
        try {
            $secret = ($raw | ConvertFrom-Json).Secret
        } catch {
            continue
        }
        if (-not [string]::IsNullOrWhiteSpace($secret)) {
            return $secret
        }
    }
    return $null
}

function Resolve-GhcrPublishCredential {
    <#
    .SYNOPSIS
    The first available token that can push to GHCR, with where it came from.

    .DESCRIPTION
    Candidates, in order: GHCR_TOKEN, CR_PAT, GITHUB_TOKEN, the GitHub CLI token,
    and the ghcr.io credential in Docker's store. Every candidate is verified
    the same way, and a rejected one is reported by source (never by value) so
    the owner knows which credential to refresh. Throws when none qualifies.
    #>
    param(
        [string]$Registry = "ghcr.io",
        [string]$User = "munishgoyal1"
    )

    $candidates = [System.Collections.Generic.List[object]]::new()
    foreach ($name in @("GHCR_TOKEN", "CR_PAT", "GITHUB_TOKEN")) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $candidates.Add([pscustomobject]@{ Source = $name; Token = $value })
        }
    }
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        $ghToken = (& gh auth token --hostname github.com 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($ghToken)) {
            $candidates.Add([pscustomobject]@{ Source = "GitHub CLI"; Token = $ghToken })
        }
    }
    $storedToken = Get-DockerStoredRegistryToken -Registry $Registry
    if (-not [string]::IsNullOrWhiteSpace($storedToken)) {
        $candidates.Add([pscustomobject]@{ Source = "Docker credential store"; Token = $storedToken })
    }

    $rejections = @()
    foreach ($candidate in $candidates) {
        # An Actions installation token cannot call /user; the workflow's
        # packages: write permission is what authorises it.
        if ($candidate.Source -eq "GITHUB_TOKEN" -and $env:GITHUB_ACTIONS -eq "true") {
            return $candidate
        }
        $reason = Test-GhcrPublishToken -Token $candidate.Token -User $User
        if ($null -eq $reason) {
            return $candidate
        }
        $rejections += "$($candidate.Source): $reason"
    }

    $found = if ($rejections.Count -eq 0) {
        "No GHCR credential was found (checked GHCR_TOKEN, CR_PAT, GITHUB_TOKEN, GitHub CLI, Docker credential store)."
    } else {
        "No GHCR credential can publish as ${User}:`n  - " + ($rejections -join "`n  - ")
    }
    throw ("$found`nFix one, then retry: run 'gh auth refresh -h github.com -s write:packages', " +
        "or set GHCR_TOKEN to a classic PAT with write:packages.")
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