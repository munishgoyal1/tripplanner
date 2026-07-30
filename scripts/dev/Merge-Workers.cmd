@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-workers.ps1"
if errorlevel 1 pause