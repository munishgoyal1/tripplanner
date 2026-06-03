# One-shot wrapper for interactive testing of the Chainlit web UI.
#
# This is THE script to use when Munish is sitting at the browser testing
# changes the agent is making. It defaults to:
#   * NoBrowser  -- don't auto-open VS Code's integrated browser (use external)
#   * WithAuth   -- enable Google/GitHub OAuth + guest cookie
#   * NoWatch    -- DO NOT hot-reload on .py edits, so the chat session
#                   isn't blown away every time the agent touches a file
#   * AutoHeal   -- start scripts/autoheal.ps1 in a SECOND pwsh window that
#                   tails the server log and auto-fixes recurring issues
#                   (corrupt prefs, stale .pyc, missing modules, port-in-use,
#                    Azure OpenAI bad api-version, 401s, 429s).
#                   Disable with -NoAutoHeal if you don't want it.
#
# Workflow:
#   1. .\scripts\test.ps1                # starts the server + watcher window
#   2. Open http://localhost:8000 in your normal browser (Chrome/Edge/Firefox)
#   3. Chat with the agent. Munish makes feature requests, agent edits files.
#      The chat KEEPS RUNNING because hot reload is OFF.
#   4. When you want to test the agent's latest code change:
#        - Click on this terminal (where Chainlit is printing logs)
#        - Press Ctrl+C  -> server stops, watcher window auto-closes
#        - Press Up arrow then Enter  -> reruns this script
#        - Switch to browser, press F5 (or Ctrl+Shift+R if F5 doesn't refresh)
#   5. Repeat 3-4.
#
# Flags (all optional):
#   -Port <int>    custom port (default 8000)
#   -Cosmos        use the production Cosmos DB instead of local JSON
#                  (DANGER: writes to live data -- use a test identity)
#   -OpenBrowser   override -NoBrowser and auto-open VS Code's built-in browser
#                  (NOT recommended; the agent shouldn't see your chat)
#   -Watch         override -NoWatch and re-enable hot reload (you'll lose
#                  the chat session on every .py edit; only use when you're
#                  the one editing files, not the agent)
#   -NoAutoHeal    don't spawn the auto-heal watcher window
#   -AutoHealDryRun  launch the watcher in detection-only mode (logs would-be
#                    fixes without doing them; useful when validating new healers)

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Cosmos,
    [switch]$OpenBrowser,
    [switch]$Watch,
    [switch]$NoAutoHeal,
    [switch]$AutoHealDryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# --- Auto-heal: generate a per-run log file and spawn the watcher window first.
$watcherProc = $null
$logFile = $null
if (-not $NoAutoHeal) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logsDir = Join-Path $repoRoot "logs"
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
    $logFile = Join-Path $logsDir "server-$stamp.log"

    $watcherScript = Join-Path $PSScriptRoot "autoheal.ps1"
    $watcherArgs = @(
        "-NoExit",
        "-NoLogo",
        "-ExecutionPolicy", "Bypass",
        "-File", $watcherScript,
        "-LogPath", $logFile
    )
    if ($AutoHealDryRun) { $watcherArgs += "-DryRun" }

    Write-Host ""
    Write-Host "==> Auto-heal ON. Spawning watcher window..." -ForegroundColor Cyan
    Write-Host "    Server log: $logFile" -ForegroundColor DarkGray
    Write-Host "    To disable next time: .\scripts\test.ps1 -NoAutoHeal" -ForegroundColor DarkGray

    try {
        $watcherProc = Start-Process -FilePath "pwsh" -ArgumentList $watcherArgs `
            -WorkingDirectory $repoRoot -PassThru
    } catch {
        # Fall back to powershell.exe if pwsh isn't on PATH.
        $watcherProc = Start-Process -FilePath "powershell" -ArgumentList $watcherArgs `
            -WorkingDirectory $repoRoot -PassThru
    }
}

$forwarded = @("-Port", $Port, "-WithAuth")
if (-not $OpenBrowser) { $forwarded += "-NoBrowser" }
if (-not $Watch)       { $forwarded += "-NoWatch" }
if ($Cosmos)           { $forwarded += "-UseCosmos" }
if ($logFile)          { $forwarded += @("-LogFile", $logFile) }

Write-Host ""
Write-Host "==> scripts/test.ps1 launching dev server with:" -ForegroundColor Cyan
Write-Host "    $($forwarded -join ' ')" -ForegroundColor Cyan
Write-Host ""

try {
    & "$PSScriptRoot\dev.ps1" @forwarded
} finally {
    if ($watcherProc -and -not $watcherProc.HasExited) {
        Write-Host ""
        Write-Host "==> Closing auto-heal watcher (PID $($watcherProc.Id))..." -ForegroundColor DarkGray
        try { Stop-Process -Id $watcherProc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}
