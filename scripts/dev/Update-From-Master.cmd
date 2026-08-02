@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-from-master.ps1" %*
exit /b %errorlevel%
