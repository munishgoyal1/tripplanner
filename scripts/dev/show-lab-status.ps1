#!/usr/bin/env pwsh
# Report the authoritative lifecycle state of every UX Lab.
#
# Lab status has one tracked canonical store plus committed fallbacks:
#   - docs/ux-experiments/LAB_SELECTIONS.json contains versioned owner and agent history
#   - frontend/labs/src/shared/labRecords.ts is the fallback for labs without history
# A machine-local cache is merged into the canonical store by the Labs server.
#
# Reading only the committed file gives a stale answer. Run this before quoting
# which Labs are open. Rows marked DRIFT need labRecords.ts updated to match.
#
#   show-lab-status.ps1              every lab, newest first
#   show-lab-status.ps1 -DriftOnly   only labs whose committed default is wrong
[CmdletBinding()]
param(
    [switch]$DriftOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$recordsPath = Join-Path $repoRoot "frontend/labs/src/shared/labRecords.ts"
$storePath = Join-Path $repoRoot "docs/ux-experiments/LAB_SELECTIONS.json"

if (-not (Test-Path $recordsPath)) { throw "Lab records not found: $recordsPath" }

$store = @{}
if (Test-Path $storePath) {
    (Get-Content $storePath -Raw | ConvertFrom-Json).PSObject.Properties |
        ForEach-Object { $store[$_.Name] = $_.Value }
} else {
    Write-Warning "No canonical decision store at $storePath. Showing committed defaults only."
}

$source = Get-Content $recordsPath -Raw
$recordPattern = '(?s)labNumber:\s*(?<number>\d+),\s*\r?\n\s*id:\s*"(?<id>[^"]+)".*?defaultDisposition:\s*"(?<disposition>[^"]+)"'
$rows = foreach ($match in [regex]::Matches($source, $recordPattern)) {
    $id = $match.Groups["id"].Value
    $committed = $match.Groups["disposition"].Value
    $saved = $store[$id]
    $live = if ($saved -and $saved.disposition) { $saved.disposition } else { $committed }
    [pscustomobject]@{
        Lab       = [int]$match.Groups["number"].Value
        Id        = $id
        Live      = $live
        Committed = $committed
        Selection = if ($saved) { $saved.selectionLabel } else { "" }
        Drift     = if ($live -ne $committed) { "DRIFT" } else { "" }
    }
}

$rows = $rows | Sort-Object Lab -Descending
if ($DriftOnly) { $rows = $rows | Where-Object { $_.Drift } }
$rows | Format-Table -AutoSize

$drifted = @($rows | Where-Object { $_.Drift })
if ($drifted.Count) {
    Write-Host "$($drifted.Count) lab(s) drifted. Update defaultDisposition in labRecords.ts to match Live." -ForegroundColor Yellow
}
