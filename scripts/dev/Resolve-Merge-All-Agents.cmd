@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-all-agents.ps1" -ResolveConflicts %*
if errorlevel 1 pause