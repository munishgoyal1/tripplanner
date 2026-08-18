@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\show-prompts.ps1" %*
exit /b %errorlevel%
