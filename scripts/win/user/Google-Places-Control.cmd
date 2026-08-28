@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\infra\gcp\set-google-places-access.ps1" %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
