@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-latest.ps1"
if errorlevel 1 pause