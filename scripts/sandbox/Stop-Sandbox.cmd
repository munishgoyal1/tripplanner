@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\sandbox.ps1" -Stop %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
