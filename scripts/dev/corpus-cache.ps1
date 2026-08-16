#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Keep the corpus's place grounding in the repository, not in one sandbox.

.DESCRIPTION
  Thin dispatcher over scripts/dev/corpus_cache.py using the repository virtual
  environment when one is present.

  -Save    reads a sandbox emulator database and merges what it finds into
           corpus/places.json, so the grounding survives the worktree.
  -Restore writes corpus/places.json into a sandbox database, so a fresh lane
           renders and checks trips without calling a provider.

  With no switch it reports what is stored and what each sandbox still holds
  that has not been saved.
#>

[CmdletBinding()]
param(
    [switch]$Save,
    [switch]$Restore,
    [string]$Database = "",
    [switch]$All,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# A sandbox worktree has no virtual environment of its own; the shared one lives
# in the primary checkout, which the git common directory points at.
$primaryRoot = $repoRoot
$commonDir = & git -C $repoRoot rev-parse --git-common-dir 2>$null
if ($LASTEXITCODE -eq 0 -and $commonDir) {
    $resolved = if ([System.IO.Path]::IsPathRooted($commonDir)) { $commonDir }
                else { Join-Path $repoRoot $commonDir }
    $primaryRoot = Split-Path -Parent (Resolve-Path $resolved).Path
}

$candidates = @(
    (Join-Path $repoRoot ".venv/bin/python"),
    (Join-Path $repoRoot ".venv/Scripts/python.exe"),
    (Join-Path $primaryRoot ".venv/bin/python"),
    (Join-Path $primaryRoot ".venv/Scripts/python.exe")
)
$python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    $python = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
}
if (-not $python) {
    throw "No Python interpreter found. Create the repository virtual environment first."
}

$argv = @()
if ($Save) { $argv += "--save" }
if ($Restore) { $argv += "--restore" }
if ($All) { $argv += "--all" }
if ($Database) { $argv += @("--database", $Database) }
if ($Rest) { $argv += $Rest }

$cli = Join-Path $PSScriptRoot "corpus_cache.py"
& $python $cli @argv
exit $LASTEXITCODE
