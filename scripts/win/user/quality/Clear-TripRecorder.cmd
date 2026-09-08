@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\debug-store.ps1" clear %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%