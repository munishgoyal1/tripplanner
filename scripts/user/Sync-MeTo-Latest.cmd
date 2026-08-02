@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\sync-latest.ps1" %*
exit /b %errorlevel%