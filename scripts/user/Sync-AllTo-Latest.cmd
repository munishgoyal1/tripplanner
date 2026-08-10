@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\all-worktrees-sync.ps1" %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%