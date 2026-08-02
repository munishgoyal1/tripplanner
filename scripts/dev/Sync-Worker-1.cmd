@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-worker.ps1" -WorkerNumber 1 -ResolveConflicts %*
if errorlevel 1 pause