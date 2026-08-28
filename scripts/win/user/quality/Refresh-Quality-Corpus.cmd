@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\refresh-audit-corpus.ps1"
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%