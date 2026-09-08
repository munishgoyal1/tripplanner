@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\multiagent.ps1" pause %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
