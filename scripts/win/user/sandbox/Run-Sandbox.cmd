@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\sandbox.ps1" -Run %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
