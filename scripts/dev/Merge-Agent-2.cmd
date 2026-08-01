@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-agent-2.ps1"
if errorlevel 1 pause