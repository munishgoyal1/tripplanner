. "$PSScriptRoot/../scripts/dev/lib/run-log.ps1"

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

            if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
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