# Auto-heal watcher -- tails the dev-server log and applies safe fixes for
# known recurring issues so Munish doesn't have to babysit the terminal.
#
# What it does (in one sentence): every new line from the server log is
# matched against a set of regex healers; on match, a small action runs
# (quarantine a corrupt file, clear stale __pycache__, print the exact pip
# install command, etc.) and a banner is printed to THIS terminal so you
# notice.
#
# Healers are intentionally conservative:
#   * Anything that requires installing packages is PRINTED, not executed.
#   * Anything that requires restarting the server prints "RESTART REQUIRED".
#   * Only fully reversible local actions (file rename, cache delete) run
#     automatically. Each healer has a cooldown so we don't spam.
#
# Usage (normally launched automatically by scripts/test.ps1):
#   .\scripts\autoheal.ps1                              # tail logs/server.log
#   .\scripts\autoheal.ps1 -LogPath logs/server-*.log   # tail specific file
#   .\scripts\autoheal.ps1 -DryRun                      # detect only, no fixes
#   .\scripts\autoheal.ps1 -Verbose                     # print every healer eval

[CmdletBinding()]
param(
    [string]$LogPath = "logs/server.log",
    [string]$ActionLog = "logs/autoheal.log",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Make sure log dir exists for the action log we write to.
$actionDir = Split-Path -Parent $ActionLog
if ($actionDir -and -not (Test-Path $actionDir)) {
    New-Item -ItemType Directory -Path $actionDir -Force | Out-Null
}

function Write-Banner {
    param([string]$Title, [string]$Tag = "match")
    $stamp = (Get-Date).ToString("HH:mm:ss")
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Yellow
    Write-Host "[$stamp] AUTO-HEAL [$Tag] $Title" -ForegroundColor Yellow
    Write-Host ("=" * 60) -ForegroundColor Yellow
}

function Write-Healer {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "  $Message" -ForegroundColor $Color
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $ActionLog -Value "[$stamp] $Message" -Encoding utf8
}

# -------- Healer definitions --------
# Each healer:
#   Name      short id (used for cooldown bucket)
#   Pattern   regex evaluated against the rolling buffer (multi-line)
#   Cooldown  seconds before the same healer can fire again
#   Action    scriptblock that takes the regex match
#
# Add new ones here -- keep them safe and reversible.

$Healers = @(
    @{
        Name     = "missing-python-module"
        Pattern  = "ModuleNotFoundError: No module named '([^']+)'"
        Cooldown = 60
        Action   = {
            param($m)
            $mod = $m.Groups[1].Value
            Write-Healer "Missing Python module: $mod" "Red"
            Write-Healer "Most likely you skipped a `pip install -e .[dev]` after a pull." "Yellow"
            Write-Healer "FIX (run in repo root, then restart server):" "Yellow"
            Write-Healer "    .\.venv\Scripts\python.exe -m pip install -e `".[dev]`"" "Green"
        }
    },
    @{
        Name     = "corrupt-prefs-json"
        Pattern  = "json\.decoder\.JSONDecodeError|Preferences file .* was corrupt"
        Cooldown = 30
        Action   = {
            param($m)
            $base = Join-Path $env:USERPROFILE ".multiagent"
            if (-not (Test-Path $base)) { return }
            $candidates = @()
            $candidates += Get-ChildItem -Path $base -Recurse -Filter "preferences.json" -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path $base -Recurse -Filter "active_trip.json" -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path $base -Filter "user_preferences.json" -ErrorAction SilentlyContinue
            $fixed = 0
            foreach ($f in $candidates) {
                try {
                    if ((Get-Item $f.FullName).Length -eq 0) { throw "empty file" }
                    Get-Content $f.FullName -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop | Out-Null
                } catch {
                    $corrupt = "$($f.FullName).corrupt.$(Get-Date -Format yyyyMMddHHmmss)"
                    if ($DryRun) {
                        Write-Healer "[DRY] would move $($f.FullName) -> $corrupt" "Yellow"
                    } else {
                        Move-Item -Force -Path $f.FullName -Destination $corrupt
                        Write-Healer "Quarantined corrupt JSON: $($f.FullName)" "Green"
                        Write-Healer "  (kept as $corrupt; app will recreate defaults next request)" "DarkGray"
                        $fixed++
                    }
                }
            }
            if ($fixed -eq 0) {
                Write-Healer "No corrupt JSON files found under $base -- the app's own self-heal may have already handled it." "DarkGray"
            }
        }
    },
    @{
        Name     = "stale-pyc-cache"
        Pattern  = "ImportError: bad magic number|EOFError: marshal data too short|SyntaxError: source code string cannot contain null bytes"
        Cooldown = 120
        Action   = {
            param($m)
            $caches = Get-ChildItem -Path "src" -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
            if (-not $caches) {
                Write-Healer "No __pycache__ dirs found under src/." "DarkGray"
                return
            }
            if ($DryRun) {
                Write-Healer "[DRY] would remove $($caches.Count) __pycache__ dir(s)" "Yellow"
            } else {
                $caches | Remove-Item -Recurse -Force
                Write-Healer "Cleared $($caches.Count) __pycache__ dir(s) under src/" "Green"
                Write-Healer "RESTART REQUIRED: Ctrl+C the server terminal, then Up-arrow + Enter" "Yellow"
            }
        }
    },
    @{
        Name     = "port-in-use"
        Pattern  = "OSError: \[Errno 10048\]|address already in use|only one usage of each socket address"
        Cooldown = 60
        Action   = {
            param($m)
            $port = 8000
            if ($env:API_PORT) { $port = $env:API_PORT }
            Write-Healer "Port $port is already in use." "Red"
            $owner = $null
            try {
                $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($conn) {
                    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                    if ($proc) { $owner = "$($proc.ProcessName) (PID $($proc.Id))" }
                }
            } catch {}
            if ($owner) {
                Write-Healer "Listener: $owner" "Yellow"
                Write-Healer "FIX (kills the stale listener -- WILL stop that process):" "Yellow"
                Write-Healer "    Stop-Process -Id $($conn.OwningProcess) -Force" "Green"
            } else {
                Write-Healer "Could not identify the listener. Try a different port: .\scripts\test.ps1 -Port 8001" "Yellow"
            }
        }
    },
    @{
        Name     = "azure-openai-bad-api-version"
        Pattern  = "openai\.NotFoundError|DeploymentNotFound|InvalidApiVersion|Resource not found.*openai|openai.*Resource not found"
        Cooldown = 120
        Action   = {
            param($m)
            $cur = $env:AZURE_OPENAI_API_VERSION
            Write-Healer "Azure OpenAI returned 404 -- likely a bad AZURE_OPENAI_API_VERSION or AZURE_OPENAI_DEPLOYMENT in .env." "Red"
            Write-Healer "Current api-version: $(if ($cur) { $cur } else { '<unset>' })" "Yellow"
            Write-Healer "Known-good api-version (data-plane GA):  2024-10-21" "Green"
            Write-Healer "Common bad value (model snapshot date):  2024-11-20  <-- this is NOT an API version" "Yellow"
            Write-Healer "Also verify AZURE_OPENAI_DEPLOYMENT matches a real deployment name in your Azure resource." "Yellow"
        }
    },
    @{
        Name     = "openai-auth-401"
        Pattern  = "AuthenticationError|401 Unauthorized.*openai|Invalid API key provided"
        Cooldown = 120
        Action   = {
            param($m)
            Write-Healer "OpenAI / Azure OpenAI 401 -- API key invalid or expired." "Red"
            Write-Healer "Check .env for: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT" "Yellow"
            Write-Healer "If you rotated the key in the portal, copy the new value into .env and restart." "Yellow"
        }
    },
    @{
        Name     = "rate-limit-429"
        Pattern  = "RateLimitError|429.*Too Many Requests|throttle"
        Cooldown = 60
        Action   = {
            param($m)
            Write-Healer "Upstream rate-limited (429). Detection only -- not auto-fixable." "Yellow"
            Write-Healer "Tip: wait ~30s and retry, or switch deployment if you have a second one." "DarkGray"
        }
    }
)

# -------- Startup banner --------

Write-Host ""
Write-Host "+----------------------------------------------------+" -ForegroundColor Magenta
Write-Host "|  Trip Planner -- auto-heal watcher                 |" -ForegroundColor Magenta
Write-Host "|  Tailing : $LogPath" -ForegroundColor Magenta
Write-Host "|  Action  : $ActionLog" -ForegroundColor Magenta
Write-Host "|  Healers : $($Healers.Count) loaded$(if ($DryRun) { ' (DRY-RUN)' })" -ForegroundColor Magenta
Write-Host "|  Stop    : Ctrl+C in THIS terminal                 |" -ForegroundColor Magenta
Write-Host "+----------------------------------------------------+" -ForegroundColor Magenta
Write-Host ""
Write-Host "Loaded healers:" -ForegroundColor DarkGray
foreach ($h in $Healers) {
    Write-Host "  - $($h.Name) (cooldown $($h.Cooldown)s)" -ForegroundColor DarkGray
}
Write-Host ""

# Wait for the log file to appear (test.ps1 launches us before the server writes).
$waited = 0
while (-not (Test-Path $LogPath)) {
    if ($waited % 5 -eq 0) {
        Write-Host "Waiting for $LogPath ..." -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 1
    $waited++
    if ($waited -gt 120) {
        Write-Host "Gave up waiting for $LogPath after 2 min. Exiting." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Tailing $LogPath ..." -ForegroundColor Green
Write-Host ""

# Rolling buffer for multi-line patterns (tracebacks span many lines).
$buffer = New-Object System.Collections.Generic.Queue[string]
$bufferSize = 40
$lastTriggered = @{}

Get-Content -Path $LogPath -Wait -Tail 0 -ErrorAction SilentlyContinue | ForEach-Object {
    $line = $_
    if ($null -eq $line) { return }

    # Echo a dimmed copy so the watcher window doubles as a tail.
    Write-Host $line -ForegroundColor DarkGray

    $buffer.Enqueue($line)
    while ($buffer.Count -gt $bufferSize) { [void]$buffer.Dequeue() }
    $window = [string]::Join("`n", $buffer.ToArray())

    foreach ($h in $Healers) {
        if ($lastTriggered.ContainsKey($h.Name)) {
            $age = ((Get-Date) - $lastTriggered[$h.Name]).TotalSeconds
            if ($age -lt $h.Cooldown) { continue }
        }
        $match = [regex]::Match($window, $h.Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($match.Success) {
            $lastTriggered[$h.Name] = Get-Date
            Write-Banner $h.Name $(if ($DryRun) { "dry-run" } else { "fixing" })
            try {
                & $h.Action $match
            } catch {
                Write-Healer "Healer '$($h.Name)' raised: $_" "Red"
            }
        }
    }
}
