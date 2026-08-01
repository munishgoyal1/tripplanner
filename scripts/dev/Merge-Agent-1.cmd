@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-worker.ps1" -WorkerNumber 1
if errorlevel 1 pause