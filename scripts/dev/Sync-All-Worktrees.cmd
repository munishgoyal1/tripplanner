@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-all-worktrees.ps1" -ResolveConflicts %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%