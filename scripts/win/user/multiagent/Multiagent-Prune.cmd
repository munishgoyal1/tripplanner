@echo off
set "args=%*"
set "args=%args:-DryRun=--dry-run%"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\multiagent.ps1" prune %args%
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%