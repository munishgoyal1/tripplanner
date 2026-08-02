@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-all-agents.ps1" -ResolveConflicts %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%