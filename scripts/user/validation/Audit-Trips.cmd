@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\trip-audit.ps1" %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
