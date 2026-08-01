@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-all-agents.ps1"
if errorlevel 1 pause