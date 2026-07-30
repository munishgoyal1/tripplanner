@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-agent-1.ps1"
if errorlevel 1 pause