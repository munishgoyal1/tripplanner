#!/usr/bin/env pwsh
# Read the owner prompt log back as one newest-first stream.
#
# The active owner prompt log is master.txt. Retired worker logs remain historical
# records and are intentionally excluded from this view.
#
#   show-prompts.ps1                     master entries, newest first
#   show-prompts.ps1 -Important          only entries marked with !
#   show-prompts.ps1 -Search hotel       entries whose title or body matches
#   show-prompts.ps1 -TitlesOnly         one line per prompt
[CmdletBinding()]
param(
    [switch]$Important,
    [string]$Search,
    [int]$Last = 0,
    [switch]$TitlesOnly
)

$ErrorActionPreference = "Stop"

$promptLog = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "docs/reference/owner-inputs/prompts/master.txt"
if (-not (Test-Path $promptLog)) {
    throw "Master prompt log not found: $promptLog"
}

$headerPattern = '^\[(?<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] \[(?<lane>[^\]]+)\](?<imp>\s+!)?\s+(?<title>.+)$'
$entries = [System.Collections.Generic.List[pscustomobject]]::new()

    $current = $null
foreach ($line in Get-Content -LiteralPath $promptLog) {
    $match = [regex]::Match($line, $headerPattern)
    if ($match.Success) {
        if ($current) { $entries.Add($current) }
        $current = [pscustomobject]@{
            At        = [datetime]::ParseExact($match.Groups["ts"].Value, "yyyy-MM-dd HH:mm", $null)
            Lane      = $match.Groups["lane"].Value
            Important = $match.Groups["imp"].Success
            Title     = $match.Groups["title"].Value.Trim()
            Body      = [System.Collections.Generic.List[string]]::new()
        }
        continue
    }
    if ($current) { $current.Body.Add($line) }
}
if ($current) { $entries.Add($current) }

$view = $entries | Sort-Object At -Descending
if ($Important) { $view = @($view | Where-Object { $_.Important }) }
if ($Search) {
    $view = @($view | Where-Object { "$($_.Title) $($_.Body -join ' ')" -like "*$Search*" })
}
if ($Last -gt 0) { $view = @($view | Select-Object -First $Last) }

if (-not $view -or @($view).Count -eq 0) {
    Write-Host "No prompts matched." -ForegroundColor Yellow
    Write-Host "Entries before 5-Aug-2026 are archived in docs/reference/owner-inputs/prompts_executed.txt."
    return
}

foreach ($entry in $view) {
    $flag = if ($entry.Important) { " !" } else { "" }
    Write-Host ("[{0:yyyy-MM-dd HH:mm}] [{1}]{2} {3}" -f $entry.At, $entry.Lane, $flag, $entry.Title) -ForegroundColor Cyan
    if (-not $TitlesOnly) {
        foreach ($line in $entry.Body) {
            if ($line.Trim()) { Write-Host "    $line" }
        }
        Write-Host ""
    }
}

Write-Host ("{0} prompt(s). Entries before 5-Aug-2026: docs/reference/owner-inputs/prompts_executed.txt" -f @($view).Count) -ForegroundColor DarkGray
