@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\resolve-conflicts.ps1" %*
exit /b %errorlevel%
