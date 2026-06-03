# One-shot wrapper for interactive testing of the Chainlit web UI.
#
# This is THE script to use when Munish is sitting at the browser testing
# changes the agent is making. It defaults to:
#   * NoBrowser  -- don't auto-open VS Code's integrated browser (use external)
#   * WithAuth   -- enable Google/GitHub OAuth + guest cookie
#   * NoWatch    -- DO NOT hot-reload on .py edits, so the chat session
#                   isn't blown away every time the agent touches a file
#
# Workflow:
#   1. .\scripts\test.ps1                # starts the server, prints URL
#   2. Open http://localhost:8000 in your normal browser (Chrome/Edge/Firefox)
#   3. Chat with the agent. Munish makes feature requests, agent edits files.
#      The chat KEEPS RUNNING because hot reload is OFF.
#   4. When you want to test the agent's latest code change:
#        - Click on this terminal (where Chainlit is printing logs)
#        - Press Ctrl+C  -> server stops
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

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Cosmos,
    [switch]$OpenBrowser,
    [switch]$Watch
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$forwarded = @("-Port", $Port, "-WithAuth")
if (-not $OpenBrowser) { $forwarded += "-NoBrowser" }
if (-not $Watch)       { $forwarded += "-NoWatch" }
if ($Cosmos)           { $forwarded += "-UseCosmos" }

Write-Host ""
Write-Host "==> scripts/test.ps1 launching dev server with:" -ForegroundColor Cyan
Write-Host "    $($forwarded -join ' ')" -ForegroundColor Cyan
Write-Host ""

& "$PSScriptRoot\dev.ps1" @forwarded
