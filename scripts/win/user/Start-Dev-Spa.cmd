@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\dev-spa.ps1" %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%