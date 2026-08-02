@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-latest.ps1" %*
exit /b %errorlevel%
