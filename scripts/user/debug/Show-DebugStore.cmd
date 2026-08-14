@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\debug-store.ps1" show %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
