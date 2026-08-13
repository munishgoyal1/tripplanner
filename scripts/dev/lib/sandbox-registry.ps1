#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Shared sandbox registry lookup used by every sandbox-facing script.

.DESCRIPTION
  One resolver so "2", "2-lab16-chatdock", and "lab16-chatdock" reach the same
  sandbox from any entry point. Duplicating this per script is what let the
  launchers drift apart.
#>

function Get-SandboxRegistryPath {
    param([Parameter(Mandatory = $true)][string]$PrimaryRoot)
    return "$PrimaryRoot.worktrees/sandboxes.json"
}

function Get-SandboxRegistry {
    param([Parameter(Mandatory = $true)][string]$PrimaryRoot)
    $path = Get-SandboxRegistryPath -PrimaryRoot $PrimaryRoot
    if (-not (Test-Path $path -PathType Leaf)) { return @() }
    $raw = Get-Content -Raw -Path $path
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    return @($raw | ConvertFrom-Json)
}

function Get-SandboxEntryNumber {
    # The number is the port slot: #1 serves 8100/5273/5275, #2 serves 8110/5283/5285.
    param([Parameter(Mandatory = $true)][object]$Entry)
    return ([int]$Entry.slot) + 1
}

function Get-SandboxShortName {
    param([Parameter(Mandatory = $true)][string]$Name)
    return ($Name -replace "^\d+-", "")
}

function Select-SandboxEntry {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Entries,
        [Parameter(Mandatory = $true)][string]$Reference
    )

    if ($Entries.Count -eq 0) {
        throw "No sandboxes are registered."
    }
    $match = @($Entries | Where-Object { $_.slug -eq $Reference })
    if ($match.Count -eq 0 -and $Reference -match "^\d+$") {
        $match = @($Entries | Where-Object { (Get-SandboxEntryNumber -Entry $_) -eq [int]$Reference })
    }
    if ($match.Count -eq 0) {
        $short = Get-SandboxShortName -Name $Reference
        $match = @($Entries | Where-Object { (Get-SandboxShortName -Name $_.slug) -eq $short })
    }
    if ($match.Count -eq 1) { return $match[0] }
    if ($match.Count -gt 1) {
        $slugs = ($match | ForEach-Object { $_.slug }) -join ", "
        throw "'$Reference' matches more than one sandbox: $slugs. Use the number instead."
    }
    $known = ($Entries | ForEach-Object { "#$(Get-SandboxEntryNumber -Entry $_) $($_.slug)" }) -join ", "
    throw "Unknown sandbox '$Reference'. Registered: $known."
}
