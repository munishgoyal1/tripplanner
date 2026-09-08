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

. (Join-Path $PSScriptRoot "lib/python-runtime.ps1")
$python = (Resolve-TripplannerPython -RepoRoot $repoRoot).Python

$argv = @()
if ($Save) { $argv += "--save" }
if ($Restore) { $argv += "--restore" }
if ($All) { $argv += "--all" }
if ($Database) { $argv += @("--database", $Database) }
if ($Rest) { $argv += $Rest }

$cli = Join-Path $PSScriptRoot "corpus_cache.py"
& $python $cli @argv
exit $LASTEXITCODE
